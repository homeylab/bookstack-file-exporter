import logging

# pylint: disable=import-error
from minio.credentials import Provider

from bookstack_file_exporter.config_helper.models import BaseStorageConfig

log = logging.getLogger(__name__)


def aws_endpoint_from_region(region: str) -> str:
    """Default AWS S3 endpoint host for a region (used when no host is given)."""
    return f"s3.{region}.amazonaws.com"


## convenience class — holds one resolved object storage target (minio or s3)
# pylint: disable=too-few-public-methods
class StorageProviderConfig:
    """Resolved configuration for a single object storage target.

    Carries a minio-py credential Provider (not raw key strings) plus the resolved
    endpoint host and TLS flag, so the archiver can construct a Minio() client directly.

    Args:
        storage_type <str> = 'minio' | 's3'; drives validation + dispatch
        endpoint <str> = host:port the client connects to (resolved; for s3 may be
            defaulted from region)
        secure <bool> = TLS on/off
        credentials <Provider> = minio-py credential provider
        config <BaseStorageConfig> = the raw parsed entry (bucket/path/region/keep_last)
    """

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def __init__(self, storage_type: str, endpoint: str, secure: bool,
                 credentials: Provider, config: BaseStorageConfig):
        self.type = storage_type
        self.endpoint = endpoint
        self.secure = secure
        self.credentials = credentials
        self.config = config
        self._valid_checker = {
            "minio": self._is_minio_valid,
            "s3": self._is_s3_valid,
        }

    def is_valid(self, storage_type: str) -> bool:
        """check if object storage config is valid for the given type"""
        return self._valid_checker[storage_type]()

    def _is_minio_valid(self) -> bool:
        """minio requires an explicit host; creds may resolve at call time."""
        if not self.config.host:
            log.error("host is missing from minio configuration and is required")
            return False
        return True

    def _is_s3_valid(self) -> bool:
        """s3 requires a region (host defaults from it); creds may come from the AWS
        chain (incl. IAM role) at runtime, so they are NOT statically required here."""
        if not self.config.region:
            log.error("region is missing from s3 configuration and is required")
            return False
        return True
