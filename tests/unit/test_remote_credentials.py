# pylint: disable=missing-function-docstring
import pytest
from bookstack_file_exporter.config_helper.models import S3StorageConfig
from bookstack_file_exporter.config_helper.remote import S3ProviderConfig


def _entry(**kw):
    base = dict(name="t", bucket="b", endpoint="minio.local:9000",
                access_key="a", secret_key="s")
    base.update(kw)
    return S3StorageConfig(**base)


def test_env_name_creds(monkeypatch):
    monkeypatch.setenv("AK", "v1"); monkeypatch.setenv("SK", "v2")
    e = _entry(access_key="", secret_key="", access_key_env="AK", secret_key_env="SK")
    assert S3ProviderConfig._resolve_credentials(e) == ("v1", "v2")

def test_env_names_unset_raises(monkeypatch):
    monkeypatch.delenv("AK", raising=False); monkeypatch.delenv("SK", raising=False)
    e = _entry(access_key="", secret_key="", access_key_env="AK", secret_key_env="SK")
    with pytest.raises(ValueError):
        S3ProviderConfig._resolve_credentials(e)

def test_inline_creds():
    assert S3ProviderConfig._resolve_credentials(_entry()) == ("a", "s")

def test_ambient_returns_none():
    e = S3StorageConfig(name="t", bucket="b", region="us-east-1", ambient_auth=True)
    assert S3ProviderConfig._resolve_credentials(e) == (None, None)

def test_endpoint_url_scheme_from_secure():
    assert S3ProviderConfig._resolve_endpoint_url(_entry(secure=True)) == "https://minio.local:9000"
    assert S3ProviderConfig._resolve_endpoint_url(_entry(secure=False)) == "http://minio.local:9000"

def test_endpoint_url_none_without_endpoint():
    e = S3StorageConfig(name="t", bucket="b", region="us-east-1", ambient_auth=True)
    assert S3ProviderConfig._resolve_endpoint_url(e) is None

def test_region_default_us_east_1_when_endpoint_set():
    assert S3ProviderConfig._resolve_region(_entry(region=None)) == "us-east-1"
    assert S3ProviderConfig._resolve_region(_entry(region="eu-west-1")) == "eu-west-1"

def test_region_none_for_aws_ambient():
    e = S3StorageConfig(name="t", bucket="b", region=None, ambient_auth=True)
    assert S3ProviderConfig._resolve_region(e) is None

def test_addressing_inferred_and_overridden():
    assert S3ProviderConfig._resolve_addressing(_entry()) == "path"          # endpoint set
    assert S3ProviderConfig._resolve_addressing(
        _entry(addressing_style="virtual")) == "virtual"                     # pass-through
    e = S3StorageConfig(name="t", bucket="b", region="us-east-1", ambient_auth=True)
    assert S3ProviderConfig._resolve_addressing(e) == "auto"                 # no endpoint
    assert S3ProviderConfig._resolve_addressing(S3StorageConfig(
        name="t", bucket="b", region="us-east-1", ambient_auth=True,
        addressing_style="path")) == "path"

def test_construction_wires_all_resolved_fields():
    # custom-store entry: all four resolvers should wire together on the instance
    provider = S3ProviderConfig(_entry(secure=True))
    assert provider.endpoint_url == "https://minio.local:9000"
    assert provider.region == "us-east-1"           # endpoint set, no explicit region
    assert provider.addressing_style == "path"      # inferred from endpoint
    assert (provider.access_key, provider.secret_key) == ("a", "s")
