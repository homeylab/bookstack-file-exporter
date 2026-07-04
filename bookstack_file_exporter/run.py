import argparse
import logging
import signal
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable

from bookstack_file_exporter.config_helper.config_helper import ConfigNode
from bookstack_file_exporter.exporter.node import Node
from bookstack_file_exporter.exporter.exporter import NodeExporter
from bookstack_file_exporter.exporter.filter import NodeFilter
from bookstack_file_exporter.archiver.archiver import Archiver
from bookstack_file_exporter.common.util import HttpHelper, seconds_until_next_cron
from bookstack_file_exporter.notify.handler import NotifyHandler
from bookstack_file_exporter.notify.models import (
    NotifyResult, ExportStatus, STATUS_EFFECTS, format_run_summary)
from bookstack_file_exporter.health.status import RunStatus
from bookstack_file_exporter.health.server import start_health_server

log = logging.getLogger(__name__)


class NoContentArchivedError(Exception):
    """Every fetch failed and nothing was archived: no backup exists for this run.

    A hard failure (exit 1 / failure notification / mark_failed), NOT Partial —
    Partial promises some of the backup survived."""


def entrypoint(args: argparse.Namespace) -> int:
    """Entrypoint for the export process. Returns an exit code."""
    try:
        config = ConfigNode(args)
    except Exception as err:  # pylint: disable=broad-except
        log.error("Configuration error: %s", err)
        log.debug("Traceback:", exc_info=True)
        return 1

    inputs = config.user_inputs
    if args.run_once or (not inputs.run_interval and not inputs.run_schedule):
        return _run_once(config)
    if inputs.run_schedule:
        return _run_scheduled(
            config, lambda: seconds_until_next_cron(inputs.run_schedule, datetime.now()))
    return _run_scheduled(config, lambda: inputs.run_interval)


def _install_signal_handlers(stop: threading.Event) -> dict:
    """Install SIGTERM/SIGINT handlers for cooperative shutdown in both run modes.

    Signal handlers run in the main thread between bytecodes, mid-anything;
    raising across arbitrary code is unsafe and SIGTERM has no default
    exception. So the handler only SETS the stop flag (which also breaks
    scheduled mode's interruptible stop.wait()); the export polls it at
    checkpoints to cancel. It also restores the default disposition for BOTH
    catchable signals so that ANY second signal -- not only an identical
    repeat -- force-kills via the kernel with its conventional exit code
    (SIGINT->130, SIGTERM->143). This is an operator escape hatch if a slow
    in-flight download won't drain inside the grace window (e.g. `docker stop`
    then an impatient Ctrl-C).

    Returns the dict the handler records the signal number into; one-shot mode
    reads it to derive its 128+signum exit code (scheduled mode exits 0).
    """
    received = {}

    def _handle_signal(signum, _frame):
        received["signum"] = signum
        log.info("Received signal %s, shutting down (signal again to force)", signum)
        stop.set()
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.signal(signal.SIGINT, signal.SIG_DFL)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    return received


def _run_once(config: ConfigNode) -> int:
    """Run the export exactly once and return an exit code.

    Cancellation is cooperative via a shared threading.Event -- the same
    mechanism scheduled mode uses. The export polls it at checkpoints (fetch,
    node, per-format, per-asset boundaries) and bails; the exporter's `finally`
    still runs discard_incomplete, which matters for ephemeral one-shot containers
    (`docker run --rm`, a k8s Job) where no later run exists to sweep a
    stranded `.tgz.incomplete` off the output volume. The first signal restores
    the default disposition for both signals so a second signal force-kills
    via the kernel. Exit code is 128+signum (SIGINT->130, SIGTERM->143).

    A signal that lands after archiving (during archive finalize/upload/cleanup,
    which have no checkpoints) lets the run finish, and the exit code reflects the run's
    actual outcome -- matching scheduled mode finishing its cycle instead of
    force-stopping mid-upload.
    """
    stop = threading.Event()
    received = _install_signal_handlers(stop)

    try:
        result = run(config, stop)
        if result is None:
            # Cycle cancelled by the shutdown signal (exporter's
            # shutdown-during-fetch / shutdown-mid-cycle paths).
            signum = int(received.get("signum", signal.SIGINT))
            log.info("Interrupted by signal %s, exiting", signum)
            return 128 + signum
        code = STATUS_EFFECTS[result.status].exit_code
        log.info("One-shot run exit code: %d", code)
        return code
    except KeyboardInterrupt:
        # Backstop only: a Ctrl-C landing in the brief window before the
        # handlers above are installed still raises normally.
        signum = int(received.get("signum", signal.SIGINT))
        log.info("Interrupted by signal %s, exiting", signum)
        return 128 + signum
    except Exception:  # pylint: disable=broad-except
        # run() already logged the terminal "Run summary [FAILED]" line before
        # re-raising, so avoid a duplicate error line here; keep the traceback.
        log.debug("Traceback:", exc_info=True)
        return 1


def _run_cycle(config: ConfigNode, stop: threading.Event, status: RunStatus | None) -> None:
    """Execute one scheduled export cycle and reflect its outcome in health status.

    Owns the full mark_running -> run -> success/degraded/failed transition for a
    single cycle so the scheduling loop stays a thin timer. A cycle's own export
    failure is caught, logged (in run()) and recorded on health, letting the caller
    retry on the next interval instead of tearing down the scheduler. (A signal-borne
    BaseException still propagates to the loop's KeyboardInterrupt backstop, as before.)"""
    if status:
        status.mark_running()
    try:
        result = run(config, stop)
        # None = cycle cancelled by shutdown; the caller breaks on stop.is_set()
        # right after, so an unfinished cycle is never marked success/degraded.
        if status and result is not None:
            if STATUS_EFFECTS[result.status].health_degraded:
                status.mark_degraded(result)
            else:
                status.mark_success(result)
    except Exception as err:  # pylint: disable=broad-except
        # log-and-continue: run() already logged the "Run summary [FAILED]" line and
        # fired the failure notification, so no duplicate error line here; the caller
        # still waits the interval before retrying (no busy-loop). Keep the traceback
        # and mark health failed.
        log.debug("Traceback:", exc_info=True)
        if status:
            status.mark_failed(err)


def _run_scheduled(config: ConfigNode, next_wait: Callable[[], float]) -> int:
    """Run the export on a repeating schedule until a stop signal is received."""
    stop = threading.Event()
    server = None
    try:
        _install_signal_handlers(stop)

        status = None
        if config.user_inputs.health_port:
            status = RunStatus()
            server = start_health_server(
                config.user_inputs.health_host, config.user_inputs.health_port, status)
            log.info("Health endpoint listening on %s:%s",
                     config.user_inputs.health_host, config.user_inputs.health_port)

        while not stop.is_set():
            _run_cycle(config, stop, status)
            if stop.is_set():
                break

            wait_secs = next_wait()
            if status:
                status.set_next_run(datetime.now(timezone.utc) + timedelta(seconds=wait_secs))
            log.info("Waiting %s seconds for next run", wait_secs)
            stop.wait(wait_secs)

        log.info("Shutdown complete")
        return 0
    except KeyboardInterrupt:
        # Backstop: a Ctrl-C landing before/while _install_signal_handlers runs
        # still raises normally; map it to the same 128+signum contract as
        # one-shot mode's backstop.
        log.info("Interrupted before graceful shutdown was armed; exiting")
        return 128 + signal.SIGINT
    finally:
        # Idempotent teardown on every exit path (normal, exception, backstop).
        if server is not None:
            server.shutdown()
            server.server_close()


def run(config: ConfigNode, stop: threading.Event | None = None) -> NotifyResult | None:
    """run export process with error handling and notification support"""
    try:
        result = exporter(config, stop)
        # Terminal outcome roll-up for the logs, independent of notifications:
        # WARNING for a degraded run so it is visible in scheduled mode (where the
        # process still exits 0 and per-cycle status otherwise only reaches /health).
        if result is not None:
            summary_level = (logging.WARNING if result.status is ExportStatus.PARTIAL
                             else logging.INFO)
            log.log(summary_level, "Run summary [%s]: %s",
                    result.status.name, format_run_summary(result))
        # None = cancelled by shutdown (run.py's shutdown-during-fetch /
        # shutdown-mid-cycle paths); notifying would report an outcome that
        # never happened, so skip notification entirely. Any real outcome
        # (including EMPTY) still notifies below.
        if result is not None and config.user_inputs.notifications:
            try:
                notif = NotifyHandler(config.user_inputs.notifications)
                notif.do_notify(result=result)
            except Exception as notif_err:  # pylint: disable=broad-exception-caught
                # log-and-continue: the export itself succeeded, a failed
                # notification must not downgrade or fail the run
                log.error("Failed to send notification: %s", str(notif_err))
        return result
    except Exception as run_err: # general catch all for notifications
        # Flatten newlines so a multi-line str(exception) stays one grep-able line,
        # matching format_run_summary's single-line guarantee; error= keeps the
        # payload field-shaped like the SUCCESS/PARTIAL/EMPTY summary lines.
        log.error("Run summary [FAILED]: error=%s",
                  str(run_err).replace("\r", " ").replace("\n", " "))
        if not config.user_inputs.notifications:
            raise run_err
        try:
            notif = NotifyHandler(config.user_inputs.notifications)
            notif.do_notify(run_err)
        except Exception as notif_err:  # pylint: disable=broad-exception-caught
            log.error("Failed to send notification: %s", str(notif_err))
        # raise original error instead of notification error
        raise run_err

def _run_local_cleanup(archive: Archiver) -> tuple[list[str], str | None]:
    """Prune local stale archives after upload. A failed delete is housekeeping, not
    a run failure -- caught here and downgraded to PARTIAL by the caller, same
    treatment as a remote retention failure in archiver._upload. Stale local files
    are harmless; the next run prunes them."""
    try:
        return archive.clean_up(), None
    except Exception as err:  # pylint: disable=broad-except
        log.error("Local cleanup failed (export and uploads succeeded): %s", err)
        return [], str(err) or "local cleanup failed"


def _warn_if_pruning_skipped(archive: Archiver) -> None:
    """Log once when this run's content loss disabled retention pruning everywhere
    (local and every remote target), but only when pruning was actually configured
    -- no point warning about a skip of an action that would never have run."""
    if not archive.prune_allowed and archive.retention_configured:
        log.warning(
            "Retention pruning skipped (local and all remote targets): this run "
            "is partial; set prune_on_partial: true to prune on partial runs")


def exporter(config: ConfigNode, stop: threading.Event | None = None) -> NotifyResult | None:
    """export bookstack nodes and archive locally and/or remotely"""

    #### Export Data #####
    # need to implement pagination for apis
    log.info("Beginning run")

    ## Helper functions with user provided (or defaults) http config
    http_client = HttpHelper(config.headers, config.user_inputs.http_config,
                             export_workers=config.user_inputs.export_workers)

    ## Build node filter from user config (None when no filters are configured)
    node_filter = NodeFilter(config.user_inputs.filters) if config.user_inputs.filters else None

    ## Use exporter class to get all the resources (pages, books, etc.) and their relationships
    log.info("Building shelve/book/chapter/page relationships")
    export_helper = NodeExporter(config.urls, http_client, node_filter=node_filter, stop=stop)
    ## shelves
    shelve_nodes: dict[int, Node] = export_helper.get_all_shelves()
    ## books (always needed - basis for all export levels)
    book_nodes: dict[int, Node] = export_helper.get_all_books(shelve_nodes,
                                                              config.unassigned_book_dir)

    ## Build archiver before the level branch (shared for all levels)
    archive: Archiver = Archiver(config, http_client)

    # Inject the cooperative-shutdown flag. Both modes pass a real Event now;
    # stop is None only when run()/exporter() are called directly (tests/library use).
    archive.set_stop(stop)

    # create export directory if not exists
    archive.create_export_dir()

    # Remove orphaned .tar/.tgz.incomplete from prior runs (SIGKILL backstop) before
    # this cycle writes anything.
    archive.sweep_orphans()

    ## Select nodes by export level
    export_level = config.user_inputs.export_level
    nodes: dict[int, Node]
    if export_level == "books":
        nodes = book_nodes
    elif export_level == "chapters":
        nodes = export_helper.get_chapter_nodes(book_nodes)
    else:
        # default: "pages"
        nodes = export_helper.get_all_pages(book_nodes)

    # A shutdown signal during the fetch above leaves the node tree truncated.
    # Skip the archive phase entirely rather than emit a partial export.
    if stop is not None and stop.is_set():
        log.info("Shutdown requested during fetch; skipping archive")
        return None

    if not nodes:
        log.warning(
            "No %s data available from given Bookstack instance. Nothing to archive",
            export_level,
        )
        return NotifyResult(status=ExportStatus.EMPTY, export_level=export_level)

    log.info("Beginning archive")
    try:
        # get all content for each node
        archive.get_bookstack_exports(nodes)

        # Graceful shutdown requested mid-cycle: drop the incomplete archive and skip
        # finalize/upload/cleanup so a cancelled cycle never produces an archive.
        if stop is not None and stop.is_set():
            log.info("Shutdown requested mid-cycle; discarding incomplete export")
            return None

        # Gate on DOCUMENT content, not the archive stream: assets/meta alone are not a
        # restorable backup. Failures recorded but zero node exports archived ->
        # hard failure, not Partial (Partial promises some of the backup
        # survived). Empty ledger + empty tar is a benign empty instance.
        if archive.failed_nodes or archive.failed_assets:
            if not archive.content_written:
                raise NoContentArchivedError(
                    f"no {export_level} content was archived: "
                    f"{len(archive.failed_nodes)} node export(s) and "
                    f"{len(archive.failed_assets)} asset download(s) failed")
        elif not archive.has_exported_content:
            log.warning("No %s content was archived. Nothing to upload", export_level)
            return NotifyResult(status=ExportStatus.EMPTY, export_level=export_level)

        # close the archive stream and publish the .tgz
        archive.create_archive()
        _warn_if_pruning_skipped(archive)

        # attempt every remote target, then derive status (raises only when no copy survives)
        outcomes = archive.archive_remote()
        status = archive.resolve_remote_status(outcomes)

        # any dropped content (node export or asset download) makes the archive
        # incomplete -- downgrade regardless of upload success
        if archive.failed_nodes or archive.failed_assets:
            status = ExportStatus.PARTIAL

        # Local retention pruning is housekeeping: at this point durable copies exist
        # (resolve_remote_status raised otherwise), so a failed local delete downgrades
        # the run to PARTIAL instead of failing it, rather than failing the whole run.
        removed, cleanup_error = _run_local_cleanup(archive)
        if cleanup_error:
            status = ExportStatus.PARTIAL

        log.info("Created file archive: %s", archive.archive_file)
        log.info("Completed run")
        return NotifyResult(status=status, local=archive.archive_file, uploads=outcomes,
                            removed=removed, cleanup_error=cleanup_error,
                            failed_nodes=archive.failed_nodes,
                            failed_assets=archive.failed_assets,
                            export_level=export_level)
    finally:
        # Eager cleanup of THIS cycle's incomplete archive on every terminal path
        # (stop, exception). No-op on success: the stream is already closed and
        # the .incomplete renamed away. The run-start sweep is the backstop for
        # SIGKILL, which kills the process before finally runs.
        archive.discard_incomplete()
