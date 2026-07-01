from bookstack_file_exporter.config_helper.models import BaseStorageConfig


## convenience class — one resolved, boto3-ready object storage target
# pylint: disable=too-few-public-methods
class StorageProviderConfig:
    """Resolved, boto3-ready configuration for a single object storage target.

    Args:
        endpoint_url <str|None> = full URL (scheme://host[:port]); None => AWS default endpoint.
        region <str|None> = region_name for boto3 (None => let botocore resolve, ambient only).
        addressing_style <str> = 'path' or 'auto', passed to botocore Config.
        access_key/secret_key <str|None> = explicit static creds; None => botocore ambient chain.
        config <BaseStorageConfig> = the raw parsed entry (bucket/prefix/keep_last/name).
    """
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def __init__(self, endpoint_url: str | None, region: str | None, addressing_style: str,
                 access_key: str | None, secret_key: str | None, config: BaseStorageConfig):
        self.endpoint_url = endpoint_url
        self.region = region
        self.addressing_style = addressing_style
        self.access_key = access_key
        self.secret_key = secret_key
        self.config = config
