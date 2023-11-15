from typing import List, Dict, Union
from datetime import datetime
import logging
import os

from bookstack_file_exporter.exporter.node import Node
from bookstack_file_exporter.archiver import util
from bookstack_file_exporter.archiver.assets_archiver import AssetsArchiver
from bookstack_file_exporter.archiver.minio_archiver import MinioArchiver
from bookstack_file_exporter.config_helper.remote import StorageProviderConfig
from bookstack_file_exporter.config_helper.models import UserInput

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
        :urls: str (required) = the full urls and paths to get content.
        :headers: Dict[str, str] (required) = the headers which include the Authorization to use
        :md_asset_options: MarkdownAssets (optional) = additional options to configure 
        image/attachment exports for markdown files.

    Returns:
        Archiver instance with attributes that are 
        accessible for use for file level archival and backup.
    """
    def __init__(self, base_dir: str, urls: Dict[str, str],
                 headers: Dict[str, str], user_input: UserInput):
        self.base_dir = base_dir
        self.api_urls = urls
        self._asset_archiver = AssetsArchiver(user_input.assets, user_input.formats)
        self._headers = headers
        self._root_dir = self._generate_root_folder(self.base_dir)
        # the tgz file will be name of
        # parent export directory, bookstack-<timestamp>, and .tgz extension
        self._archive_file = f"{self._root_dir}{_FILE_EXTENSION_MAP['tgz']}"
        # name of intermediate tar file before gzip
        self._tar_file = f"{self._root_dir}{_FILE_EXTENSION_MAP['tar']}"
        # name of the base folder to use within the tgz archive (internal tar layout)
        self._archive_base_path = self._root_dir.split("/")[-1]
        # remote_system to function mapping
        self._remote_exports = {'minio': self._archive_minio, 's3': self._archive_s3}

    # create local tarball first
    def get_bookstack_files(self, page_nodes: Dict[int, Node], export_formats: List[str],
                add_meta: Union[bool, None]):
        """pull all bookstack pages into local files/tar"""
        log.info("Exporting all bookstack page contents")
        for _, page in page_nodes.items():
            for ex_format in export_formats:
                self._gather(page, ex_format)
                if add_meta:
                    self._gather_meta(page.file_path, page.meta)
                # self._gather_images(page.file_path, ex_format)
        # self._gzip_tar()

    def get_bookstack_images(self, page_nodes: Dict[int, Node]):
        """export images on pages if specified by user"""
        if not self._asset_archiver.export_images:
            log.debug("skipping image export based on user input")
            return
        image_page_meta = self._asset_archiver.get_image_meta(self._headers, self.api_urls['images'])
        if not image_page_meta:
            log.debug("skipping image export - no data returned from image meta")
            return
        log.info("Exporting all bookstack page images")
        for _, page in page_nodes.items():
            self._gather_images(page.file_path)
        self._get_markdown_assets()

    def _get_markdown_assets(self, page_nodes: Dict[int, Node], image_page_meta: Dict[int, List[str]]):
        if not self._asset_archiver.modify_md:
            return
        # for _, page in page_nodes.items():

    def create_archive(self):
        # check if tar needs to be created first
        self._gzip_tar()

    # convert to bytes to be agnostic to end destination (future use case?)
    def _gather(self, page_node: Node, export_format: str):
        raw_data = self._get_data_format(page_node.id_, export_format)
        self._gather_local(page_node.file_path, raw_data, export_format)

    def _gather_local(self, page_path: str, data: bytes,
                      export_format: str):
        page_file_name = f"{self._archive_base_path}/" \
        f"{page_path}{_FILE_EXTENSION_MAP[export_format]}"
        self._write_data(file_path=page_file_name, data=data)

    def _gather_meta(self, page_path: str, meta_data: Dict[str, Union[str, int]]):
        meta_file_name = f"{self._archive_base_path}/{page_path}{_FILE_EXTENSION_MAP['meta']}"
        bytes_meta = util.get_json_bytes(meta_data)
        self._write_data(file_path=meta_file_name, data=bytes_meta)

    def _gather_images(self, page_path: str):
        return
        # page_file_name = f"{self._archive_base_path}/" \
        # f"{page_path}{_FILE_EXTENSION_MAP['markdown']}"
        # page_image_dir = f"{self._archive_base_path}/{page_path}{_IMAGE_DIR_SUFFIX}"
        # util.create_dir(page_image_dir)

    def _update_image_links(self, page_path: str):
        pass

    def _write_data(self, file_path: str, data: bytes):
        # if we don't have to modify markdown files for image export links
        # we can go just create a tar file directly and append to it
        if not self._asset_archiver.modify_md:
            util.write_tar(self._tar_file, file_path=file_path, data=data)


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
        url = f"{self.api_urls['pages']}/{page_node_id}/{_EXPORT_API_PATH}/{export_format}"
        # url = self._get_export_url(node_id=page_node_id, export_format=export_format)
        return util.get_byte_response(url=url, headers=self._headers)

    # def _get_export_url(self, node_id: int, export_format: str) -> str:
    #     return f"{self.base_page_url}/{node_id}/{_EXPORT_API_PATH}/{export_format}"

    @staticmethod
    def _generate_root_folder(base_folder_name: str) -> str:
        """return base archive name"""
        return base_folder_name + "_" + datetime.now().strftime(_DATE_STR_FORMAT)
