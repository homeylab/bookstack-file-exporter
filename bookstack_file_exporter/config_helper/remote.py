from typing import Union

## convenience class
## able to work for minio, s3, etc.
class StorageProviderConfig:
    """
    Convenience class to get dot notation for remote object storage
    configuration access.
    
    Args:
        access_key <str> = required token id
        secret_key <str> = required secret token
        bucket <str> = bucket to upload
        host <str> (optional) = if provider requires a host/url
        path <str> (optional) = specify bucket path for upload
        region <str> (optional) = if provider requires region

    Returns:
        StorageProviderConfig instance for dot notation access
    """
    def __init__(self, access_key: str, secret_key: str, bucket: str,
                 host: Union[str, None]=None, path: Union[str, None]=None,
                 region: Union[str, None]=None):
        self.host = host
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.path = path
        self.region = region
