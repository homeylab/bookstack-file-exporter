from typing import List, Dict, Union
from pathlib import Path
import json

from bookstack_file_exporter.exporter.node import Node
from bookstack_file_exporter.archiver import util

_META_FILE_prefix = "meta_"

_EXPORT_API_PATH = "export"

_FILE_EXTENSION_MAP = {
    "markdown": ".md",
    "html": ".html",
    "pdf": ".pdf",
    "plaintext": ".txt"
}

class Archiver:
    def __init__(self, root_dir: str, add_meta: bool, base_page_url: str, headers: Dict[str, str]):
        self.root_dir = root_dir
        self.add_meta = add_meta
        self.base_page_url = base_page_url
        self.headers = headers
        # self.export_formats = export_formats
        self._export_map = {'local': self._archive_local, 'minio': self._archive_minio}
        self._minio_token = ""
        self._minio_id = ""
    
    # convert to bytes to be agnostic to end destination
    def archive(self, archive_type: str, page_node: Node, export_format: str):
        raw_data = self._get_data_format(page_node.meta['id'], export_format)
        # meta_data = self._get_meta(page_node)
        self._export_map[archive_type](page_node.file_path, raw_data, export_format)
        # if meta_data:
        # self._add_meta(page_node)
    
    def _archive_local(self, page_path: str, data: bytes, export_format: str):
        file_path = self._get_combined_path(page_path)
        file_full_name = f"{file_path}{_FILE_EXTENSION_MAP[export_format]}"
        self._write_bytes(file_path=file_full_name, data=data)
    
    def _archive_minio(self, page_node: Node):
        pass

    # convert page data to bytes
    def _get_data_format(self, page_node_id: int, export_format: str) -> bytes:
        url = self._get_export_url(node_id=page_node_id, export_format=export_format)
        return util.get_byte_response(url=url, headers=self.headers)

    def _get_meta(self, page_node: Node) -> Union[str, None]:
        if not self.add_meta:
            return
        return json.dumps(page_node.meta)

    def _tar_dir():
        pass

    def _get_combined_path(self, dir_name: str) -> str:
        return f"{self.root_dir}/{dir_name}"
    
    def _get_export_url(self, node_id: int, export_format: str) -> str:
        return f"{self.base_page_url}/{node_id}/{_EXPORT_API_PATH}/{export_format}"
        
    @staticmethod
    def _write_bytes(file_path: str, data: bytes):
        path_file = Path(file_path)
        # create parent directories as needed, ignore already exists errors
        path_file.parent.mkdir(parents=True, exist_ok=True)
        path_file.write_bytes(data)