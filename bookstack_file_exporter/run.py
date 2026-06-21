import argparse
import logging
import signal
import threading

from bookstack_file_exporter.config_helper.config_helper import ConfigNode
from bookstack_file_exporter.exporter.node import Node
from bookstack_file_exporter.exporter.exporter import NodeExporter
from bookstack_file_exporter.exporter.filter import NodeFilter
from bookstack_file_exporter.archiver.archiver import Archiver
from bookstack_file_exporter.common.util import HttpHelper
from bookstack_file_exporter.notify.handler import NotifyHandler
from bookstack_file_exporter.notify.models import NotifyResult

log = logging.getLogger(__name__)


def entrypoint(args: argparse.Namespace) -> int:
    """Entrypoint for the export process. Returns an exit code."""
    try:
        config = ConfigNode(args)
    except Exception as err:  # pylint: disable=broad-except
        log.error("Configuration error: %s", err)
        log.debug("Traceback:", exc_info=True)
        return 1

    if getattr(args, "run_once", False) or not config.user_inputs.run_interval:
        return _run_once(config)
    return _run_scheduled(config)


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


def _run_scheduled(config: ConfigNode) -> int:
    """Run the export on a repeating interval until a stop signal is received."""
    stop = threading.Event()
    interval = config.user_inputs.run_interval

    def _handle_signal(signum, _frame):
        log.info("Received signal %s, shutting down", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    while not stop.is_set():
        try:
            run(config)
        except Exception as err:  # pylint: disable=broad-except
            # log-and-continue: a failed cycle still waits the interval below
            # before retrying (no busy-loop), and the failure notification has
            # already fired inside run().
            log.error("Export failed: %s", err)
            log.debug("Traceback:", exc_info=True)

        if stop.is_set():
            break

        log.info("Waiting %s seconds for next run", interval)
        stop.wait(interval)

    log.info("Shutdown complete")
    return 0


def run(config: ConfigNode):
    """run export process with error handling and notification support"""
    try:
        result = exporter(config)
        if config.user_inputs.notifications:
            notif = NotifyHandler(config.user_inputs.notifications)
            notif.do_notify(result=result)
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

def exporter(config: ConfigNode):
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
    export_helper = NodeExporter(config.urls, http_client, node_filter=node_filter)
    ## shelves
    shelve_nodes: dict[int, Node] = export_helper.get_all_shelves()
    ## books (always needed - basis for all export levels)
    book_nodes: dict[int, Node] = export_helper.get_all_books(shelve_nodes,
                                                              config.unassigned_book_dir)

    ## Build archiver before the level branch (shared for all levels)
    archive: Archiver = Archiver(config, http_client)

    # create export directory if not exists
    archive.create_export_dir()

    ## Select nodes by export level
    export_level = config.user_inputs.export_level
    if export_level == "books":
        nodes: dict[int, Node] = book_nodes
    elif export_level == "chapters":
        nodes = export_helper.get_chapter_nodes(book_nodes)
    else:
        # default: "pages"
        nodes = export_helper.get_all_pages(book_nodes)

    if not nodes:
        log.warning(
            "No %s data available from given Bookstack instance. Nothing to archive",
            export_level,
        )
        return None

    log.info("Beginning archive")
    # get all content for each node
    archive.get_bookstack_exports(nodes)
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
