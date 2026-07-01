# pylint: disable=missing-function-docstring,missing-class-docstring
from bookstack_file_exporter.config_helper.models import S3StorageConfig
from bookstack_file_exporter.config_helper.remote import S3ProviderConfig


def test_holds_boto3_ready_values():
    entry = S3StorageConfig(name="minio-main", bucket="b", prefix="daily", keep_last=5,
                            endpoint="minio.local:9000", secure=False,
                            access_key="a", secret_key="s")
    p = S3ProviderConfig(entry)
    assert p.name == "minio-main"
    assert p.bucket == "b" and p.prefix == "daily" and p.keep_last == 5
    assert p.endpoint_url == "http://minio.local:9000"
    assert p.region == "us-east-1"                  # endpoint set, no explicit region
    assert p.addressing_style == "path"             # inferred from endpoint
    assert p.access_key == "a" and p.secret_key == "s"


def test_ambient_holder_has_none_keys():
    entry = S3StorageConfig(name="aws", bucket="b", prefix="", keep_last=0,
                            region="us-east-1", ambient_auth=True)
    p = S3ProviderConfig(entry)
    assert p.name == "aws" and p.bucket == "b" and p.prefix == "" and p.keep_last == 0
    assert p.endpoint_url is None
    assert p.region == "us-east-1"
    assert p.addressing_style == "auto"             # no endpoint => virtual-hosted
    assert p.access_key is None and p.secret_key is None
