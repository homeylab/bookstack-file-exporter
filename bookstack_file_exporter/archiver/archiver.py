from typing import List, Dict, Union
from datetime import datetime
import logging
import os

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

# pylint: disable=too-many-instance-attributes

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
        minio_archiver.clean_up(config.keep_last, _FILE_EXTENSION_MAP['tgz'])

    def _archive_s3(self, config: StorageProviderConfig):
        pass

    def clean_up(self, keep_last: Union[int, None]):
        """remove archive after sending to remote target"""
        # this captures keep_last = 0
        if not keep_last:
            return
        to_delete = self._get_stale_archives(keep_last)
        if to_delete:
            self._delete_files(to_delete)

    def _get_stale_archives(self, keep_last: int) -> List[str]:
        # if user is uploading to object storage
        # delete the local .tgz archive since we have it there already
        archive_list: List[str] = util.scan_archives(self.base_dir, _FILE_EXTENSION_MAP['tgz'])
        if not archive_list:
            log.debug("No archive files found to clean up")
            return []
        # if negative number, we remove all local archives
        # assume user is using remote storage and will upload there
        if keep_last < 0:
            log.debug("Local archive files will be deleted, keep_last: -1")
            return archive_list
        # keep_last > 0 condition
        to_delete = []
        if len(archive_list) > keep_last:
            log.debug("Number of archives is greater than 'keep_last'")
            log.debug("Running clean up of local archives")
            to_delete = self._filter_archives(keep_last, archive_list)
        return to_delete

    def _filter_archives(self, keep_last: int, file_list: List[str]) -> List[str]:
        """get older archives based on keep number"""
        file_dict = {}
        for file in file_list:
            file_dict[file] = os.stat(file).st_ctime
        # order dict by creation time
        # ascending order
        ordered_dict = dict(sorted(file_dict.items(), key=lambda item: item[1]))
        # ordered_dict = {k: v for k, v in sorted(file_dict.items(),
        #                                         key=lambda item: item[1])}

        files_to_clean = []
        # how many items we will have to delete to fulfill keep_last
        to_delete = len(ordered_dict) - keep_last
        for key in ordered_dict:
            files_to_clean.append(key)
            to_delete -= 1
            if to_delete <= 0:
                break
        log.debug("%d local archives will be cleaned up", len(files_to_clean))
        return files_to_clean

    def _delete_files(self, file_list: List[str]):
        for file in file_list:
            util.remove_file(file)

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
