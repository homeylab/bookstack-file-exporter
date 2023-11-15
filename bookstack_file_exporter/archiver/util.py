from typing import Dict, Union, List
import json
import os
import logging
import tarfile
import shutil
from io import BytesIO
import gzip
import glob
import re

from bookstack_file_exporter.common import util

log = logging.getLogger(__name__)

def get_byte_response(url: str, headers: Dict[str, str]) -> bytes:
    """get byte response from http request"""
    response = util.http_get_request(url=url, headers=headers)
    return response.content

# def create_dir(dir_name: str):
#     """create a dir if not exists"""
#     if not os.path.exists(dir_name):
#         os.mkdir(dir_name)

# append to a tar file instead of creating files locally and then tar'ing after
def write_tar(base_tar_dir: str, file_path: str, data: bytes):
    """append byte data to tar file"""
    with tarfile.open(base_tar_dir, "a") as tar:
        data_obj = BytesIO(data)
        tar_info = tarfile.TarInfo(name=file_path)
        tar_info.size = data_obj.getbuffer().nbytes
        log.debug("Adding file: %s with size: %d bytes to tar file", tar_info.name, tar_info.size)
        tar.addfile(tar_info, fileobj=data_obj)

# create files first for manipulation/changes and tar later
def write_file(file_path: str, data: bytes):
    """write byte data to a local file"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'wb') as file_obj:
        file_obj.write(data)

def write_bytes(base_tar_dir: str, file_path: str, data: bytes):
    """append byte data to tar file"""
    with tarfile.open(base_tar_dir, "a") as tar:
        data_obj = BytesIO(data)
        tar_info = tarfile.TarInfo(name=file_path)
        tar_info.size = data_obj.getbuffer().nbytes
        log.debug("Adding file: %s with size: %d bytes to tar file", tar_info.name, tar_info.size)
        tar.addfile(tar_info, fileobj=data_obj)

def get_json_bytes(data: Dict[str, Union[str, int]]) -> bytes:
    """dump dict to json file"""
    return json.dumps(data, indent=4).encode('utf-8')

# set as function in case we want to do checks or final actions later
def remove_file(file_path: str):
    """remove a file"""
    os.remove(file_path)

def create_gzip(file_path: str, gzip_file: str, remove_old: bool = True):
    """create a gzip of an existing file/dir and remove it"""
    with open(file_path, 'rb') as f_in:
        with gzip.open(gzip_file, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    if remove_old:
        remove_file(file_path)

def scan_archives(base_dir: str, extension: str) -> str:
    """scan export directory for archives"""
    file_pattern = f"{base_dir}_*{extension}"
    return glob.glob(file_pattern)

def find_file_matches(file_path: str, regex_expr: re.Pattern) -> List[str]:
    """find all matching lines for regex pattern"""
    matches=[]
    with open(file_path, encoding="utf-8") as open_file:
        for line in open_file:
            for match in re.finditer(regex_expr, line):
                matches.append(match.group)
    return matches
