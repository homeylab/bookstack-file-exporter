from datetime import datetime
import logging
import os

from bookstack_file_exporter.exporter.node import Node
from bookstack_file_exporter.archiver import util
from bookstack_file_exporter.archiver.node_archiver import (
    NodeArchiver,
    BookArchiver,
    ChapterArchiver,
    PageArchiver,
)
from bookstack_file_exporter.archiver.minio_archiver import MinioArchiver
from bookstack_file_exporter.config_helper.remote import StorageProviderConfig
from bookstack_file_exporter.config_helper.config_helper import ConfigNode
from bookstack_file_exporter.common.util import HttpHelper

log = logging.getLogger(__name__)

_DATE_STR_FORMAT = "%Y-%m-%d_%H-%M-%S"

# pylint: disable=too-many-instance-attributes
class Archiver:
    """
    Archiver helps handle archive duties: pulls all the necessary files from upstream
    and then pushes them to the specified backup location(s)

    Args:
        :config: <ConfigNode> = Configuration with user inputs and general options.
        :http_client: <HttpHelper> = http helper functions with config from user inputs

    Returns:
        Archiver instance with attributes that are accessible
        for use for handling bookstack exports and remote uploads.
    """
    def __init__(self, config: ConfigNode, http_client: HttpHelper):
        self.config = config
        # for convenience
        self.base_dir = self._level_base_dir(config.base_dir_name,
                                             config.user_inputs.export_level)
        self.archive_dir = self._generate_root_folder(self.base_dir)
        self._archiver: NodeArchiver = self._build_archiver(http_client)

    def _build_archiver(self, http_client: HttpHelper) -> NodeArchiver:
        """Return the appropriate archiver based on the configured export level."""
        export_level = self.config.user_inputs.export_level
        export_meta: bool = self.config.user_inputs.assets.export_meta
        if export_level == "books":
            return BookArchiver(
                archive_dir=self.archive_dir,
                api_urls=self.config.urls,
                export_formats=self.config.user_inputs.formats,
                http_client=http_client,
                export_meta=export_meta,
            )
        if export_level == "chapters":
            return ChapterArchiver(
                archive_dir=self.archive_dir,
                api_urls=self.config.urls,
                export_formats=self.config.user_inputs.formats,
                http_client=http_client,
                export_meta=export_meta,
            )
        # default: "pages"
        return PageArchiver(self.archive_dir, self.config, http_client)

    def create_export_dir(self):
        """create directory for archiving"""
        if not self.config.user_inputs.output_path:
            log.info("No output path specified, using current directory for archive")
            return
        log.info("Creating base directory for archive: %s",
                 self.config.user_inputs.output_path)
        # in docker, this may fail if the user id is not the same as the host
        try:
            util.create_dir(self.config.user_inputs.output_path)
        except PermissionError as perm_err:
            log.warning("Failed to create base directory: %s", perm_err)
            log.warning("This usually occurs in docker environments " \
                        "attempting to skip this step")
            return

    def get_bookstack_exports(self, nodes: dict[int, Node]):
        """export all node content (polymorphic: pages, books, or chapters)"""
        log.info("Exporting all bookstack contents")
        self._archiver.archive(nodes)

    @property
    def has_exported_content(self) -> bool:
        """True if the intermediate tar exists, i.e. at least one file was written.

        Checked against the tar on disk (ground truth) rather than a flag threaded
        up from the archivers, so it cannot drift from what was actually archived.
        """
        return os.path.exists(self._archiver.tar_file)

    def create_archive(self):
        """create tgz archive"""
        self._archiver.gzip_archive()

    # send to remote systems
    def archive_remote(self):
        """for each target, do their respective tasks"""
        if not self.config.object_storage_config:
            return
        # dict built per-call so instance-level monkey-patching of handlers
        # propagates during tests (class-level dict captures pre-patch values)
        handlers = {
            "minio": self._archive_minio,
            "s3": self._archive_s3,
        }
        for key, value in self.config.object_storage_config.items():
            handler = handlers.get(key)
            if handler is None:
                raise ValueError(f"unsupported remote storage type: {key}")
            handler(value)

    def _archive_minio(self, obj_config: StorageProviderConfig):
        minio_archiver = MinioArchiver(obj_config.access_key,
                                       obj_config.secret_key, obj_config.config)
        minio_archiver.upload_backup(self._archiver.archive_file)
        minio_archiver.clean_up(self._archiver.file_extension_map['tgz'])

    def _archive_s3(self, obj_config: StorageProviderConfig):
        raise NotImplementedError("S3 remote storage is not yet implemented")

    def clean_up(self):
        """remove archive after sending to remote target"""
        # this captures keep_last = 0
        if not self.config.user_inputs.keep_last:
            return
        to_delete = self._get_stale_archives()
        if to_delete:
            self._delete_files(to_delete)

    def _get_stale_archives(self) -> list[str]:
        # if user is uploading to object storage
        # delete the local .tgz archive since we have it there already
        archive_list: list[str] = util.scan_archives(self.base_dir,
                                                     self._archiver.file_extension_map['tgz'])
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

    def _filter_archives(self, file_list: list[str]) -> list[str]:
        """get older archives based on keep number"""
        file_dict = {file: os.stat(file).st_ctime for file in file_list}
        ordered = sorted(file_dict.items(), key=lambda item: item[1])
        to_delete = len(ordered) - self.config.user_inputs.keep_last
        # Guard against negative slice when caller invokes us directly with
        # keep_last >= len(file_list). Negative `to_delete` makes ordered[:to_delete]
        # return the first N items instead of an empty list — wrong files deleted.
        if to_delete <= 0:
            return []
        files_to_clean = [key for key, _ in ordered[:to_delete]]
        log.debug("%d local archives will be cleaned up", len(files_to_clean))
        return files_to_clean

    def _delete_files(self, file_list: list[str]):
        for file in file_list:
            util.remove_file(file)

    @staticmethod
    def _level_base_dir(base_dir: str, export_level: str) -> str:
        """Append the export level to the archive base name for non-default levels.

        `pages` (the default) stays byte-identical to prior behavior; `books` and
        `chapters` get a distinguishable name (e.g. `bkps_books`). Because keep_last
        cleanup globs on this base, retention is naturally scoped per level.
        """
        if export_level == "pages":
            return base_dir
        return f"{base_dir}_{export_level}"

    @staticmethod
    def _generate_root_folder(base_folder_name: str) -> str:
        """return base archive name"""
        return base_folder_name + "_" + datetime.now().strftime(_DATE_STR_FORMAT)
