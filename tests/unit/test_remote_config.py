# pylint: disable=missing-function-docstring,missing-class-docstring
from bookstack_file_exporter.config_helper.remote import S3ProviderConfig


def test_holds_boto3_ready_values(make_storage_entry):
    entry = make_storage_entry(name="minio-main", prefix="daily", keep_last=5, secure=False)
    p = S3ProviderConfig(entry)
    assert p.name == "minio-main"
    assert p.bucket == "b" and p.prefix == "daily" and p.keep_last == 5
    assert p.endpoint_url == "http://minio.local:9000"
    assert p.region == "us-east-1"                  # endpoint set, no explicit region
    assert p.addressing_style == "path"             # inferred from endpoint
    assert p.access_key == "a" and p.secret_key == "s"


def test_ambient_holder_has_none_keys(make_storage_entry):
    entry = make_storage_entry(name="aws", prefix="", keep_last=0,
                                endpoint=None, region="us-east-1", ambient_auth=True,
                                access_key="", secret_key="")
    p = S3ProviderConfig(entry)
    assert p.name == "aws" and p.bucket == "b" and p.prefix == "" and p.keep_last == 0
    assert p.endpoint_url is None
    assert p.region == "us-east-1"
    assert p.addressing_style == "auto"             # no endpoint => virtual-hosted
    assert p.access_key is None and p.secret_key is None


def test_prefix_normalized_at_resolution(make_storage_entry):
    entry = make_storage_entry(prefix="/daily/exports///")
    assert S3ProviderConfig(entry).prefix == "daily/exports"


def test_none_prefix_resolves_empty(make_storage_entry):
    entry = make_storage_entry(prefix=None)
    assert S3ProviderConfig(entry).prefix == ""
