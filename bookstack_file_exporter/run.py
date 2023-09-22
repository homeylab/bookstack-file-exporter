import argparse
import os
import logging
from time import sleep
from typing import Dict, Union, List

from bookstack_file_exporter.config_helper.config_helper import ConfigNode
from bookstack_file_exporter.exporter.node import Node
from bookstack_file_exporter.exporter.exporter import NodeExporter
from bookstack_file_exporter.archiver import util as archiver_util
from bookstack_file_exporter.archiver.archiver import Archiver

log = logging.getLogger(__name__)

def exporter(args: argparse.Namespace):
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

    ## Use exporter class to get all the resources (pages, books, etc.) and their relationships
    exportHelper = NodeExporter(api_urls, bookstack_headers)
    ## shelves
    shelve_nodes: Dict[int, Node] = exportHelper.get_shelf_nodes()
    ## books
    book_nodes: Dict[int, Node] = exportHelper.get_child_nodes("books", shelve_nodes)
    # books with no shelve assignment
    # default will be put in "unassigned" directory relative to backup dir
    # catch ValueError for Missing Response/Empty Data if no chapters exists
    try:
        books_no_shelf: Dict[int, Node] = exportHelper.get_unassigned_books(book_nodes, unassigned_dir)
    except ValueError:
        log.Info("No unassigned books found")
        books_no_shelf = {}

    # add new book nodes to map
    # these should not already be present in map
    # since we started with shelves first and then moved our way down.
    if books_no_shelf:
        for key, value in books_no_shelf.items():
            book_nodes[key] = value

    ## chapters (if exists)
    # chapter nodes are treated a little differently
    # are children under books
    try:
        chapter_nodes: Dict[int, Node] = exportHelper.get_chapter_nodes(book_nodes)
    except ValueError:
        log.Info("No chapter data was found")
        chapter_nodes = {}

    ## pages
    page_nodes: Dict[int, Node] = exportHelper.get_child_nodes("pages", book_nodes)
    # add chapter node pages
    # replace existing page node if found with proper chapter parent
    if chapter_nodes:
        page_chapter_nodes: Dict[int, Node] = exportHelper.get_child_nodes("pages", chapter_nodes)
        ## since we filter empty, check if there is any content
        ## add all chapter pages to existing page nodes
        if page_chapter_nodes:
            for key, value in page_chapter_nodes.items():
                page_nodes[key] = value
    
    ## start archive ##
    archive: Archiver = Archiver(base_export_dir, config.user_inputs.export_meta, page_base_url, bookstack_headers, config.object_storage_config)
    
    # create tar
    archive.archive(page_nodes, export_formats)
    
    # archive to remote targets
    archive.archive_remote(config.object_storage_config)

    archive.clean_up(config.user_inputs.clean_up)