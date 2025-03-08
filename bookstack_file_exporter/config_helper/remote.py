import logging

from bookstack_file_exporter.config_helper.models import ObjectStorageConfig

log = logging.getLogger(__name__)

## convenience class
## able to work for minio, s3, etc.
class StorageProviderConfig:
    """
    Convenience class to hold object storage provider configuration
    
    Args:
        access_key <str> = required token id

        secret_key <str> = required secret token

        config <ObjectStorageConfig> = required configuration options

    Returns:
        StorageProviderConfig instance for holding configuration
    """

    def __init__(self, access_key: str, secret_key: str, config: ObjectStorageConfig):
        self.config = config
        self._access_key = access_key
        self._secret_key = secret_key
        self._valid_checker = {'minio': self._is_minio_valid()}

    @property
    def access_key(self) -> str:
        """return access key for use"""
        return self._access_key

    @property
    def secret_key(self) -> str:
        """return secret key for use"""
        return self._secret_key

    def is_valid(self, storage_type: str) -> bool:
        """check if object storage config is valid"""
        return self._valid_checker[storage_type]
    
    def _is_minio_valid(self) -> bool:
        """check if minio config is valid"""
        # required values - keys and bucket already checked so skip
        checks = {
            "host": self.config.host
        }
        for prop, check in checks.items():
            if not check:
                log.error("%s is missing from minio configuration and is required", prop)
                return False
        return True
