import argparse
import sys
import logging
from typing import Dict

from bookstack_file_exporter.config_helper.config_helper import ConfigNode
from bookstack_file_exporter.exporter.node import Node
from bookstack_file_exporter.exporter.exporter import NodeExporter
from bookstack_file_exporter.archiver.archiver import Archiver

log = logging.getLogger(__name__)

def exporter(args: argparse.Namespace):
    """export bookstack nodes and archive locally and/or remotely"""
    ## get configuration from helper
    config = ConfigNode(args)

    ## convenience vars
    bookstack_headers = config.headers
    api_urls = config.urls
    unassigned_dir = config.unassigned_book_dir
    verify_ssl = config.user_inputs.assets.verify_ssl

    #### Export Data #####
    # need to implement pagination for apis
    log.info("Beginning run")

    ## Use exporter class to get all the resources (pages, books, etc.) and their relationships
    log.info("Building shelve/book/chapter/page relationships")
    export_helper = NodeExporter(api_urls, bookstack_headers, verify_ssl)
    ## shelves
    shelve_nodes: Dict[int, Node] = export_helper.get_all_shelves()
    ## books
    book_nodes: Dict[int, Node] = export_helper.get_all_books(shelve_nodes, unassigned_dir)
    ## pages
    page_nodes: Dict[int, Node] = export_helper.get_all_pages(book_nodes)
    if not page_nodes:
        log.warning("No page data available from given Bookstack instance. Nothing to archive")
        sys.exit(0)
    log.info("Beginning archive")
    ## start archive ##
    archive: Archiver = Archiver(config)

    # get all page content for each page
    archive.get_bookstack_exports(page_nodes)

    # create tar if needed and gzip tar
    archive.create_archive()

    # archive to remote targets
    archive.archive_remote()
    # if remote target is specified and clean is true
    # clean up the .tgz archive since it is already uploaded
    archive.clean_up()

    log.info("Completed run")
