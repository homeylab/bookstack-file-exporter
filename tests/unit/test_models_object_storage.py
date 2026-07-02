# pylint: disable=missing-function-docstring
"""Unit tests for S3StorageConfig and UserInput.object_storage parsing."""
import pytest
from pydantic import ValidationError

from bookstack_file_exporter.config_helper.models import S3StorageConfig, UserInput


def _entry(**overrides):
    base = {"name": "primary", "bucket": "b", "endpoint": "minio.local"}
    base.update(overrides)
    return base


def test_entry_defaults():
    cfg = S3StorageConfig(**_entry(access_key="a", secret_key="s"))
    assert cfg.bucket == "b"
    assert cfg.secure is True          # TLS default preserves today's behavior
    assert cfg.region is None          # region optional
    assert cfg.keep_last == 0


def test_inline_cred_half_pair_rejected():
    with pytest.raises(ValidationError, match="access_key and secret_key"):
        S3StorageConfig(**_entry(access_key="AKIA"))  # secret missing


def test_env_name_half_pair_rejected():
    with pytest.raises(ValidationError, match="access_key_env and secret_key_env"):
        S3StorageConfig(**_entry(access_key_env="A_ENV"))  # secret env missing


def test_full_inline_pair_ok():
    cfg = S3StorageConfig(**_entry(access_key="AKIA", secret_key="wJal"))
    assert cfg.access_key == "AKIA"
    assert cfg.secret_key == "wJal"


def test_userinput_parses_object_storage_list():
    raw = {
        "host": "https://wiki.example.com",
        "formats": ["markdown"],
        "object_storage": [
            {"name": "one", "bucket": "b1", "endpoint": "minio.local",
             "access_key": "a", "secret_key": "s"},
            {"name": "two", "bucket": "b2", "region": "us-east-1",
             "access_key": "a", "secret_key": "s"},
        ],
    }
    ui = UserInput(**raw)
    assert ui.object_storage is not None
    # pylint: disable-next=not-an-iterable
    assert [e.name for e in ui.object_storage] == ["one", "two"]


def test_userinput_object_storage_defaults_none():
    ui = UserInput(host="https://x", formats=["markdown"])
    assert ui.object_storage is None


# --- name (required) ---

def test_name_required():
    with pytest.raises(ValidationError):
        S3StorageConfig(bucket="b", endpoint="h", access_key="a", secret_key="s")


def test_endpoint_and_prefix_fields():
    cfg = S3StorageConfig(name="t", bucket="b", endpoint="minio.local:9000",
                            prefix="daily", access_key="a", secret_key="s")
    assert cfg.endpoint == "minio.local:9000"
    assert cfg.prefix == "daily"


def test_ambient_auth_defaults_false_and_settable():
    assert S3StorageConfig(name="t", bucket="b", ambient_auth=True,
                             region="us-east-1").ambient_auth is True
    assert S3StorageConfig(name="t", bucket="b", endpoint="h",
                             access_key="a", secret_key="s").ambient_auth is False


def test_addressing_style_default_none_and_validated():
    cfg = S3StorageConfig(name="t", bucket="b", endpoint="h",
                            access_key="a", secret_key="s")
    assert cfg.addressing_style is None
    with pytest.raises(ValidationError):
        S3StorageConfig(name="t", bucket="b", endpoint="h", access_key="a",
                          secret_key="s", addressing_style="pathy")


# --- UserInput name-uniqueness validator ---

def _user_input(*entries):
    return {
        "host": "https://wiki.example.com",
        "formats": ["markdown"],
        "object_storage": list(entries),
    }


def test_duplicate_name_raises():
    e1 = _entry(name="same", bucket="b1", access_key="a", secret_key="s")
    e2 = _entry(name="same", bucket="b2", access_key="a", secret_key="s")
    with pytest.raises(ValidationError, match="Duplicate object_storage name"):
        UserInput(**_user_input(e1, e2))


def test_distinct_names_ok():
    e1 = _entry(name="primary", bucket="b1", access_key="a", secret_key="s")
    e2 = _entry(name="secondary", bucket="b2", access_key="a", secret_key="s")
    ui = UserInput(**_user_input(e1, e2))
    assert ui.object_storage is not None
    # pylint: disable-next=not-an-iterable
    assert len(ui.object_storage) == 2


# --- UserInput duplicate-destination warning ---

def test_same_destination_different_names_warns(caplog):
    import logging
    e1 = _entry(name="a", prefix="daily/", access_key="a", secret_key="s")
    e2 = _entry(name="b", prefix="daily", access_key="a2", secret_key="s2")
    with caplog.at_level(logging.WARNING):
        UserInput(**_user_input(e1, e2))
    assert "same destination" in caplog.text


def test_distinct_destinations_no_warning(caplog):
    import logging
    e1 = _entry(name="a", prefix="daily", access_key="a", secret_key="s")
    e2 = _entry(name="b", prefix="weekly", access_key="a", secret_key="s")
    with caplog.at_level(logging.WARNING):
        UserInput(**_user_input(e1, e2))
    assert "same destination" not in caplog.text


# --- Task 2b: fail-closed creds + region + reject-legacy-type validators ---

def test_no_creds_and_no_ambient_is_error():
    with pytest.raises(ValidationError):
        S3StorageConfig(name="t", bucket="b", endpoint="h")  # fail-closed


def test_ambient_auth_allows_no_creds():
    cfg = S3StorageConfig(name="t", bucket="b", region="us-east-1", ambient_auth=True)
    assert cfg.ambient_auth is True


def test_explicit_env_names_satisfy_creds():
    cfg = S3StorageConfig(name="t", bucket="b", endpoint="h",
                            access_key_env="AK", secret_key_env="SK")
    assert cfg.access_key_env == "AK"


def test_aws_target_requires_region_without_ambient():
    with pytest.raises(ValidationError):
        # no endpoint (AWS), inline creds, but no region and no ambient
        S3StorageConfig(name="t", bucket="b", access_key="a", secret_key="s")


def test_aws_target_region_optional_under_ambient():
    cfg = S3StorageConfig(name="t", bucket="b", ambient_auth=True)  # botocore resolves region
    assert cfg.region is None


def test_renamed_host_key_rejected():
    with pytest.raises(ValidationError) as exc:
        S3StorageConfig(name="t", host="minio.local", bucket="b",
                          access_key="a", secret_key="s")
    assert "endpoint" in str(exc.value).lower()


def test_renamed_path_key_rejected():
    with pytest.raises(ValidationError) as exc:
        S3StorageConfig(name="t", path="daily", bucket="b", endpoint="h",
                          access_key="a", secret_key="s")
    assert "prefix" in str(exc.value).lower()


def test_endpoint_with_scheme_rejected():
    with pytest.raises(ValidationError) as exc:
        S3StorageConfig(name="t", endpoint="https://minio.local", bucket="b",
                          access_key="a", secret_key="s")
    assert "scheme" in str(exc.value).lower()


# --- Task 5: extra="forbid" on all config models ---

def test_unknown_entry_key_rejected():
    with pytest.raises(ValidationError) as exc:
        S3StorageConfig(**_entry(access_key="a", secret_key="s", keeplast=5))
    assert "keeplast" in str(exc.value)


def test_unknown_top_level_key_rejected():
    raw = _user_input(_entry(access_key="a", secret_key="s"))
    raw["export_workres"] = 2
    with pytest.raises(ValidationError) as exc:
        UserInput(**raw)
    assert "export_workres" in str(exc.value)


def test_unknown_nested_key_rejected():
    raw = _user_input(_entry(access_key="a", secret_key="s"))
    raw["http_config"] = {"timout": 5}
    with pytest.raises(ValidationError) as exc:
        UserInput(**raw)
    assert "timout" in str(exc.value)
