# pylint: disable=missing-function-docstring
"""Unit tests for BaseStorageConfig and UserInput.object_storage parsing."""
import pytest
from pydantic import ValidationError

from bookstack_file_exporter.config_helper.models import BaseStorageConfig, UserInput


def _entry(**overrides):
    base = {"name": "primary", "bucket": "b", "endpoint": "minio.local"}
    base.update(overrides)
    return base


def test_entry_defaults():
    cfg = BaseStorageConfig(**_entry())
    assert cfg.bucket == "b"
    assert cfg.secure is True          # TLS default preserves today's behavior
    assert cfg.region is None          # region optional
    assert cfg.keep_last == 0


def test_inline_cred_half_pair_rejected():
    with pytest.raises(ValidationError, match="access_key and secret_key"):
        BaseStorageConfig(**_entry(access_key="AKIA"))  # secret missing


def test_env_name_half_pair_rejected():
    with pytest.raises(ValidationError, match="access_key_env and secret_key_env"):
        BaseStorageConfig(**_entry(access_key_env="A_ENV"))  # secret env missing


def test_full_inline_pair_ok():
    cfg = BaseStorageConfig(**_entry(access_key="AKIA", secret_key="wJal"))
    assert cfg.access_key == "AKIA"
    assert cfg.secret_key == "wJal"


def test_userinput_parses_object_storage_list():
    raw = {
        "host": "https://wiki.example.com",
        "formats": ["markdown"],
        "object_storage": [
            {"name": "one", "bucket": "b1", "endpoint": "minio.local"},
            {"name": "two", "bucket": "b2", "region": "us-east-1"},
        ],
    }
    ui = UserInput(**raw)
    assert ui.object_storage is not None
    # pylint: disable-next=not-an-iterable
    assert [e.name for e in ui.object_storage] == ["one", "two"]


def test_userinput_object_storage_defaults_none():
    ui = UserInput(host="https://x", formats=["markdown"])
    assert ui.object_storage is None


# --- name (required) and label property ---

def test_name_required():
    with pytest.raises(ValidationError):
        BaseStorageConfig(bucket="b", endpoint="h", access_key="a", secret_key="s")


def test_label_is_name():
    cfg = BaseStorageConfig(name="minio-main", bucket="b", endpoint="h",
                            access_key="a", secret_key="s")
    assert cfg.label == "minio-main"


def test_endpoint_and_prefix_fields():
    cfg = BaseStorageConfig(name="t", bucket="b", endpoint="minio.local:9000",
                            prefix="daily", access_key="a", secret_key="s")
    assert cfg.endpoint == "minio.local:9000"
    assert cfg.prefix == "daily"


def test_ambient_auth_defaults_false_and_settable():
    assert BaseStorageConfig(name="t", bucket="b", ambient_auth=True,
                             region="us-east-1").ambient_auth is True
    assert BaseStorageConfig(name="t", bucket="b", endpoint="h",
                             access_key="a", secret_key="s").ambient_auth is False


def test_force_path_style_default_none():
    cfg = BaseStorageConfig(name="t", bucket="b", endpoint="h",
                            access_key="a", secret_key="s")
    assert cfg.force_path_style is None


# --- UserInput name-uniqueness validator ---

def _user_input(*entries):
    return {
        "host": "https://wiki.example.com",
        "formats": ["markdown"],
        "object_storage": list(entries),
    }


def test_duplicate_name_raises():
    e1 = _entry(name="same", bucket="b1")
    e2 = _entry(name="same", bucket="b2")
    with pytest.raises(ValidationError, match="name"):
        UserInput(**_user_input(e1, e2))


def test_distinct_names_ok():
    e1 = _entry(name="primary", bucket="b1")
    e2 = _entry(name="secondary", bucket="b2")
    ui = UserInput(**_user_input(e1, e2))
    assert ui.object_storage is not None
    # pylint: disable-next=not-an-iterable
    assert len(ui.object_storage) == 2
