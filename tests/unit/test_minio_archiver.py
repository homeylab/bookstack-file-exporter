# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name
# pylint: disable=protected-access,too-few-public-methods
"""Unit tests for S3CompatibleArchiver: upload return value + client construction."""
from unittest.mock import MagicMock, patch

from bookstack_file_exporter.archiver.minio_archiver import S3CompatibleArchiver


def _make_archiver(bucket: str, path: str | None = None):
    """Build an S3CompatibleArchiver bypassing real Minio init."""
    instance = S3CompatibleArchiver.__new__(S3CompatibleArchiver)
    instance._client = MagicMock()
    instance.bucket = bucket
    instance.path = S3CompatibleArchiver._generate_path(instance, path)
    instance.keep_last = 0
    return instance


class TestUploadBackupReturnValue:
    def test_returns_bucket_slash_object_path_with_prefix(self):
        archiver = _make_archiver("my-bucket", "backups/2024")
        result = MagicMock(object_name="backups/2024/export.tgz", etag="abc", version_id=None)
        archiver._client.fput_object.return_value = result
        assert archiver.upload_backup("/local/export.tgz") == "my-bucket/backups/2024/export.tgz"

    def test_returns_bucket_slash_filename_without_prefix(self):
        archiver = _make_archiver("my-bucket", None)
        result = MagicMock(object_name="export.tgz", etag="def", version_id="v1")
        archiver._client.fput_object.return_value = result
        assert archiver.upload_backup("/some/export.tgz") == "my-bucket/export.tgz"

    def test_fput_object_called_with_correct_args(self):
        archiver = _make_archiver("bucket-x", "uploads")
        archiver._client.fput_object.return_value = MagicMock()
        archiver.upload_backup("/data/archive.tgz")
        archiver._client.fput_object.assert_called_once_with(
            "bucket-x", "uploads/archive.tgz", "/data/archive.tgz"
        )


class TestClientConstruction:
    def test_minio_client_built_with_endpoint_secure_region_credentials(self):
        creds = MagicMock()
        provider_config = MagicMock()
        provider_config.endpoint = "minio.local:9000"
        provider_config.secure = False
        provider_config.credentials = creds
        provider_config.config = MagicMock(bucket="b", path="p", keep_last=0, region="us-east-1")

        with patch("bookstack_file_exporter.archiver.minio_archiver.Minio") as mock_minio:
            instance = S3CompatibleArchiver.__new__(S3CompatibleArchiver)
            # call the real __init__ but stub bucket validation
            with patch.object(S3CompatibleArchiver, "_validate_bucket", lambda self: None):
                S3CompatibleArchiver.__init__(instance, provider_config)

        mock_minio.assert_called_once_with(
            "minio.local:9000",
            credentials=creds,
            secure=False,
            region="us-east-1",
        )
        assert instance.bucket == "b"
        assert instance.keep_last == 0
