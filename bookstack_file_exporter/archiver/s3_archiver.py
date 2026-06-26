import logging
import os

# pylint: disable=import-error
from minio import Minio
# pylint: disable=import-error
from minio.datatypes import Object as MinioObject

from bookstack_file_exporter.common import util as common_util
from bookstack_file_exporter.config_helper.remote import StorageProviderConfig



log = logging.getLogger(__name__)

class S3CompatibleArchiver:
    """Handles uploads, retention, and bucket validation for any S3-compatible target
    (AWS S3, MinIO, or any other S3-compatible store). Both types share this class — the
    upload/cleanup API surface (fput_object, list_objects, remove_object, bucket_exists)
    is identical.

    Args:
        :provider_config: <StorageProviderConfig> = resolved endpoint, secure flag,
            credential Provider, and the raw entry (bucket/path/region/keep_last).
    """
    def __init__(self, provider_config: StorageProviderConfig):
        cfg = provider_config.config
        self._client = Minio(
            provider_config.endpoint,
            credentials=provider_config.credentials,
            secure=provider_config.secure,
            region=cfg.region,
        )
        self.bucket = cfg.bucket
        self.path = self._generate_path(cfg.path)
        self.keep_last = cfg.keep_last
        self._validate_bucket()

    def _validate_bucket(self):
        if not self._client.bucket_exists(self.bucket):
            raise ValueError(f"Given bucket does not exist: {self.bucket}")

    def _generate_path(self, path_name: str | None) -> str:
        return path_name.rstrip('/') if path_name else ""

    def upload_backup(self, local_file_path: str) -> str:
        """upload archive file to object storage bucket; return 'bucket/object_path' dest string"""
        # this will be the name of the object to upload
        # only get the file name not path
        # we are going to use path provided by user for object storage
        file_name = os.path.basename(local_file_path)
        if self.path:
            object_path = f"{self.path}/{file_name}"
        else:
            object_path = file_name
        result = self._client.fput_object(self.bucket, object_path, local_file_path)
        log.info("""Created object: %s with tag: %s and version-id: %s""",
                 result.object_name, result.etag, result.version_id)
        return f"{self.bucket}/{object_path}"

    def clean_up(self, file_extension: str):
        """delete objects based on 'keep_last' number"""
        # this captures keep_last = 0
        if not self.keep_last:
            return
        to_delete = self._get_stale_objects(file_extension)
        if to_delete:
            self._delete_objects(to_delete)

    def _scan_objects(self, file_extension: str) -> list[MinioObject]:
        filter_str = "bookstack_export_"
        # prefix should end in '/' for object listing
        # ref: https://min.io/docs/minio/linux/developers/python/API.html#list_objects
        path_prefix = self.path + "/"
        # get all objects in archive path/directory
        full_list: list[MinioObject] = self._client.list_objects(self.bucket, prefix=path_prefix)
        # validate and filter out non managed objects
        return [object for object in full_list
                if object.object_name.endswith(file_extension)
                    and filter_str in object.object_name]

    def _get_stale_objects(self, file_extension: str) -> list[MinioObject]:
        minio_objects = self._scan_objects(file_extension)
        if not minio_objects:
            log.debug("No objects found to clean up")
            return []
        if self.keep_last < 0:
            # we want to keep one copy at least
            # last copy that remains if local is deleted
            log.debug("'keep_last' set to negative number, ignoring")
            return []
        to_delete = []
        if len(minio_objects) > self.keep_last:
            log.debug("Number of objects is greater than 'keep_last'")
            log.debug("Running clean up of objects")
            to_delete = self._filter_objects(minio_objects)
        return to_delete

    def _filter_objects(self, minio_objects: list[MinioObject]) -> list[MinioObject]:
        objects_to_clean = common_util.oldest_beyond_keep(
            minio_objects,
            key=lambda d: d.last_modified,
            keep_last=self.keep_last,
        )
        log.debug("%d objects will be cleaned up", len(objects_to_clean))
        return objects_to_clean

    def _delete_objects(self, minio_objects: list[MinioObject]):
        for item in minio_objects:
            self._client.remove_object(self.bucket, item.object_name)
