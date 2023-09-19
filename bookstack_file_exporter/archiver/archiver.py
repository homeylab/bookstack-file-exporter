from typing import List, Dict, Union
from time import sleep
from datetime import datetime

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

_DATE_STR_FORMAT = "%Y-%m-%d_%H-%M-%S"

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
    def __init__(self, base_dir: str, add_meta: bool, base_page_url: str, headers: Dict[str, str]):
        self.base_dir = base_dir
        self.add_meta = add_meta
        self.base_page_url = base_page_url
        self.headers = headers
        # remote_system to function mapping
        self._remote_exports = {'minio': self._archive_minio, 's3': self._archive_s3}
        self._root_dir = self.generate_root_folder(self.base_dir)
        self._minio_token = ""
        self._minio_id = ""
    
    # create local tarball first
    def archive(self, page_nodes: Dict[int, Node], export_formats: List[str]):
        for _, page in page_nodes.items():
            for format in export_formats:
                # instead of sleep, implement back off retry in utils
                sleep(0.5)
                self._gather(page, format)
        self._tar_dir()
    
    # convert to bytes to be agnostic to end destination (future use case?)
    def _gather(self, page_node: Node, export_format: str):
        raw_data = self._get_data_format(page_node.id, export_format)
        self._gather_local(page_node.file_path, raw_data, export_format, page_node.meta)
    
    def _gather_local(self, page_path: str, data: bytes, export_format: str, meta_data: Union[bytes, None]):
        file_path = f"{self._root_dir}/{page_path}"
        file_full_name = f"{file_path}{_FILE_EXTENSION_MAP[export_format]}"
        util.write_bytes(file_path=file_full_name, data=data)
        if self.add_meta:
            meta_file_name = f"{file_path}{_FILE_EXTENSION_MAP['meta']}"
            util.dump_json(file_name=meta_file_name, data=meta_data)

    # send to remote systems
    def archive_remote(self, remote_targets: List[str]):
        if remote_targets:
            for target in remote_targets:
                self._remote_exports[target]()

    def _tar_dir(self):
        util.create_tar(self._root_dir, _FILE_EXTENSION_MAP['tar'])

    def _archive_minio(self):
        pass

    def _archive_s3(self):
        pass

    # convert page data to bytes
    def _get_data_format(self, page_node_id: int, export_format: str) -> bytes:
        url = self._get_export_url(node_id=page_node_id, export_format=export_format)
        return util.get_byte_response(url=url, headers=self.headers)
    
    def _get_export_url(self, node_id: int, export_format: str) -> str:
        return f"{self.base_page_url}/{node_id}/{_EXPORT_API_PATH}/{export_format}"
    
    @staticmethod
    def generate_root_folder(base_folder_name: str) -> str:
        return base_folder_name + "_" + datetime.now().strftime(_DATE_STR_FORMAT)