import argparse
import os
import logging
from typing import Dict, Union, List

from bookstack_file_exporter.config_helper.config_helper import ConfigNode
from bookstack_file_exporter.exporter import util
from bookstack_file_exporter.exporter.node import Node


log = logging.getLogger(__name__)

def test(args: argparse.Namespace, token_id_env: str, token_secret_env: str):
    config = ConfigNode(args)
    config.token_id= os.environ.get(token_id_env, "")
    config.token_secret = os.environ.get(token_secret_env, "")

    bookstack_headers = config.headers
    export_formats = config.user_inputs.formats

    ## urls
    shelve_base_url = config.urls['shelves']
    book_base_url = config.urls['books']
    page_base_url = config.urls['pages']
    

    ## shelves
    all_shelves: List[int] = util.get_all_shelves(url=shelve_base_url, headers=bookstack_headers)
    shelve_nodes: Dict[int, Node] = util.get_shelve_meta(url=shelve_base_url,
                                                          headers=bookstack_headers, shelves=all_shelves)
    
    ## books
    book_nodes: Dict[int, Node] = util.get_child_meta(url=book_base_url, headers=bookstack_headers, parent_nodes=shelve_nodes)
    
    ## pages
    page_nodes = util.get_child_meta(url=page_base_url, headers=bookstack_headers, parent_nodes=book_nodes)


    # for key, page in page_nodes.items():
    #     # print(page.meta)
    #     print(page.file_path)



    