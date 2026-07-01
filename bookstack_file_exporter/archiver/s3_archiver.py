import logging
import os

# pylint: disable=import-error
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError

from bookstack_file_exporter.common import util as common_util
from bookstack_file_exporter.config_helper.remote import StorageProviderConfig

log = logging.getLogger(__name__)

# only objects containing this substring are eligible for retention clean up;
# guards against deleting user-managed objects that happen to share a prefix/bucket
_MANAGED_FILTER = "bookstack_export_"

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

    def clean_up(self, file_extension: str):
        """delete objects based on 'keep_last' number"""
        if not self.keep_last:  # captures keep_last == 0
            return
        to_delete = self._get_stale_objects(file_extension)
        if to_delete:
            self._delete_objects(to_delete)

    def _scan_objects(self, file_extension: str) -> list[dict]:
        prefix = f"{self.prefix}/" if self.prefix else ""
        objects: list[dict] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            objects.extend(page.get("Contents", []))
        return [obj for obj in objects
                if obj["Key"].endswith(file_extension) and _MANAGED_FILTER in obj["Key"]]

    def _get_stale_objects(self, file_extension: str) -> list[dict]:
        objects = self._scan_objects(file_extension)
        if not objects:
            log.debug("No objects found to clean up")
            return []
        if self.keep_last < 0:
            log.warning(
                "'keep_last' for bucket %s is negative (%s); skipping retention "
                "— no objects deleted", self.bucket, self.keep_last)
            return []
        if len(objects) > self.keep_last:
            log.debug("Number of objects is greater than 'keep_last'; running clean up")
            return self._filter_objects(objects)
        return []

    def _filter_objects(self, objects: list[dict]) -> list[dict]:
        objects_to_clean = common_util.oldest_beyond_keep(
            objects, key=lambda d: d["LastModified"], keep_last=self.keep_last)
        log.debug("%d objects will be cleaned up", len(objects_to_clean))
        return objects_to_clean

    def _delete_objects(self, objects: list[dict]):
        for item in objects:
            self._client.delete_object(Bucket=self.bucket, Key=item["Key"])
