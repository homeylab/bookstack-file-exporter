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

def get_all_shelves(url: str, headers: Dict[str, str]) -> List[int]:
    shelves_api_meta = get_json_response(url=url, headers=headers)
    all_shelves = [shelve['id'] for shelve in shelves_api_meta['data']]
    return all_shelves

def get_shelve_meta(url: str, headers: Dict[str, str], shelves: List[int]) -> Dict[int, Node]:
    shelve_nodes = {}
    for shelve_id in shelves:
        shelve_url = url + "/" + str(shelve_id)
        shelve_data = get_json_response(url=shelve_url, headers=headers)
        shelve_nodes[shelve_id] = Node(shelve_data)
    return shelve_nodes

def get_child_meta(url: str, headers: Dict[str, str], parent_nodes: Dict[int, Node]) -> Dict[int, Node]:
    child_nodes = {}
    for _, parent in parent_nodes.items():
        if parent.children:
            for child in parent.children:
                child_id = child['id']
                child_url = url + "/" + str(child_id)
                child_data = get_json_response(url=child_url, headers=headers)
                child_nodes[child_id] = Node(child_data, parent)
    return child_nodes

def generate_root_folder(destination: str) -> str:
    pass
