from typing import List, Dict
from datetime import datetime
import logging
import os

from bookstack_file_exporter.exporter.node import Node
from bookstack_file_exporter.archiver import util
from bookstack_file_exporter.archiver.page_archiver import PageArchiver, ImageNode
from bookstack_file_exporter.archiver.minio_archiver import MinioArchiver
from bookstack_file_exporter.config_helper.remote import StorageProviderConfig
from bookstack_file_exporter.config_helper.config_helper import ConfigNode

log = logging.getLogger(__name__)

_DATE_STR_FORMAT = "%Y-%m-%d_%H-%M-%S"

# pylint: disable=too-many-instance-attributes
class Archiver:
    """
    Archiver pulls all the necessary files from upstream 
    and then pushes them to the specified backup location(s)

    Args:
        :config: <ConfigNode> = Configuration with user inputs and general options.

    Returns:
        Archiver instance with attributes that are accessible 
        for use for handling bookstack exports and remote uploads.
    """
    def __init__(self, config: ConfigNode):
        self.config = config
        # for convenience
        self.base_dir = config.base_dir_name
        self.archive_dir = self._generate_root_folder(self.base_dir)
        self._page_archiver = self._generate_page_archiver()
        self._remote_exports = {'minio': self._archive_minio, 's3': self._archive_s3}


    def get_bookstack_exports(self, page_nodes: Dict[int, Node]):
        """export all page content"""
        log.info("Exporting all bookstack page contents")
        # get images first if requested
        # this is because we may want to manipulate page data with modify_markdown flag
        all_image_meta = self._get_page_image_map()
        for _, page in page_nodes.items():
            page_image_meta = []
            if page.id_ in all_image_meta:
                page_image_meta = all_image_meta[page.id_]
            self._get_page_files(page, page_image_meta)
            self._get_page_images(page, page_image_meta)

    def _get_page_files(self, page_node: Node, image_meta: List[ImageNode]):
        """pull all bookstack pages into local files/tar"""
        log.debug("Exporting bookstack page data")
        self._page_archiver.archive_page(page_node, image_meta)

    def _get_page_image_map(self) -> Dict[int, ImageNode]:
        if not self._page_archiver.export_images:
            log.debug("skipping image export based on user input")
            return {}
        return self._page_archiver.get_image_meta()

    def _get_page_images(self, page_node: Node, img_nodes: List[ImageNode]):
        if not img_nodes:
            log.debug("page has no images to pull")
            return
        log.debug("Exporting bookstack page images")
        self._page_archiver.archive_page_images(page_node.parent.file_path,
                                                page_node.name, img_nodes)

    def create_archive(self):
        """create tgz archive"""
        # check if tar needs to be created first
        self._page_archiver.gzip_archive()

    # send to remote systems
    def archive_remote(self):
        """for each target, do their respective tasks"""
        if self.config.object_storage_config:
            for key, value in self.config.object_storage_config.items():
                self._remote_exports[key](value)

    def _archive_minio(self, obj_config: StorageProviderConfig):
        minio_archiver = MinioArchiver(obj_config.access_key,
                                       obj_config.secret_key, obj_config.config)
        minio_archiver.upload_backup(self._page_archiver.archive_file)
        minio_archiver.clean_up(self._page_archiver.file_extension_map['tgz'])

    def _archive_s3(self, obj_config: StorageProviderConfig):
        pass

    def clean_up(self):
        """remove archive after sending to remote target"""
        # this captures keep_last = 0
        if not self.config.user_inputs.keep_last:
            return
        to_delete = self._get_stale_archives()
        if to_delete:
            self._delete_files(to_delete)

    def _get_stale_archives(self) -> List[str]:
        # if user is uploading to object storage
        # delete the local .tgz archive since we have it there already
        archive_list: List[str] = util.scan_archives(self.base_dir,
                                                     self._page_archiver.file_extension_map['tgz'])
        if not archive_list:
            log.debug("No archive files found to clean up")
            return []
        # if negative number, we remove all local archives
        # assume user is using remote storage and will upload there
        if self.config.user_inputs.keep_last < 0:
            log.debug("Local archive files will be deleted, keep_last: -1")
            return archive_list
        # keep_last > 0 condition
        to_delete = []
        if len(archive_list) > self.config.user_inputs.keep_last:
            log.debug("Number of archives is greater than 'keep_last'")
            log.debug("Running clean up of local archives")
            to_delete = self._filter_archives(archive_list)
        return to_delete

    def _filter_archives(self, file_list: List[str]) -> List[str]:
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
        to_delete = len(ordered_dict) - self.config.user_inputs.keep_last
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

    def _generate_page_archiver(self)-> PageArchiver:
        return PageArchiver(self.archive_dir, self.config)


    @staticmethod
    def _generate_root_folder(base_folder_name: str) -> str:
        """return base archive name"""
        return base_folder_name + "_" + datetime.now().strftime(_DATE_STR_FORMAT)
