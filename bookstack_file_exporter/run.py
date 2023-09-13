import argparse
import os
import logging

from bookstack_file_exporter.config_helper.config_helper import ConfigNode
from bookstack_file_exporter.exporter import util
from bookstack_file_exporter.exporter.node import Node


log = logging.getLogger(__name__)

def test(args: argparse.Namespace, token_id_env: str, token_secret_env: str):
    config = ConfigNode(args)
    config.token_id= os.environ.get(token_id_env, "")
    config.token_secret = os.environ.get(token_secret_env, "")

    # log.info(config)
    # log.info(config.user_inputs)
    # log.info(config.headers)

    # log.info(config.urls)

    bookstack_headers = config.headers
    export_formats = config.user_inputs.formats

    ## urls
    shelve_base_url = config.urls['shelves']
    book_base_url = config.urls['books']
    page_base_url = config.urls['pages']
    

    ## shelves
    
    # all_shelves = []
    all_shelves: List[int] = util.get_all_shelves(url=shelve_base_url, headers=bookstack_headers)
    # get all the shelves and their ids from api
    # shelves_api_meta = util.get_json_response(url=config.urls['shelves'], headers=bookstack_headers)

    # # set all shelves and their simple metadata
    # for shelve in shelves_api_meta['data']:
    #     all_shelves.append(shelve['id'])


    # shelve_nodes = {}
    shelve_nodes: Dict[int, Node] = util.get_shelve_meta(url=shelve_base_url, headers=bookstack_headers, shelves=all_shelves)

    # for shelve_id in all_shelves:
    #     shelve_url = config.urls['shelves'] + "/" + str(shelve_id)
    #     shelve_data = util.get_json_response(url=shelve_url, headers=bookstack_headers)
    #     shelve_nodes[shelve_id] = node.Node(shelve_data)
    
    ## books
    # get all books assigned to a shelve
    # book_nodes = {}
    book_nodes: Dict[int, Node] = util.get_child_meta(url=book_base_url, headers=bookstack_headers, parent_nodes=shelve_nodes)

    # for _, shelve in shelve_nodes.items():
    #     if shelve.children:
    #         for child in shelve.children:
    #             child_id = child['id']
    #             book_url = config.urls['books'] + "/" + str(child_id)
    #             book_data = util.get_json_response(url=book_url, headers=bookstack_headers)
    #             book_nodes[child_id] = node.Node(book_data, shelve)
    
    # for key, book in book_nodes.items():
    #     print(book.children)
    
    ## pages
    # get all pages assigned to a book
    # page_nodes = {}
    page_nodes = util.get_child_meta(url=page_base_url, headers=bookstack_headers, parent_nodes=book_nodes)

    # for _, book in book_nodes.items():
    #     if book.children:
    #         for child in book.children:
    #             child_id = child['id']
    #             page_url = config.urls['pages'] + "/" + str(child_id)
    #             page_data = util.get_json_response(url=page_url, headers=bookstack_headers)
    #             page_nodes[child_id] = node.Node(page_data, book)


    for key, page in page_nodes.items():
        # print(page.meta)
        print(page.file_path)



    