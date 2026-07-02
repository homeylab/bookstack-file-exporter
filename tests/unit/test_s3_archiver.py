# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name
# pylint: disable=protected-access
import boto3
import pytest
from moto import mock_aws

from bookstack_file_exporter.archiver.s3_archiver import S3CompatibleArchiver
from bookstack_file_exporter.config_helper.models import S3StorageConfig
from bookstack_file_exporter.config_helper.remote import S3ProviderConfig


def _provider(bucket="test-bucket", prefix=None, keep_last=0):
    return S3ProviderConfig(S3StorageConfig(name="t", bucket=bucket, prefix=prefix or "",
                                            endpoint=None, region="us-east-1",
                                            ambient_auth=True, keep_last=keep_last))


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


def test_validate_bucket_404_raises(monkeypatch):
    # definitively-missing bucket: hard fail before an export runs
    from unittest.mock import MagicMock
    from botocore.exceptions import ClientError
    err = ClientError(
        {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}}, "HeadBucket")
    fake = MagicMock()
    fake.head_bucket.side_effect = err
    monkeypatch.setattr("boto3.session.Session.client", lambda self, *a, **k: fake)
    with pytest.raises(ValueError):
        S3CompatibleArchiver(_provider())


def test_validate_bucket_403_warns_and_proceeds(monkeypatch, caplog):
    # write-only key (PutObject but no ListBucket) => HeadBucket 403; must NOT block
    # construction, since the upload itself may still succeed. Warn instead.
    import logging
    from unittest.mock import MagicMock
    from botocore.exceptions import ClientError
    err = ClientError(
        {"Error": {"Code": "403"}, "ResponseMetadata": {"HTTPStatusCode": 403}}, "HeadBucket")
    fake = MagicMock()
    fake.head_bucket.side_effect = err
    monkeypatch.setattr("boto3.session.Session.client", lambda self, *a, **k: fake)
    with caplog.at_level(logging.WARNING):
        arch = S3CompatibleArchiver(_provider())  # must not raise
    assert arch.bucket == "test-bucket"
    assert "Could not verify bucket" in caplog.text


def test_ambient_none_keys_uses_env_chain(aws, tmp_path):
    # provider with access_key=None -> Session(None,None) -> botocore ambient chain (AWS_* env from `aws` fixture)
    prov = S3ProviderConfig(S3StorageConfig(name="amb", bucket="test-bucket", prefix="",
                                            endpoint=None, region="us-east-1",
                                            ambient_auth=True, keep_last=0))
    f = tmp_path / "export.tgz"; f.write_bytes(b"data")
    assert S3CompatibleArchiver(prov).upload_backup(str(f)) == "test-bucket/export.tgz"


def _seed(client, bucket, keys):
    for k in keys:
        client.put_object(Bucket=bucket, Key=k, Body=b"x")


def test_clean_up_deletes_oldest_beyond_keep_last(aws):
    client = boto3.client("s3", region_name="us-east-1")
    _seed(client, "test-bucket", [f"uploads/bookstack_export_{i}.tgz" for i in range(5)])
    S3CompatibleArchiver(_provider(prefix="uploads", keep_last=2)).clean_up(".tgz")
    remaining = client.list_objects_v2(Bucket="test-bucket").get("Contents", [])
    assert len(remaining) == 2


def test_clean_up_keep_last_zero_deletes_nothing(aws):
    client = boto3.client("s3", region_name="us-east-1")
    _seed(client, "test-bucket", ["uploads/bookstack_export_1.tgz", "uploads/unrelated.tgz"])
    S3CompatibleArchiver(_provider(prefix="uploads", keep_last=0)).clean_up(".tgz")
    assert len(client.list_objects_v2(Bucket="test-bucket").get("Contents", [])) == 2


def test_scan_paginates_beyond_1000(aws):
    client = boto3.client("s3", region_name="us-east-1")
    _seed(client, "test-bucket", [f"bookstack_export_{i:04d}.tgz" for i in range(1001)])
    assert len(S3CompatibleArchiver(_provider(prefix=None, keep_last=1))._scan_objects(".tgz")) == 1001


def test_filter_objects_keeps_newest_by_lastmodified(aws):
    from datetime import datetime, timezone
    arch = S3CompatibleArchiver(_provider(keep_last=2))
    # input deliberately NOT in chronological order to prove it sorts by LastModified
    objs = [
        {"Key": "new2", "LastModified": datetime(2024, 1, 5, tzinfo=timezone.utc)},
        {"Key": "old0", "LastModified": datetime(2024, 1, 1, tzinfo=timezone.utc)},
        {"Key": "new1", "LastModified": datetime(2024, 1, 4, tzinfo=timezone.utc)},
        {"Key": "old1", "LastModified": datetime(2024, 1, 2, tzinfo=timezone.utc)},
        {"Key": "old2", "LastModified": datetime(2024, 1, 3, tzinfo=timezone.utc)},
    ]
    deleted = {o["Key"] for o in arch._filter_objects(objs)}
    assert deleted == {"old0", "old1", "old2"}  # 3 oldest deleted, 2 newest kept


def test_clean_up_preserves_unmanaged_objects(aws):
    client = boto3.client("s3", region_name="us-east-1")
    _seed(client, "test-bucket",
          [f"uploads/bookstack_export_{i}.tgz" for i in range(3)] + ["uploads/unrelated.tgz"])
    S3CompatibleArchiver(_provider(prefix="uploads", keep_last=1)).clean_up(".tgz")
    keys = {o["Key"] for o in client.list_objects_v2(Bucket="test-bucket").get("Contents", [])}
    assert "uploads/unrelated.tgz" in keys          # non-managed object never a deletion candidate
    assert len([k for k in keys if "bookstack_export_" in k]) == 1  # 3 managed -> keep_last=1


def test_scan_ignores_nested_keys(aws):
    # v2.3.0 minio-py listed non-recursively; nested "subfolders" under the
    # prefix are user-managed space and must never be retention candidates
    client = boto3.client("s3", region_name="us-east-1")
    _seed(client, "test-bucket", ["uploads/bookstack_export_1.tgz",
                                  "uploads/archive/bookstack_export_2.tgz"])
    arch = S3CompatibleArchiver(_provider(prefix="uploads", keep_last=1))
    keys = [o["Key"] for o in arch._scan_objects(".tgz")]
    assert keys == ["uploads/bookstack_export_1.tgz"]


def test_clean_up_never_deletes_nested_keys(aws):
    client = boto3.client("s3", region_name="us-east-1")
    _seed(client, "test-bucket",
          [f"uploads/bookstack_export_{i}.tgz" for i in range(3)]
          + ["uploads/archive/bookstack_export_keepme.tgz"])
    S3CompatibleArchiver(_provider(prefix="uploads", keep_last=1)).clean_up(".tgz")
    keys = {o["Key"] for o in
            client.list_objects_v2(Bucket="test-bucket").get("Contents", [])}
    assert "uploads/archive/bookstack_export_keepme.tgz" in keys
    assert len([k for k in keys if k.startswith("uploads/bookstack_export_")]) == 1
