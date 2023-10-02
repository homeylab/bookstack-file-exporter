from typing import List, Dict, Union
from datetime import datetime
import logging

from bookstack_file_exporter.exporter.node import Node
from bookstack_file_exporter.archiver import util
from bookstack_file_exporter.archiver.minio_archiver import MinioArchiver
from bookstack_file_exporter.config_helper.remote import StorageProviderConfig

log = logging.getLogger(__name__)

_META_FILE_SUFFIX = "_meta.json"
_TAR_SUFFIX = ".tar"
_TAR_GZ_SUFFIX = ".tgz"

_EXPORT_API_PATH = "export"

_FILE_EXTENSION_MAP = {
    "markdown": ".md",
    "html": ".html",
    "pdf": ".pdf",
    "plaintext": ".txt",
    "meta": _META_FILE_SUFFIX,
    "tar": _TAR_SUFFIX,
    "tgz": _TAR_GZ_SUFFIX
}

_DATE_STR_FORMAT = "%Y-%m-%d_%H-%M-%S"

class Archiver:
    """
    Archiver pulls all the necessary files from upstream 
    and then pushes them to the specified backup location(s)

    Args:
        :root_dir: str (required) = the base directory for 
        which the archive .tgz will be placed.
        :add_meta: bool (required) = whether or not to add 
        metadata json files for each page, book, chapter, and/or shelve.
        :base_page_url: str (required) = the full url and path to get page content.
        :headers: Dict[str, str] (required) = the headers which include the Authorization to use

    Returns:
        Archiver instance with attributes that are 
        accessible for use for file level archival and backup.
    """
    def __init__(self, base_dir: str, add_meta: Union[bool, None],
                  base_page_url: str, headers: Dict[str, str]):
        self.base_dir = base_dir
        self.add_meta = add_meta
        self.base_page_url = base_page_url
        self._headers = headers
        self._root_dir = self.generate_root_folder(self.base_dir)
        # the tgz file will be name of
        # parent export directory, bookstack-<timestamp>, and .tgz extension
        self._archive_file = f"{self._root_dir}{_FILE_EXTENSION_MAP['tgz']}"
        # name of intermediate tar file before gzip
        self._tar_file = f"{self._root_dir}{_FILE_EXTENSION_MAP['tar']}"
        # name of the base folder to use within the tgz archive
        self._archive_base_path = self._root_dir.split("/")[-1]
        # remote_system to function mapping
        self._remote_exports = {'minio': self._archive_minio, 's3': self._archive_s3}

    # create local tarball first
    def archive(self, page_nodes: Dict[int, Node], export_formats: List[str]):
        """create a .tgz of all page content"""
        for _, page in page_nodes.items():
            for ex_format in export_formats:
                self._gather(page, ex_format)
        self._gzip_tar()

    # convert to bytes to be agnostic to end destination (future use case?)
    def _gather(self, page_node: Node, export_format: str):
        raw_data = self._get_data_format(page_node.id_, export_format)
        self._gather_local(page_node.file_path, raw_data, export_format, page_node.meta)

    def _gather_local(self, page_path: str, data: bytes,
                      export_format: str, meta_data: Union[bytes, None]):
        page_file_name = f"{self._archive_base_path}/" \
        f"{page_path}{_FILE_EXTENSION_MAP[export_format]}"
        util.write_bytes(self._tar_file, file_path=page_file_name, data=data)
        if self.add_meta:
            meta_file_name = f"{self._archive_base_path}/{page_path}{_FILE_EXTENSION_MAP['meta']}"
            bytes_meta = util.get_json_bytes(meta_data)
            util.write_bytes(self._tar_file, file_path=meta_file_name, data=bytes_meta)

    # send to remote systems
    def archive_remote(self, remote_targets: Dict[str, StorageProviderConfig]):
        """for each target, do their respective tasks"""
        if remote_targets:
            for key, value in remote_targets.items():
                self._remote_exports[key](value)

    def _gzip_tar(self):
        util.create_gzip(self._tar_file, self._archive_file)

    def _archive_minio(self, config: StorageProviderConfig):
        minio_archiver = MinioArchiver(config)
        minio_archiver.upload_backup(self._archive_file)

    def _archive_s3(self, config: StorageProviderConfig):
        pass

    def clean_up(self, clean_up_archive: Union[bool, None]):
        """remove archive after sending to remote target"""
        self._clean(clean_up_archive)

    def _clean(self, clean_up_archive: Union[bool, None]):
        # if user is uploading to object storage
        # delete the local .tgz archive since we have it there already
        if clean_up_archive:
            util.remove_file(self._archive_file)

    # convert page data to bytes
    def _get_data_format(self, page_node_id: int, export_format: str) -> bytes:
        url = self._get_export_url(node_id=page_node_id, export_format=export_format)
        return util.get_byte_response(url=url, headers=self._headers)

    def _get_export_url(self, node_id: int, export_format: str) -> str:
        return f"{self.base_page_url}/{node_id}/{_EXPORT_API_PATH}/{export_format}"

    @staticmethod
    def generate_root_folder(base_folder_name: str) -> str:
        """return base archive name"""
        return base_folder_name + "_" + datetime.now().strftime(_DATE_STR_FORMAT)
