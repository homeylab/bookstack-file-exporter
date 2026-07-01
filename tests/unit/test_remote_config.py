# pylint: disable=missing-function-docstring,missing-class-docstring
from bookstack_file_exporter.config_helper.remote import StorageProviderConfig


def test_holds_boto3_ready_values():
    p = StorageProviderConfig(name="minio-main", bucket="b", prefix="daily", keep_last=5,
                              endpoint_url="http://minio.local:9000", region="us-east-1",
                              addressing_style="path", access_key="a", secret_key="s")
    assert p.name == "minio-main"
    assert p.bucket == "b" and p.prefix == "daily" and p.keep_last == 5
    assert p.endpoint_url == "http://minio.local:9000"
    assert p.region == "us-east-1"
    assert p.addressing_style == "path"
    assert p.access_key == "a" and p.secret_key == "s"


def test_ambient_holder_has_none_keys():
    p = StorageProviderConfig(name="aws", bucket="b", prefix="", keep_last=0,
                              endpoint_url=None, region="us-east-1", addressing_style="auto",
                              access_key=None, secret_key=None)
    assert p.access_key is None and p.endpoint_url is None
