# pylint: disable=missing-function-docstring,missing-class-docstring
from bookstack_file_exporter.config_helper.remote import StorageProviderConfig
from bookstack_file_exporter.config_helper.models import BaseStorageConfig


def test_holds_boto3_ready_values():
    cfg = BaseStorageConfig(name="t", bucket="b", endpoint="minio.local:9000",
                            access_key="a", secret_key="s")
    p = StorageProviderConfig(endpoint_url="http://minio.local:9000", region="us-east-1",
                              addressing_style="path", access_key="a", secret_key="s", config=cfg)
    assert p.endpoint_url == "http://minio.local:9000"
    assert p.region == "us-east-1"
    assert p.addressing_style == "path"
    assert p.access_key == "a" and p.secret_key == "s"
    assert p.config is cfg


def test_ambient_holder_has_none_keys():
    cfg = BaseStorageConfig(name="t", bucket="b", region="us-east-1", ambient_auth=True)
    p = StorageProviderConfig(endpoint_url=None, region="us-east-1", addressing_style="auto",
                              access_key=None, secret_key=None, config=cfg)
    assert p.access_key is None and p.endpoint_url is None
