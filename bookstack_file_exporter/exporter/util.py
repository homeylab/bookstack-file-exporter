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
    if ids_api_meta:
        return [item['id'] for item in ids_api_meta['data']]
    else:
        return []


