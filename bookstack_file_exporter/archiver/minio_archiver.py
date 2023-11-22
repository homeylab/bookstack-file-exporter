from typing import Union, List
import logging

# pylint: disable=import-error
from minio import Minio
# pylint: disable=import-error
from minio.datatypes import Object as MinioObject

from bookstack_file_exporter.config_helper.remote import StorageProviderConfig



log = logging.getLogger(__name__)

class MinioArchiver:
    """
    MinioArchiver handles uploads, lifecycle, and validations for minio archives.
    
    Args:
        :config: <StorageProviderConfig> = minio configuration

        :bucket: <str> = upload bucket
        
        :path: <str> (optional) = specify bucket path for upload

    Returns:
        MinioArchiver instance for archival use
    """
    def __init__(self, access_key: str, secret_key: str, config: StorageProviderConfig):
        self._client = Minio(
            config.host,
            access_key=access_key,
            secret_key=secret_key,
            region=config.region
        )
        self.bucket = config.bucket
        self.path = self._generate_path(config.path)
        self.keep_last = config.keep_last
        self._validate_bucket()

    def _validate_bucket(self):
        if not self._client.bucket_exists(self.bucket):
            raise ValueError(f"Given bucket does not exist: {self.bucket}")

    def _generate_path(self, path_name: Union[str, None]) -> str:
        if path_name:
            if path_name[-1] == '/':
                return path_name[:-1]
            return path_name
        return ""

    def upload_backup(self, local_file_path: str):
        """upload archive file to minio bucket"""
        # this will be the name of the object to upload
        # only get the file name not path
        # we are going to use path provided by user for object storage
        file_name = local_file_path.split("/")[-1]
        if self.path:
            object_path = f"{self.path}/{file_name}"
        else:
            object_path = file_name
        result = self._client.fput_object(self.bucket, object_path, local_file_path)
        log.info("""Created object: %s with tag: %s and version-id: %s""",
                 result.object_name, result.etag, result.version_id)

    def clean_up(self, file_extension: str):
        """delete objects based on 'keep_last' number"""
        # this captures keep_last = 0
        if not self.keep_last:
            return
        to_delete = self._get_stale_objects(file_extension)
        if to_delete:
            self._delete_objects(to_delete)

    def _scan_objects(self, file_extension: str) -> List[MinioObject]:
        filter_str = "bookstack_export_"
        # prefix should end in '/' for minio
        # ref: https://min.io/docs/minio/linux/developers/python/API.html#list_objects
        path_prefix = self.path + "/"
        # get all objects in archive path/directory
        full_list: List[MinioObject] = self._client.list_objects(self.bucket, prefix=path_prefix)
        # validate and filter out non managed objects
        if full_list:
            return [object for object in full_list
                    if object.object_name.endswith(file_extension)
                        and filter_str in object.object_name]
        return []

    def _get_stale_objects(self, file_extension: str) -> List[MinioObject]:
        minio_objects = self._scan_objects(file_extension)
        if not minio_objects:
            log.debug("No minio objects found to clean up")
            return []
        if self.keep_last < 0:
            # we want to keep one copy at least
            # last copy that remains if local is deleted
            log.debug("Minio 'keep_last' set to negative number, ignoring")
            return []
        to_delete = []
        if len(minio_objects) > self.keep_last:
            log.debug("Number of minio objects is greater than 'keep_last'")
            log.debug("Running clean up of minio objects")
            to_delete = self._filter_objects(minio_objects)
        return to_delete

    def _filter_objects(self, minio_objects: List[MinioObject]) -> List[MinioObject]:
        # sort by minio datetime 'last_modified' time
        # ascending order
        sorted_objects = sorted(minio_objects, key=lambda d: d.last_modified)
        objects_to_clean =  []
        # how many items we will have to delete to fulfill 'keep_last'
        to_delete = len(sorted_objects) - self.keep_last
        # collect objects to delete
        for item in sorted_objects:
            objects_to_clean.append(item)
            to_delete -= 1
            if to_delete <= 0:
                break
        log.debug("%d minio objects will be cleaned up", len(objects_to_clean))
        return objects_to_clean

    def _delete_objects(self, minio_objects: List[MinioObject]):
        for item in minio_objects:
            self._client.remove_object(self.bucket, item.object_name)
