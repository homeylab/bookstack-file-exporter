# pylint: disable=missing-function-docstring
"""Unit tests for BaseStorageConfig and UserInput.object_storage parsing."""
import pytest
from pydantic import ValidationError

from bookstack_file_exporter.config_helper import models


def _entry(**overrides):
    base = {"type": "minio", "bucket": "b", "host": "minio.local"}
    base.update(overrides)
    return base


def test_minio_entry_defaults():
    cfg = models.BaseStorageConfig(**_entry())
    assert cfg.type == "minio"
    assert cfg.bucket == "b"
    assert cfg.secure is True          # TLS default preserves today's behavior
    assert cfg.region is None          # region optional for minio
    assert cfg.keep_last == 0


def test_s3_entry_minimal():
    cfg = models.BaseStorageConfig(type="s3", bucket="aws-b", region="us-east-1")
    assert cfg.type == "s3"
    assert cfg.host == ""              # host optional for s3 (defaulted later from region)


def test_invalid_type_rejected():
    with pytest.raises(ValidationError):
        models.BaseStorageConfig(type="gcs", bucket="b")


def test_inline_cred_half_pair_rejected():
    with pytest.raises(ValidationError, match="access_key and secret_key"):
        models.BaseStorageConfig(**_entry(access_key="AKIA"))  # secret missing


def test_env_name_half_pair_rejected():
    with pytest.raises(ValidationError, match="access_key_env and secret_key_env"):
        models.BaseStorageConfig(**_entry(access_key_env="A_ENV"))  # secret env missing


def test_full_inline_pair_ok():
    cfg = models.BaseStorageConfig(**_entry(access_key="AKIA", secret_key="wJal"))
    assert cfg.access_key == "AKIA"
    assert cfg.secret_key == "wJal"


def test_userinput_parses_object_storage_list():
    raw = {
        "host": "https://wiki.example.com",
        "formats": ["markdown"],
        "object_storage": [
            {"type": "minio", "bucket": "b1", "host": "minio.local"},
            {"type": "s3", "bucket": "b2", "region": "us-east-1"},
        ],
    }
    ui = models.UserInput(**raw)
    assert ui.object_storage is not None
    # pylint: disable-next=not-an-iterable
    assert [e.type for e in ui.object_storage] == ["minio", "s3"]


def test_userinput_object_storage_defaults_none():
    ui = models.UserInput(host="https://x", formats=["markdown"])
    assert ui.object_storage is None
