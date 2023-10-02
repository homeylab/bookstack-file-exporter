from typing import Union
import logging

from minio import Minio

from bookstack_file_exporter.config_helper.remote import StorageProviderConfig

log = logging.getLogger(__name__)

class MinioArchiver:
    """
    Class to handle minio object upload and validations.
    
    Args:
        config <StorageProviderConfig> = minio configuration
        bucket <str> = upload bucket
        path <str> (optional) = specify bucket path for upload

    Returns:
        MinioArchiver instance for archival use
    """
    def __init__(self, config: StorageProviderConfig):
        self._client = Minio(
            config.host,
            access_key=config.access_key,
            secret_key=config.secret_key,
            region=config.region
        )
        self.bucket = config.bucket
        self.path = self._generate_path(config.path)
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
