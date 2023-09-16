from typing import Dict, List, Union
from datetime import datetime
import json
import requests
import logging

log = logging.getLogger(__name__)

def generate_root_folder(base_folder_name: str) -> str:
    return base_folder_name + "_" + datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    pass

def get_byte_response(url: str, headers: Dict[str, str]) -> bytes:
    try:
        response = requests.get(url=url, headers=headers)
        response.raise_for_status()
    except Exception as req_err:
        log.error(f"Failed to make request for {url}")
        raise req_err
    return response.content

def get_json_format(data: Dict[str, Union[str, int]]) -> str:
    return json.dumps(data)

def dump_json(file_name: str, data: Dict[str, Union[str, int]]):
    dump_file = file_name + '.json'
    json.dumps
    with open(dump_file, 'w') as fp:
        json.dump(data, fp)
    pass