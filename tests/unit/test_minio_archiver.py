# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name
# pylint: disable=protected-access
"""Unit tests for MinioArchiver.upload_backup return value."""
from unittest.mock import MagicMock

from bookstack_file_exporter.archiver.minio_archiver import MinioArchiver


def _make_minio_archiver(bucket: str, path: str | None = None):
    """Build a MinioArchiver bypassing real Minio init."""
    instance = MinioArchiver.__new__(MinioArchiver)
    instance._client = MagicMock()
    instance.bucket = bucket
    instance.path = MinioArchiver._generate_path(instance, path)
    instance.keep_last = 0
    return instance


class TestUploadBackupReturnValue:
    def test_returns_bucket_slash_object_path_with_prefix(self):
        archiver = _make_minio_archiver("my-bucket", "backups/2024")
        mock_result = MagicMock()
        mock_result.object_name = "backups/2024/export.tgz"
        mock_result.etag = "abc123"
        mock_result.version_id = None
        archiver._client.fput_object.return_value = mock_result

        dest = archiver.upload_backup("/local/path/export.tgz")

        assert dest == "my-bucket/backups/2024/export.tgz"

    def test_returns_bucket_slash_filename_without_prefix(self):
        archiver = _make_minio_archiver("my-bucket", None)
        mock_result = MagicMock()
        mock_result.object_name = "export.tgz"
        mock_result.etag = "def456"
        mock_result.version_id = "v1"
        archiver._client.fput_object.return_value = mock_result

        dest = archiver.upload_backup("/some/path/export.tgz")

        assert dest == "my-bucket/export.tgz"

    def test_fput_object_called_with_correct_args(self):
        archiver = _make_minio_archiver("bucket-x", "uploads")
        mock_result = MagicMock()
        archiver._client.fput_object.return_value = mock_result

        archiver.upload_backup("/data/archive.tgz")

        archiver._client.fput_object.assert_called_once_with(
            "bucket-x", "uploads/archive.tgz", "/data/archive.tgz"
        )
