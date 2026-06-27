# pylint: disable=missing-function-docstring,protected-access
"""Tests for credential resolution precedence and endpoint defaulting."""
from minio.credentials import (
    StaticProvider, ChainedProvider, EnvMinioProvider,
    EnvAWSProvider, IamAwsProvider,
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


def test_inline_used_when_no_env_names(monkeypatch):
    monkeypatch.delenv("MINIO_ACCESS_KEY", raising=False)
    monkeypatch.delenv("MINIO_SECRET_KEY", raising=False)
    entry = _entry(access_key="inline-ak", secret_key="inline-sk")
    assert _resolve_credentials(entry).retrieve().access_key == "inline-ak"


def test_minio_ambient_env_beats_inline(monkeypatch):
    monkeypatch.setenv("MINIO_ACCESS_KEY", "env-ak")
    monkeypatch.setenv("MINIO_SECRET_KEY", "env-sk")
    entry = _entry(access_key="inline-ak", secret_key="inline-sk")
    assert _resolve_credentials(entry).retrieve().access_key == "env-ak"


def test_s3_ambient_env_beats_inline(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "env-ak")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "env-sk")
    entry = BaseStorageConfig(type="s3", bucket="b", region="us-east-1",
                              access_key="inline-ak", secret_key="inline-sk")
    assert _resolve_credentials(entry).retrieve().access_key == "env-ak"


def test_s3_inline_beats_imds_when_env_unset(monkeypatch):
    # With AWS_* env unset, inline StaticProvider precedes IamAwsProvider in the chain
    # and short-circuits — retrieve() returns the inline key without any network/IMDS call.
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_ACCESS_KEY", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    entry = BaseStorageConfig(type="s3", bucket="b", region="us-east-1",
                              access_key="inline-ak", secret_key="inline-sk")
    assert _resolve_credentials(entry).retrieve().access_key == "inline-ak"


def test_s3_bare_uses_aws_chain():
    # Chain must be [EnvAWSProvider, IamAwsProvider] — no ~/.aws file tier.
    entry = BaseStorageConfig(type="s3", bucket="b", region="us-east-1")
    provider = _resolve_credentials(entry)
    assert isinstance(provider, ChainedProvider)
    types = [type(p) for p in provider._providers]
    assert types == [EnvAWSProvider, IamAwsProvider]


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
