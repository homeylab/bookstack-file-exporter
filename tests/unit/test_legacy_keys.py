# pylint: disable=missing-function-docstring
"""Tests for legacy/removed config-key handling.

Deprecated/removed keys are now handled inside the pydantic models (Assets and
UserInput before-validators), exercised here through build_user_input:
  - removed 'minio:' with no usable 'object_storage:' -> hard error (ValidationError)
  - removed 'minio:' alongside a real 'object_storage:' -> warn only (stale leftover)
  - deprecated 'assets.modify_markdown' -> warn only (value still honored via alias)
"""
import logging

import pytest
from pydantic import ValidationError

from bookstack_file_exporter.config_helper.config_helper import build_user_input

# warnings now originate from the models module, not config_helper
_LOGGER = "bookstack_file_exporter.config_helper.models"

_VALID_OBJ = {"type": "minio", "bucket": "b", "host": "minio.local"}


def _raw(**overrides):
    base = {"host": "https://wiki.example.com", "formats": ["markdown"]}
    base.update(overrides)
    return base


def test_minio_without_object_storage_raises():
    raw = _raw(minio={"host": "minio.local", "bucket": "b"})
    with pytest.raises(ValidationError, match="was removed in v3"):
        build_user_input(raw)


def test_minio_with_empty_object_storage_raises():
    # empty list is not a real replacement -> would silently drop backups; must fail loud
    raw = _raw(minio={"host": "x"}, object_storage=[])
    with pytest.raises(ValidationError, match="was removed in v3"):
        build_user_input(raw)


def test_minio_with_object_storage_warns_not_raises(caplog):
    raw = _raw(minio={"host": "x"}, object_storage=[_VALID_OBJ])
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        build_user_input(raw)  # must NOT raise
    assert any("minio" in r.message and "ignored" in r.message.lower()
               for r in caplog.records if r.name == _LOGGER)


def test_modify_markdown_warns(caplog):
    raw = _raw(assets={"modify_markdown": True})
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        build_user_input(raw)  # must NOT raise (alias still honors the value)
    assert any("DEPRECATED" in r.message and "modify_markdown" in r.message
               for r in caplog.records if r.name == _LOGGER)


def test_clean_config_no_warning_no_error(caplog):
    raw = _raw(object_storage=[{"type": "s3", "bucket": "b", "region": "us-east-1"}])
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        build_user_input(raw)
    assert not [r for r in caplog.records if r.name == _LOGGER]
