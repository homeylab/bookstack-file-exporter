import argparse
import sys
import logging
import time
from typing import Dict

from bookstack_file_exporter.config_helper.config_helper import ConfigNode
from bookstack_file_exporter.exporter.node import Node
from bookstack_file_exporter.exporter.exporter import NodeExporter
from bookstack_file_exporter.archiver.archiver import Archiver
from bookstack_file_exporter.common.util import HttpHelper

log = logging.getLogger(__name__)

def entrypoint(args: argparse.Namespace):
    """entrypoint for export process"""
    # get configuration from helper
    config = ConfigNode(args)
    if config.user_inputs.run_interval:
        while True:
            exporter(config)
            log.info("Waiting %s seconds for next run", config.user_inputs.run_interval)
            # sleep process state
            time.sleep(config.user_inputs.run_interval)
    exporter(config)

def exporter(config: ConfigNode):
    """export bookstack nodes and archive locally and/or remotely"""

    #### Export Data #####
    # need to implement pagination for apis
    log.info("Beginning run")

    ## Helper functions with user provided (or defaults) http config
    http_client = HttpHelper(config.headers, config.user_inputs.http_config)

    ## Use exporter class to get all the resources (pages, books, etc.) and their relationships
    log.info("Building shelve/book/chapter/page relationships")
    export_helper = NodeExporter(config.urls, http_client)
    ## shelves
    shelve_nodes: Dict[int, Node] = export_helper.get_all_shelves()
    ## books
    book_nodes: Dict[int, Node] = export_helper.get_all_books(shelve_nodes,
                                                              config.unassigned_book_dir)
    ## pages
    page_nodes: Dict[int, Node] = export_helper.get_all_pages(book_nodes)
    if not page_nodes:
        log.warning("No page data available from given Bookstack instance. Nothing to archive")
        sys.exit(0)
    log.info("Beginning archive")
    ## start archive ##
    archive: Archiver = Archiver(config, http_client)

    # create export directory if not exists
    archive.create_export_dir()

    # get all page content for each page
    archive.get_bookstack_exports(page_nodes)

    # create tar if needed and gzip tar
    archive.create_archive()

    # archive to remote targets
    archive.archive_remote()
    # if remote target is specified and clean is true
    # clean up the .tgz archive since it is already uploaded
    archive.clean_up()

    log.info("Created file archive: %s.tgz", archive.archive_dir)
    log.info("Completed run")
