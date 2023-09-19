from typing import Dict, List, Union
from datetime import datetime
from pathlib import Path
import json
import requests
import os
import logging
import tarfile


log = logging.getLogger(__name__)

def get_byte_response(url: str, headers: Dict[str, str]) -> bytes:
    try:
        response = requests.get(url=url, headers=headers)
        response.raise_for_status()
    except Exception as req_err:
        log.error(f"Failed to make request for {url}")
        raise req_err
    return response.content

def get_json_format(data: Dict[str, Union[str, int]]) -> bytes:
    # return json.dumps(data).encode('utf-8')
    return json.dumps()

def write_bytes(file_path: str, data: bytes):
    path_file = Path(file_path)
    # create parent directories as needed, ignore already exists errors
    path_file.parent.mkdir(parents=True, exist_ok=True)
    path_file.write_bytes(data)

def dump_json(file_name: str, data: Dict[str, Union[str, int]]):
    with open(file_name, 'w') as fp:
        json.dump(data, fp, indent=4)

def create_tar(export_path: str, file_extension: str):
    # path of the export dir
    output_path = Path(export_path)
    # create tar in parent of export dir
    # get abs path of parent
    parent_path = output_path.parent
    parent_abs_path = parent_path.resolve()
    # set tar file path
    tar_path = f"{export_path}{file_extension}"
    # create tar file
    with tarfile.open(tar_path, "w:gz") as tar:
        # add export directory to dump
        tar.add(str(parent_abs_path), arcname='.')