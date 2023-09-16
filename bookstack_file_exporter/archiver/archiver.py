from typing import List, Dict

from bookstack_file_exporter.exporter.node import Node

class Archiver:
    def __init__(self, root_dir: str, export_formats: List[str]):
        self.root_dir = root_dir
        self.export_formats = export_formats
        self._minio_token = ""
        self._minio_id = ""
        self._initialize()

    def _initialize(self):
        if 'minio' in self.export_formats:
            # check for env vars
            pass
        self._create_dir(self.root_dir)
    
    def archive(bookstack_node: Node):
        pass

    def _archive_local(bookstack_node: Node):
        pass

    @staticmethod
    def _create_dir(dir_name: str):
        pass

        

        
