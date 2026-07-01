# pylint: disable=missing-function-docstring
"""Tests for legacy/removed config-key handling.

Deprecated/removed keys are now handled inside the pydantic models (Assets and
UserInput before-validators), exercised here through build_user_input:
  - REMOVED 'minio:' -> hard error on ANY presence (deprecated != removed; it no
    longer does anything, so warning would be misleading)
  - DEPRECATED 'assets.modify_markdown' -> warn only (value still honored via alias)
"""
import logging

import pytest
from pydantic import ValidationError

from bookstack_file_exporter.config_helper.config_helper import build_user_input

# warnings now originate from the models module, not config_helper
_LOGGER = "bookstack_file_exporter.config_helper.models"

_VALID_OBJ = {"name": "minio-main", "bucket": "b", "endpoint": "minio.local",
              "access_key": "a", "secret_key": "s"}


def _raw(**overrides):
    base = {"host": "https://wiki.example.com", "formats": ["markdown"]}
    base.update(overrides)
    return base


def test_minio_without_object_storage_raises():
    raw = _raw(minio={"host": "minio.local", "bucket": "b"})
    with pytest.raises(ValidationError, match="was removed in v3"):
        build_user_input(raw)


def test_minio_alongside_valid_object_storage_still_raises():
    # removed key is an error even next to a working object_storage block: a removed
    # key does nothing, so warn-and-continue would be misleading. Force a clean config.
    raw = _raw(minio={"host": "x"}, object_storage=[_VALID_OBJ])
    with pytest.raises(ValidationError, match="was removed in v3"):
        build_user_input(raw)


def test_modify_markdown_warns(caplog):
    raw = _raw(assets={"modify_markdown": True})
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        build_user_input(raw)  # must NOT raise (alias still honors the value)
    assert any("DEPRECATED" in r.message and "modify_markdown" in r.message
               for r in caplog.records if r.name == _LOGGER)


def test_clean_config_no_warning_no_error(caplog):
    raw = _raw(object_storage=[{"name": "s3-main", "bucket": "b", "region": "us-east-1",
                                 "access_key": "a", "secret_key": "s"}])
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        build_user_input(raw)
    assert not [r for r in caplog.records if r.name == _LOGGER]
