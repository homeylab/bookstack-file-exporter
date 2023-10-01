from typing import Dict, Union
from pathlib import Path
import json
import os
import logging
import tarfile
import shutil
from io import BytesIO
import gzip

from bookstack_file_exporter.common import util

log = logging.getLogger(__name__)

def get_byte_response(url: str, headers: Dict[str, str]) -> bytes:
    """get byte response from http request"""
    response = util.http_get_request(url=url, headers=headers)
    return response.content

# def write_bytes(file_path: str, data: bytes):
#     """write byte data to file"""
#     path_file = Path(file_path)
#     # create parent directories as needed, ignore already exists errors
#     path_file.parent.mkdir(parents=True, exist_ok=True)
#     path_file.write_bytes(data)

def write_bytes(base_tar_dir: str, file_path: str, data: bytes):
    """write byte data to file"""
    log.info("Opening tar file: %s", base_tar_dir)
    with tarfile.open(base_tar_dir, "a") as tar:
        data_obj = BytesIO(data)
        tar_info = tarfile.TarInfo(name=file_path)
        tar_info.size = data_obj.getbuffer().nbytes
        log.info(tar_info)
        log.info(tar_info.size)
        tar.addfile(tar_info, fileobj=data_obj)

def dump_json(file_name: str, data: Dict[str, Union[str, int]]):
    """dump dict to json file"""
    with open(file_name, 'w', encoding="utf-8") as fp:
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

def create_gzip(tar_file: str, gzip_file: str):
    with open(tar_file, 'rb') as f_in:
        with gzip.open(gzip_file, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    remove_file(tar_file)