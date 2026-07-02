import logging
import os

# pylint: disable=import-error
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError

from bookstack_file_exporter.common import util as common_util
from bookstack_file_exporter.config_helper.remote import S3ProviderConfig

log = logging.getLogger(__name__)

# only objects whose name (after the configured prefix) STARTS with this marker are
# eligible for retention clean up; anchored to guard user objects that merely contain
# the marker somewhere in their name (every tool-created archive starts with it)
_MANAGED_FILTER = "bookstack_export_"

# S3 DeleteObjects accepts at most 1000 keys per request (documented API limit,
# enforced server-side; boto3/botocore expose no constant for it)
_MAX_DELETE_KEYS = 1000

class S3CompatibleArchiver:
    """Uploads, retention, and bucket validation for any S3-compatible target (AWS S3,
    MinIO, Cloudflare R2, Backblaze B2, Wasabi, DO Spaces) via a boto3 S3 client.

    A boto3 Session is built per target from the resolved S3ProviderConfig, so each
    target has independent credentials (no shared/process-global client state). When
    access_key/secret_key are None the Session falls back to botocore's ambient chain
    (env / shared config / IRSA / IMDS / assume-role) — used only when ambient_auth is set.
    """
    def __init__(self, provider_config: S3ProviderConfig):
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
        self.bucket = provider_config.bucket
        self.prefix = provider_config.prefix
        self.keep_last = provider_config.keep_last
        self._validate_bucket()

    def _validate_bucket(self):
        """Startup bucket check via HeadBucket.

        Fail loud on a definitively-missing bucket (404) — the common config mistake, caught
        before a full export runs. Warn-and-proceed on an ambiguous ClientError (e.g. 403 from
        a write-only key that can PutObject but lacks ListBucket, or a provider that restricts
        HeadBucket): the credential may still upload fine, so don't falsely reject it — the
        upload surfaces any real problem. A BotoCoreError (EndpointConnectionError /
        ParamValidationError) is a hard failure: the endpoint itself is unreachable or
        misconfigured, not just the bucket."""
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError as err:
            code = err.response.get("Error", {}).get("Code", "")
            status = err.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code in ("404", "NoSuchBucket") or status == 404:
                raise ValueError(f"Bucket does not exist: {self.bucket}") from err
            log.warning(
                "Could not verify bucket %s (%s); permissions or provider limitation — "
                "upload will be attempted anyway", self.bucket, code or status)
        except BotoCoreError as err:
            raise ValueError(
                f"Object storage endpoint unreachable or misconfigured for bucket "
                f"{self.bucket}: {err}") from err

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
        """List managed objects directly under the prefix (top-level only).

        Delimiter='/' scopes the listing to one level — same as the v2 minio-py
        default (recursive=False) — so objects in nested 'subfolders' under the
        prefix are never retention candidates. Filtering happens per page so at
        most one page of unfiltered entries is held in memory."""
        prefix = f"{self.prefix}/" if self.prefix else ""
        matched: list[dict] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix, Delimiter="/"):
            matched.extend(obj for obj in page.get("Contents", [])
                           if obj["Key"].endswith(file_extension)
                           and obj["Key"].removeprefix(prefix).startswith(_MANAGED_FILTER))
        return matched

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
        for i in range(0, len(objects), _MAX_DELETE_KEYS):
            chunk = objects[i:i + _MAX_DELETE_KEYS]
            resp = self._client.delete_objects(
                Bucket=self.bucket,
                Delete={"Objects": [{"Key": obj["Key"]} for obj in chunk],
                        "Quiet": True})
            errors = resp.get("Errors", [])
            if errors:
                failed = ", ".join(e.get("Key", "?") for e in errors)
                raise ValueError(
                    f"retention delete failed for {len(errors)} object(s) in bucket "
                    f"{self.bucket}: {failed}")
