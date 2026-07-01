import logging
import os

# pylint: disable=import-error
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError

from bookstack_file_exporter.config_helper.remote import StorageProviderConfig

log = logging.getLogger(__name__)

class S3CompatibleArchiver:
    """Uploads, retention, and bucket validation for any S3-compatible target (AWS S3,
    MinIO, Cloudflare R2, Backblaze B2, Wasabi, DO Spaces) via a boto3 S3 client.

    A boto3 Session is built per target from the resolved StorageProviderConfig, so each
    target has independent credentials (no shared/process-global client state). When
    access_key/secret_key are None the Session falls back to botocore's ambient chain
    (env / shared config / IRSA / IMDS / assume-role) — used only when ambient_auth is set.
    """
    def __init__(self, provider_config: StorageProviderConfig):
        cfg = provider_config.config
        session = boto3.session.Session(
            aws_access_key_id=provider_config.access_key,
            aws_secret_access_key=provider_config.secret_key,
            region_name=provider_config.region,
        )
        self._client = session.client(
            "s3",
            endpoint_url=provider_config.endpoint_url,
            config=Config(s3={"addressing_style": provider_config.addressing_style}),
        )
        self.bucket = cfg.bucket
        self.prefix = self._generate_prefix(cfg.prefix)
        self.keep_last = cfg.keep_last
        self._validate_bucket()

    def _validate_bucket(self):
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except (ClientError, BotoCoreError) as err:
            raise ValueError(
                f"Given bucket does not exist or is not accessible: {self.bucket}") from err

    def _generate_prefix(self, prefix_name: str | None) -> str:
        return prefix_name.rstrip('/') if prefix_name else ""

    def upload_backup(self, local_file_path: str) -> str:
        """upload archive file to object storage bucket; return 'bucket/object_path' dest string.

        Upload errors are intentionally surfaced to the caller (archiver.py owns per-target
        aggregation), unlike _validate_bucket which wraps failures in ValueError."""
        # this will be the name of the object to upload
        # only get the file name not path
        # we are going to use the prefix provided by the user for object storage
        file_name = os.path.basename(local_file_path)
        object_path = f"{self.prefix}/{file_name}" if self.prefix else file_name
        self._client.upload_file(local_file_path, self.bucket, object_path)
        log.info("Uploaded object: %s to bucket: %s", object_path, self.bucket)
        return f"{self.bucket}/{object_path}"

    def clean_up(self, file_extension: str):  # pylint: disable=unused-argument
        """retention — implemented in the next step (Task 6)"""
        return
