from typing import List, Dict, Union
from pathlib import Path
import json

from bookstack_file_exporter.exporter.node import Node
from bookstack_file_exporter.archiver import util

_META_FILE_SUFFIX = "_meta"
_TAR_GZ_SUFFIX = ".tgz"

_EXPORT_API_PATH = "export"

_FILE_EXTENSION_MAP = {
    "markdown": ".md",
    "html": ".html",
    "pdf": ".pdf",
    "plaintext": ".txt",
    "meta": f"{_META_FILE_SUFFIX}.json",
    "tar": _TAR_GZ_SUFFIX
}

class Archiver:
    """
    Archiver pulls all the necessary files from upstream and then pushes them to the specified backup location(s)

    Args:
        root_dir: str (required) = the base directory for which the files will be placed .
        add_meta: bool (required) = whether or not to add metadata json files for each page, book, chapter, and/or shelve.
        base_page_url: str (required) = the full url and path to get page content.
        headers: Dict[str, str] (required) = the headers which include the Authorization to use

    Returns:
        Archiver instance with attributes that are accessible for use for file level archival and backup.
    """
    def __init__(self, root_dir: str, add_meta: bool, base_page_url: str, headers: Dict[str, str]):
        self.root_dir = root_dir
        self.add_meta = add_meta
        self.base_page_url = base_page_url
        self.headers = headers
        # remote_system to function mapping
        self._remote_exports = {'minio': self._archive_minio, 's3': self._archive_s3}
        # self._tar_file = ""
        self._minio_token = ""
        self._minio_id = ""
    
    # create local tarball first
    # convert to bytes to be agnostic to end destination (future use case?)
    def gather(self, page_node: Node, export_format: str):
        raw_data = self._get_data_format(page_node.id, export_format)
        self._gather_local(page_node.file_path, raw_data, export_format, page_node.meta)
        
    def archive(self):
        self._tar_dir()
        
    # send to remote systems
    def archive_remote(self, remote_dest: str):
        self._remote_exports[remote_dest]()
    
    def _gather_local(self, page_path: str, data: bytes, export_format: str, meta_data: Union[bytes, None]):
        file_path = self._get_combined_path(page_path)
        file_full_name = f"{file_path}{_FILE_EXTENSION_MAP[export_format]}"
        util.write_bytes(file_path=file_full_name, data=data)
        if self.add_meta:
            meta_file_name = f"{file_path}{_FILE_EXTENSION_MAP['meta']}"
            util.dump_json(file_name=meta_file_name, data=meta_data)

    def _tar_dir(self):
        # tar_path = f"{self.root_dir}{_FILE_EXTENSION_MAP['tar']}"
        util.create_tar(self.root_dir, _FILE_EXTENSION_MAP['tar'])

    def _archive_minio(self):
        pass

    def _archive_s3(self):
        pass

    # convert page data to bytes
    def _get_data_format(self, page_node_id: int, export_format: str) -> bytes:
        url = self._get_export_url(node_id=page_node_id, export_format=export_format)
        return util.get_byte_response(url=url, headers=self.headers)

    def _get_combined_path(self, dir_name: str) -> str:
        return f"{self.root_dir}/{dir_name}"
    
    def _get_export_url(self, node_id: int, export_format: str) -> str:
        return f"{self.base_page_url}/{node_id}/{_EXPORT_API_PATH}/{export_format}"