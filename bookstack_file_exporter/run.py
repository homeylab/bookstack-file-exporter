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
from bookstack_file_exporter.notify.models import NotifyResult
from bookstack_file_exporter.health.status import RunStatus
from bookstack_file_exporter.health.server import start_health_server

log = logging.getLogger(__name__)


def entrypoint(args: argparse.Namespace) -> int:
    """Entrypoint for the export process. Returns an exit code."""
    try:
        config = ConfigNode(args)
    except Exception as err:  # pylint: disable=broad-except
        log.error("Configuration error: %s", err)
        log.debug("Traceback:", exc_info=True)
        return 1

    inputs = config.user_inputs
    if getattr(args, "run_once", False) or (not inputs.run_interval and not inputs.run_schedule):
        return _run_once(config)
    if inputs.run_schedule:
        return _run_scheduled(
            config, lambda: seconds_until_next_cron(inputs.run_schedule, datetime.now()))
    return _run_scheduled(config, lambda: inputs.run_interval)


def _run_once(config: ConfigNode) -> int:
    """Run the export exactly once and return an exit code."""
    try:
        run(config)
        return 0
    except KeyboardInterrupt:
        log.info("Interrupted, exiting")
        return 130
    except Exception as err:  # pylint: disable=broad-except
        log.error("Export failed: %s", err)
        log.debug("Traceback:", exc_info=True)
        return 1


def _run_scheduled(config: ConfigNode, next_wait: Callable[[], float]) -> int:
    """Run the export on a repeating schedule until a stop signal is received."""
    stop = threading.Event()

    def _handle_signal(signum, _frame):
        # Signal handlers run in the main thread between bytecodes, mid-anything;
        # raising across arbitrary code is unsafe and SIGTERM has no default
        # exception. So we only SET a flag (also breaks the interruptible
        # stop.wait() below); the export polls it at checkpoints to cancel.
        log.info("Received signal %s, shutting down (signal again to force)", signum)
        stop.set()
        # Restore the default disposition for BOTH catchable signals so that ANY
        # second signal — not only an identical repeat — force-kills via the
        # kernel with its conventional exit code (SIGINT->130, SIGTERM->143). This
        # is an operator escape hatch if a slow in-flight download won't drain
        # inside the grace window (e.g. `docker stop` then an impatient Ctrl-C).
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.signal(signal.SIGINT, signal.SIG_DFL)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    status = None
    server = None
    if config.user_inputs.health_port:
        status = RunStatus()
        server = start_health_server(
            config.user_inputs.health_host, config.user_inputs.health_port, status)
        log.info("Health endpoint listening on %s:%s",
                 config.user_inputs.health_host, config.user_inputs.health_port)

    while not stop.is_set():
        if status:
            status.mark_running()
        try:
            result = run(config, stop)
            if status:
                status.mark_success(result)
        except Exception as err:  # pylint: disable=broad-except
            # log-and-continue: a failed cycle still waits the interval below
            # before retrying (no busy-loop), and the failure notification has
            # already fired inside run().
            log.error("Export failed: %s", err)
            log.debug("Traceback:", exc_info=True)
            if status:
                status.mark_failed(err)

        if stop.is_set():
            break

        wait_secs = next_wait()
        if status:
            status.set_next_run(datetime.now(timezone.utc) + timedelta(seconds=wait_secs))
        log.info("Waiting %s seconds for next run", wait_secs)
        stop.wait(wait_secs)

    if server:
        server.shutdown()
    log.info("Shutdown complete")
    return 0


def run(config: ConfigNode, stop=None):
    """run export process with error handling and notification support"""
    try:
        result = exporter(config, stop)
        if config.user_inputs.notifications:
            notif = NotifyHandler(config.user_inputs.notifications)
            notif.do_notify(result=result)
        return result
    except Exception as run_err: # general catch all for notifications
        if not config.user_inputs.notifications:
            raise run_err
        try:
            notif = NotifyHandler(config.user_inputs.notifications)
            notif.do_notify(run_err)
        except Exception as notif_err:  # pylint: disable=broad-exception-caught
            log.error("Failed to send notification: %s", str(notif_err))
        # raise original error instead of notification error
        raise run_err

def exporter(config: ConfigNode, stop=None):
    """export bookstack nodes and archive locally and/or remotely"""

    #### Export Data #####
    # need to implement pagination for apis
    log.info("Beginning run")

    ## Helper functions with user provided (or defaults) http config
    http_client = HttpHelper(config.headers, config.user_inputs.http_config)

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

    # Inject the cooperative-shutdown flag (None in one-shot mode = no-op).
    archive.set_stop(stop)

    # create export directory if not exists
    archive.create_export_dir()

    # Remove orphaned .tar/.tgz.partial from prior runs (SIGKILL backstop) before
    # this cycle writes anything.
    archive.sweep_orphans()

    ## Select nodes by export level
    export_level = config.user_inputs.export_level
    if export_level == "books":
        nodes: dict[int, Node] = book_nodes
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
        return None

    log.info("Beginning archive")
    try:
        # get all content for each node
        archive.get_bookstack_exports(nodes)

        # Graceful shutdown requested mid-cycle: drop the partial tar and skip
        # gzip/upload/cleanup so a cancelled cycle never produces an archive.
        if stop is not None and stop.is_set():
            log.info("Shutdown requested mid-cycle; discarding partial export")
            return None

        # nothing was written to the tar (e.g. every node empty or all fetches failed):
        # skip gzip/upload/cleanup so we don't crash gzipping a non-existent tar.
        if not archive.has_exported_content:
            log.warning("No %s content was archived. Nothing to upload", export_level)
            return None

        # create tar if needed and gzip tar
        archive.create_archive()

        # archive to remote targets
        remote = archive.archive_remote()
        # if remote target is specified and clean is true
        # clean up the .tgz archive since it is already uploaded
        removed = archive.clean_up()

        local = archive.archive_file
        log.info("Created file archive: %s.tgz", archive.archive_dir)
        log.info("Completed run")
        return NotifyResult(local=local, remote=remote, removed=removed)
    finally:
        # Eager cleanup of THIS cycle's partial on every terminal path (stop,
        # exception, one-shot KeyboardInterrupt). No-op on success: the tar is
        # already consumed and the .partial renamed away. The run-start sweep is
        # the backstop for SIGKILL, which kills the process before finally runs.
        archive.discard_partial()
