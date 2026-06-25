# pylint: disable=missing-function-docstring,protected-access
"""Tests for credential resolution precedence and endpoint defaulting."""
from minio.credentials import (
    StaticProvider, ChainedProvider, EnvMinioProvider,
)

from bookstack_file_exporter.config_helper.models import BaseStorageConfig
from bookstack_file_exporter.config_helper.config_helper import (
    _resolve_credentials,
    _resolve_endpoint,
)


def _entry(**overrides):
    base = {"type": "minio", "bucket": "b", "host": "minio.local"}
    base.update(overrides)
    return BaseStorageConfig(**base)


def test_per_entry_env_names_win(monkeypatch):
    monkeypatch.setenv("M2_AK", "ak-env")
    monkeypatch.setenv("M2_SK", "sk-env")
    entry = _entry(access_key="inline-ak", secret_key="inline-sk",
                   access_key_env="M2_AK", secret_key_env="M2_SK")
    provider = _resolve_credentials(entry)
    assert isinstance(provider, StaticProvider)
    creds = provider.retrieve()
    assert creds.access_key == "ak-env"      # env names beat inline
    assert creds.secret_key == "sk-env"


def test_per_entry_env_names_unset_raises(monkeypatch):
    monkeypatch.delenv("MISSING_AK", raising=False)
    monkeypatch.delenv("MISSING_SK", raising=False)
    entry = _entry(access_key_env="MISSING_AK", secret_key_env="MISSING_SK")
    try:
        _resolve_credentials(entry)
        assert False, "expected ValueError for unset referenced env vars"
    except ValueError as err:
        assert "MISSING_AK" in str(err)


def test_inline_used_when_no_env_names():
    entry = _entry(access_key="inline-ak", secret_key="inline-sk")
    provider = _resolve_credentials(entry)
    assert isinstance(provider, StaticProvider)
    assert provider.retrieve().access_key == "inline-ak"


def test_s3_bare_uses_aws_chain():
    entry = BaseStorageConfig(type="s3", bucket="b", region="us-east-1")
    assert isinstance(_resolve_credentials(entry), ChainedProvider)


def test_minio_bare_uses_env_minio_provider():
    entry = _entry()  # no creds at all
    assert isinstance(_resolve_credentials(entry), EnvMinioProvider)


def test_endpoint_uses_explicit_host():
    entry = BaseStorageConfig(type="s3", bucket="b", region="us-east-1",
                              host="custom.example.com")
    assert _resolve_endpoint(entry) == "custom.example.com"


def test_endpoint_s3_defaults_from_region():
    entry = BaseStorageConfig(type="s3", bucket="b", region="eu-west-1")
    assert _resolve_endpoint(entry) == "s3.eu-west-1.amazonaws.com"


def test_endpoint_minio_empty_when_no_host():
    entry = BaseStorageConfig(type="minio", bucket="b", host="")
    assert _resolve_endpoint(entry) == ""
