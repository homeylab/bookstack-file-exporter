from typing import Dict, Union, List
from bookstack_file_exporter.exporter.node import Node
import requests
import logging

log = logging.getLogger(__name__)

def get_json_response(url: str, headers: Dict[str, str], verify: bool = True, timeout: int = 30) -> List[Dict[str, Union[str,int]]]:
    try:
        resp = requests.get(url=url, headers=headers, verify=verify, timeout=timeout)
        resp.raise_for_status()
    except Exception as req_err:
        # log which request failed for easier reading
        log.error(f"Failed to make request for {url}")
        raise req_err
    return resp.json()

def get_all_ids(url: str, headers: Dict[str, str]) -> List[int]:
    ids_api_meta = get_json_response(url=url, headers=headers)
    all_ids = [item['id'] for item in ids_api_meta['data']]
    return all_ids

def get_parent_meta(url: str, headers: Dict[str, str], parent_ids: List[int],
                     path_prefix: Union[str, None] = None) -> Dict[int, Node]:
    parent_nodes = {}
    for parent_id in parent_ids:
        parent_url = f"{url}/{parent_id}"
        # parent_url = url + "/" + str(parent_id)
        parent_data = get_json_response(url=parent_url, headers=headers)
        parent_nodes[parent_id] = Node(parent_data, path_prefix=path_prefix)
    return parent_nodes

def get_chapter_meta(url: str, headers: Dict[str, str], chapters: List[int],
                     books:Dict[int, Node], path_prefix: Union[str, None] = None) -> Dict[int, Node]:
    chapter_nodes = {}
    for chapter_id in chapters:
        chapter_url = f"{url}/{chapter_id}"
        # chapter_url = url + "/" + str(chapter_id)
        chapter_data = get_json_response(url=chapter_url, headers=headers)
        book_id = chapter_data['book_id']
        chapter_nodes[chapter_id] = Node(chapter_data, books[book_id], path_prefix=path_prefix)
    return chapter_nodes

def get_child_meta(url: str, headers: Dict[str, str], parent_nodes: Dict[int, Node],
                    filter_empty: bool = False, path_prefix: Union[str, None] = None) -> Dict[int, Node]:
    child_nodes = {}
    for _, parent in parent_nodes.items():
        if parent.children:
            for child in parent.children:
                child_id = child['id']
                child_url = f"{url}/{child_id}"
                # child_url = url + "/" + str(child_id)
                child_data = get_json_response(url=child_url, headers=headers)
                child_node = Node(child_data, parent, path_prefix=path_prefix)
                if filter_empty:
                    if not child_node.empty:
                        child_nodes[child_id] = child_node
                else:
                    child_nodes[child_id] = child_node
    return child_nodes

def get_page_export(url: str, headers: Dict[str, str]):
    pass


