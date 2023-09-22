from typing import Dict, Union
from pathlib import Path
import json
import os
import logging
import tarfile
import shutil

from bookstack_file_exporter.common import util

log = logging.getLogger(__name__)

def get_byte_response(url: str, headers: Dict[str, str]) -> bytes:
    response = util.http_get_request(url=url, headers=headers)
    return response.content

def write_bytes(file_path: str, data: bytes):
    path_file = Path(file_path)
    # create parent directories as needed, ignore already exists errors
    path_file.parent.mkdir(parents=True, exist_ok=True)
    path_file.write_bytes(data)

def dump_json(file_name: str, data: Dict[str, Union[str, int]]):
    with open(file_name, 'w') as fp:
        json.dump(data, fp, indent=4)

# set as function in case we want to do checks or final actions later
def remove_dir(dir_path: str):
    shutil.rmtree(dir_path)

def remove_file(file_path: str):
    os.remove(file_path)

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