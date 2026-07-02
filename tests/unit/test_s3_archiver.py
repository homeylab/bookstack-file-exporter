# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name
# pylint: disable=protected-access
import boto3
import pytest
from moto import mock_aws

from bookstack_file_exporter.archiver.s3_archiver import S3CompatibleArchiver


@pytest.fixture
def provider(make_provider):
    def _make(bucket="test-bucket", prefix=None, keep_last=0):
        return make_provider(name="t", bucket=bucket, prefix=prefix or "",
                             endpoint=None, region="us-east-1", ambient_auth=True,
                             access_key="", secret_key="", keep_last=keep_last)
    return _make


@pytest.fixture
def aws(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
        yield


def test_upload_returns_bucket_slash_object_with_prefix(aws, tmp_path, provider):
    f = tmp_path / "export.tgz"; f.write_bytes(b"data")
    assert S3CompatibleArchiver(provider(prefix="backups/2024")).upload_backup(str(f)) \
        == "test-bucket/backups/2024/export.tgz"


def test_upload_returns_bucket_slash_filename_without_prefix(aws, tmp_path, provider):
    f = tmp_path / "export.tgz"; f.write_bytes(b"data")
    assert S3CompatibleArchiver(provider()).upload_backup(str(f)) == "test-bucket/export.tgz"


def test_upload_puts_object(aws, tmp_path, provider):
    f = tmp_path / "archive.tgz"; f.write_bytes(b"xyz")
    S3CompatibleArchiver(provider(prefix="uploads")).upload_backup(str(f))
    keys = [o["Key"] for o in
            boto3.client("s3", region_name="us-east-1").list_objects_v2(Bucket="test-bucket").get("Contents", [])]
    assert "uploads/archive.tgz" in keys


def test_validate_bucket_raises_when_missing(aws, provider):
    with pytest.raises(ValueError):
        S3CompatibleArchiver(provider(bucket="nope"))


def test_validate_bucket_wraps_endpoint_connection_error(monkeypatch, provider):
    from unittest.mock import MagicMock
    from botocore.exceptions import EndpointConnectionError
    fake = MagicMock()
    fake.head_bucket.side_effect = EndpointConnectionError(endpoint_url="http://unreachable:9000")
    monkeypatch.setattr("boto3.session.Session.client", lambda self, *a, **k: fake)
    with pytest.raises(ValueError):
        S3CompatibleArchiver(provider())


def test_validate_bucket_404_raises(monkeypatch, provider):
    # definitively-missing bucket: hard fail before an export runs
    from unittest.mock import MagicMock
    from botocore.exceptions import ClientError
    err = ClientError(
        {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}}, "HeadBucket")
    fake = MagicMock()
    fake.head_bucket.side_effect = err
    monkeypatch.setattr("boto3.session.Session.client", lambda self, *a, **k: fake)
    with pytest.raises(ValueError):
        S3CompatibleArchiver(provider())


def test_validate_bucket_403_warns_and_proceeds(monkeypatch, caplog, provider):
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
        arch = S3CompatibleArchiver(provider())  # must not raise
    assert arch.bucket == "test-bucket"
    assert "Could not verify bucket" in caplog.text


def test_ambient_none_keys_uses_env_chain(aws, tmp_path, make_provider):
    # provider with access_key=None -> Session(None,None) -> botocore ambient chain (AWS_* env from `aws` fixture)
    prov = make_provider(name="amb", bucket="test-bucket", prefix="",
                          endpoint=None, region="us-east-1", ambient_auth=True,
                          access_key="", secret_key="")
    f = tmp_path / "export.tgz"; f.write_bytes(b"data")
    assert S3CompatibleArchiver(prov).upload_backup(str(f)) == "test-bucket/export.tgz"


def _seed(client, bucket, keys):
    for k in keys:
        client.put_object(Bucket=bucket, Key=k, Body=b"x")


def test_clean_up_deletes_oldest_beyond_keep_last(aws, provider):
    client = boto3.client("s3", region_name="us-east-1")
    _seed(client, "test-bucket", [f"uploads/bookstack_export_{i}.tgz" for i in range(5)])
    S3CompatibleArchiver(provider(prefix="uploads", keep_last=2)).clean_up(".tgz")
    remaining = client.list_objects_v2(Bucket="test-bucket").get("Contents", [])
    assert len(remaining) == 2


def test_clean_up_keep_last_zero_deletes_nothing(aws, provider):
    client = boto3.client("s3", region_name="us-east-1")
    _seed(client, "test-bucket", ["uploads/bookstack_export_1.tgz", "uploads/unrelated.tgz"])
    S3CompatibleArchiver(provider(prefix="uploads", keep_last=0)).clean_up(".tgz")
    assert len(client.list_objects_v2(Bucket="test-bucket").get("Contents", [])) == 2


def test_scan_paginates_beyond_1000(aws, provider):
    client = boto3.client("s3", region_name="us-east-1")
    _seed(client, "test-bucket", [f"bookstack_export_{i:04d}.tgz" for i in range(1001)])
    assert len(S3CompatibleArchiver(provider(prefix=None, keep_last=1))._scan_objects(".tgz")) == 1001


def test_filter_objects_keeps_newest_by_lastmodified(aws, provider):
    from datetime import datetime, timezone
    arch = S3CompatibleArchiver(provider(keep_last=2))
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


def test_clean_up_preserves_unmanaged_objects(aws, provider):
    client = boto3.client("s3", region_name="us-east-1")
    _seed(client, "test-bucket",
          [f"uploads/bookstack_export_{i}.tgz" for i in range(3)] + ["uploads/unrelated.tgz"])
    S3CompatibleArchiver(provider(prefix="uploads", keep_last=1)).clean_up(".tgz")
    keys = {o["Key"] for o in client.list_objects_v2(Bucket="test-bucket").get("Contents", [])}
    assert "uploads/unrelated.tgz" in keys          # non-managed object never a deletion candidate
    assert len([k for k in keys if "bookstack_export_" in k]) == 1  # 3 managed -> keep_last=1


def test_scan_ignores_nested_keys(aws, provider):
    # v2.3.0 minio-py listed non-recursively; nested "subfolders" under the
    # prefix are user-managed space and must never be retention candidates
    client = boto3.client("s3", region_name="us-east-1")
    _seed(client, "test-bucket", ["uploads/bookstack_export_1.tgz",
                                  "uploads/archive/bookstack_export_2.tgz"])
    arch = S3CompatibleArchiver(provider(prefix="uploads", keep_last=1))
    keys = [o["Key"] for o in arch._scan_objects(".tgz")]
    assert keys == ["uploads/bookstack_export_1.tgz"]


def test_clean_up_never_deletes_nested_keys(aws, provider):
    client = boto3.client("s3", region_name="us-east-1")
    _seed(client, "test-bucket",
          [f"uploads/bookstack_export_{i}.tgz" for i in range(3)]
          + ["uploads/archive/bookstack_export_keepme.tgz"])
    S3CompatibleArchiver(provider(prefix="uploads", keep_last=1)).clean_up(".tgz")
    keys = {o["Key"] for o in
            client.list_objects_v2(Bucket="test-bucket").get("Contents", [])}
    assert "uploads/archive/bookstack_export_keepme.tgz" in keys
    assert len([k for k in keys if k.startswith("uploads/bookstack_export_")]) == 1


def test_delete_objects_uses_batch_api(aws, provider):
    from unittest.mock import patch
    client = boto3.client("s3", region_name="us-east-1")
    _seed(client, "test-bucket", [f"uploads/bookstack_export_{i}.tgz" for i in range(3)])
    arch = S3CompatibleArchiver(provider(prefix="uploads", keep_last=1))
    with patch.object(arch._client, "delete_objects",
                      wraps=arch._client.delete_objects) as spy:
        arch.clean_up(".tgz")
    assert spy.call_count == 1          # one batch call, not one per key
    remaining = {o["Key"] for o in
                 client.list_objects_v2(Bucket="test-bucket").get("Contents", [])}
    assert len(remaining) == 1


def test_delete_objects_raises_on_partial_errors(aws, provider):
    from unittest.mock import patch
    arch = S3CompatibleArchiver(provider(prefix="uploads", keep_last=1))
    with patch.object(arch._client, "delete_objects",
                      return_value={"Errors": [{"Key": "uploads/bad.tgz",
                                                 "Code": "AccessDenied"}]}):
        with pytest.raises(ValueError) as exc:
            arch._delete_objects([{"Key": "uploads/bad.tgz"}])
    assert "uploads/bad.tgz" in str(exc.value)


def test_scan_ignores_lookalike_user_objects(aws, provider):
    # substring 'bookstack_export_' in a USER-named object must not make it a retention
    # candidate; only basenames that START with the managed marker are ours to delete
    client = boto3.client("s3", region_name="us-east-1")
    _seed(client, "test-bucket", ["uploads/bookstack_export_1.tgz",
                                  "uploads/my_bookstack_export_copy.tgz"])
    arch = S3CompatibleArchiver(provider(prefix="uploads", keep_last=1))
    keys = [o["Key"] for o in arch._scan_objects(".tgz")]
    assert keys == ["uploads/bookstack_export_1.tgz"]
