# pylint: disable=missing-function-docstring
"""Tests for the legacy/removed config-key guard (check_legacy_keys)."""
import logging

import pytest

from bookstack_file_exporter.config_helper.config_helper import check_legacy_keys

_LOGGER = "bookstack_file_exporter.config_helper.config_helper"


def test_minio_without_object_storage_raises():
    raw = {"minio": {"host": "minio.local", "bucket": "b"}}
    with pytest.raises(ValueError, match="was removed in v3"):
        check_legacy_keys(raw)


def test_minio_with_object_storage_warns_not_raises(caplog):
    raw = {"minio": {"host": "x"}, "object_storage": [{"type": "minio", "bucket": "b"}]}
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        check_legacy_keys(raw)  # must NOT raise
    assert any("minio" in r.message and "ignored" in r.message.lower()
               for r in caplog.records if r.name == _LOGGER)


def test_minio_with_empty_object_storage_raises():
    # empty list is not a real replacement -> would silently drop backups; must fail loud
    raw = {"minio": {"host": "x"}, "object_storage": []}
    with pytest.raises(ValueError, match="was removed in v3"):
        check_legacy_keys(raw)


def test_modify_markdown_warns(caplog):
    raw = {"assets": {"modify_markdown": True}}
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        check_legacy_keys(raw)  # must NOT raise (alias still honored)
    assert any("DEPRECATED" in r.message and "modify_markdown" in r.message
               for r in caplog.records if r.name == _LOGGER)


def test_clean_config_no_warning_no_error(caplog):
    raw = {"host": "https://x", "formats": ["markdown"],
           "object_storage": [{"type": "s3", "bucket": "b", "region": "us-east-1"}]}
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        check_legacy_keys(raw)
    assert not [r for r in caplog.records if r.name == _LOGGER]


def test_non_dict_assets_does_not_crash():
    # e.g. `assets: true` — let pydantic produce the real error later, don't blow up here
    check_legacy_keys({"assets": True})
