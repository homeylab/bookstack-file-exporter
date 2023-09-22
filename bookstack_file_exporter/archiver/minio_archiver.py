from typing import Union

from bookstack_file_exporter.config_helper.remote import StorageProviderConfig
from bookstack_file_exporter.archiver import util

from minio import Minio

import logging

log = logging.getLogger(__name__)


class MinioArchiver:
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
            else:
                return path_name
        return ""
              
    def upload_backup(self, local_file_path: str):
        # this will be the name of the object to upload
        # only get the file name not path
        # we are going to use path provided by user for object storage
        file_name = local_file_path.split("/")[-1]
        if self.path:
            object_path = f"{self.path}/{file_name}"
        else:
            object_path = file_name
        result = self._client.fput_object(self.bucket, object_path, local_file_path)
        log.info(f"Created object: {result.object_name} with tag: {result.etag} and version-id: {result.version_id}")