from typing import Dict, Union, List
import logging
from bookstack_file_exporter.common import util

log = logging.getLogger(__name__)

def get_json_response(url: str, headers: Dict[str, str]) -> List[Dict[str, Union[str,int]]]:
    """get http response data in json format"""
    response =  util.http_get_request(url=url, headers=headers)
    return response.json()

def get_all_ids(url: str, headers: Dict[str, str]) -> List[int]:
    """get all ids for a bookstack resource"""
    ids_api_meta = get_json_response(url=url, headers=headers)
    if ids_api_meta:
        return [item['id'] for item in ids_api_meta['data']]
    return []
