from typing import Union

## convenience class
## able to work for minio, s3, etc.
class StorageProviderConfig:
    def __init__(self, access_key: str, secret_key: str, bucket: str, host: Union[str, None], path: Union[str, None], region: Union[str, None]):
        self.host = host
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.path = path
        self.region = region
