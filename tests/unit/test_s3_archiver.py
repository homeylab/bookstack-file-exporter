# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name
# pylint: disable=protected-access
import boto3
import pytest
from moto import mock_aws

from bookstack_file_exporter.archiver.s3_archiver import S3CompatibleArchiver
from bookstack_file_exporter.config_helper.remote import StorageProviderConfig
from bookstack_file_exporter.config_helper.models import BaseStorageConfig


def _provider(bucket="test-bucket", prefix=None, keep_last=0):
    cfg = BaseStorageConfig(name="t", bucket=bucket, prefix=prefix or "",
                            endpoint=None, region="us-east-1", ambient_auth=True,
                            keep_last=keep_last)
    return StorageProviderConfig(endpoint_url=None, region="us-east-1",
                                 addressing_style="auto", access_key="testing",
                                 secret_key="testing", config=cfg)


@pytest.fixture
def aws(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
        yield


def test_upload_returns_bucket_slash_object_with_prefix(aws, tmp_path):
    f = tmp_path / "export.tgz"; f.write_bytes(b"data")
    assert S3CompatibleArchiver(_provider(prefix="backups/2024")).upload_backup(str(f)) \
        == "test-bucket/backups/2024/export.tgz"


def test_upload_returns_bucket_slash_filename_without_prefix(aws, tmp_path):
    f = tmp_path / "export.tgz"; f.write_bytes(b"data")
    assert S3CompatibleArchiver(_provider()).upload_backup(str(f)) == "test-bucket/export.tgz"


def test_upload_puts_object(aws, tmp_path):
    f = tmp_path / "archive.tgz"; f.write_bytes(b"xyz")
    S3CompatibleArchiver(_provider(prefix="uploads")).upload_backup(str(f))
    keys = [o["Key"] for o in
            boto3.client("s3", region_name="us-east-1").list_objects_v2(Bucket="test-bucket").get("Contents", [])]
    assert "uploads/archive.tgz" in keys


def test_validate_bucket_raises_when_missing(aws):
    with pytest.raises(ValueError):
        S3CompatibleArchiver(_provider(bucket="nope"))


def test_validate_bucket_wraps_endpoint_connection_error(monkeypatch):
    from unittest.mock import MagicMock
    from botocore.exceptions import EndpointConnectionError
    fake = MagicMock()
    fake.head_bucket.side_effect = EndpointConnectionError(endpoint_url="http://unreachable:9000")
    monkeypatch.setattr("boto3.session.Session.client", lambda self, *a, **k: fake)
    with pytest.raises(ValueError):
        S3CompatibleArchiver(_provider())


def test_ambient_none_keys_uses_env_chain(aws, tmp_path):
    # provider with access_key=None -> Session(None,None) -> botocore ambient chain (AWS_* env from `aws` fixture)
    cfg = BaseStorageConfig(name="amb", bucket="test-bucket", region="us-east-1", ambient_auth=True)
    prov = StorageProviderConfig(endpoint_url=None, region="us-east-1", addressing_style="auto",
                                 access_key=None, secret_key=None, config=cfg)
    f = tmp_path / "export.tgz"; f.write_bytes(b"data")
    assert S3CompatibleArchiver(prov).upload_backup(str(f)) == "test-bucket/export.tgz"
