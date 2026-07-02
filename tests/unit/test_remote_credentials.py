# pylint: disable=missing-function-docstring
# protected-access: deliberately unit-tests the private _resolve_* rules one by one;
# public-surface (constructor) coverage lives in test_remote_config.py
# pylint: disable=protected-access
import pytest
from bookstack_file_exporter.config_helper.remote import S3ProviderConfig


def test_env_name_creds(monkeypatch, make_storage_entry):
    monkeypatch.setenv("AK", "v1")
    monkeypatch.setenv("SK", "v2")
    e = make_storage_entry(access_key="", secret_key="", access_key_env="AK", secret_key_env="SK")
    assert S3ProviderConfig._resolve_credentials(e) == ("v1", "v2")

def test_env_names_unset_raises(monkeypatch, make_storage_entry):
    monkeypatch.delenv("AK", raising=False)
    monkeypatch.delenv("SK", raising=False)
    e = make_storage_entry(access_key="", secret_key="", access_key_env="AK", secret_key_env="SK")
    with pytest.raises(ValueError):
        S3ProviderConfig._resolve_credentials(e)

def test_inline_creds(make_storage_entry):
    assert S3ProviderConfig._resolve_credentials(make_storage_entry()) == ("a", "s")

def test_ambient_returns_none(make_storage_entry):
    e = make_storage_entry(endpoint=None, region="us-east-1", ambient_auth=True,
                            access_key="", secret_key="")
    assert S3ProviderConfig._resolve_credentials(e) == (None, None)

def test_endpoint_url_scheme_from_secure(make_storage_entry):
    assert (S3ProviderConfig._resolve_endpoint_url(make_storage_entry(secure=True))
            == "https://minio.local:9000")
    assert (S3ProviderConfig._resolve_endpoint_url(make_storage_entry(secure=False))
            == "http://minio.local:9000")

def test_endpoint_url_none_without_endpoint(make_storage_entry):
    e = make_storage_entry(endpoint=None, region="us-east-1", ambient_auth=True,
                            access_key="", secret_key="")
    assert S3ProviderConfig._resolve_endpoint_url(e) is None

def test_region_default_us_east_1_when_endpoint_set(make_storage_entry):
    assert S3ProviderConfig._resolve_region(make_storage_entry(region=None)) == "us-east-1"
    assert S3ProviderConfig._resolve_region(make_storage_entry(region="eu-west-1")) == "eu-west-1"

def test_region_none_for_aws_ambient(make_storage_entry):
    e = make_storage_entry(endpoint=None, region=None, ambient_auth=True,
                            access_key="", secret_key="")
    assert S3ProviderConfig._resolve_region(e) is None

def test_addressing_inferred_and_overridden(make_storage_entry):
    assert S3ProviderConfig._resolve_addressing(make_storage_entry()) == "path"  # endpoint set
    assert S3ProviderConfig._resolve_addressing(
        make_storage_entry(addressing_style="virtual")) == "virtual"  # pass-through
    e = make_storage_entry(endpoint=None, region="us-east-1", ambient_auth=True,
                            access_key="", secret_key="")
    assert S3ProviderConfig._resolve_addressing(e) == "auto"                 # no endpoint
    assert S3ProviderConfig._resolve_addressing(make_storage_entry(
        endpoint=None, region="us-east-1", ambient_auth=True,
        access_key="", secret_key="", addressing_style="path")) == "path"
