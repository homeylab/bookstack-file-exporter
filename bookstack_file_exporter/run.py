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
    export_formats = config.user_inputs.formats
    unassigned_dir = config.unassigned_book_dir
    page_base_url = config.urls['pages']
    base_export_dir = config.base_dir_name

    #### Export Data #####
    # need to implement pagination for apis
    log.info("Beginning export")

    ## Use exporter class to get all the resources (pages, books, etc.) and their relationships
    export_helper = NodeExporter(api_urls, bookstack_headers)
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
    archive: Archiver = Archiver(base_export_dir, config.user_inputs.export_meta,
                                 page_base_url, bookstack_headers)
    # create tar
    archive.archive(page_nodes, export_formats)
    # archive to remote targets
    archive.archive_remote(config.object_storage_config)
    # if remote target is specified and clean is true
    # clean up the .tgz archive since it is already uploaded
    archive.clean_up(config.user_inputs.clean_up)

    log.info("Completed run")
