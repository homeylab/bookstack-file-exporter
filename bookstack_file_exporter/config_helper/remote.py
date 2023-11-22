from bookstack_file_exporter.config_helper.models import ObjectStorageConfig

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

    @property
    def access_key(self) -> str:
        """return access key for use"""
        return self._access_key

    @property
    def secret_key(self) -> str:
        """return secret key for use"""
        return self._secret_key
