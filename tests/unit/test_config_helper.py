"""Unit tests for the module-level config parsing seams extracted in R2."""
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from bookstack_file_exporter.config_helper import models
from bookstack_file_exporter.config_helper.config_helper import (
    ConfigNode,
    build_user_input,
    load_yaml_config,
)

# Minimal dict that satisfies UserInput's required fields
_VALID_RAW = {
    "host": "https://wiki.example.com",
    "credentials": {"token_id": "abc", "token_secret": "def"},
    "formats": ["markdown"],
}

# Dict with an invalid value to trigger pydantic ValidationError
_INVALID_RAW = {
    "host": "https://wiki.example.com",
    "formats": "not-a-list",  # must be a list
}


# ---------------------------------------------------------------------------
# load_yaml_config
# ---------------------------------------------------------------------------

def test_load_yaml_config_raises_file_not_found_for_missing_path():
    """load_yaml_config must raise FileNotFoundError for a path that does not exist."""
    with pytest.raises(FileNotFoundError):
        load_yaml_config("/tmp/this-file-absolutely-does-not-exist-xyz.yml")


def test_load_yaml_config_returns_parsed_dict(tmp_path):
    """load_yaml_config returns the YAML content as a dict for a valid file."""
    config_file = tmp_path / "config.yml"
    config_file.write_text(yaml.dump(_VALID_RAW), encoding="utf-8")

    result = load_yaml_config(str(config_file))

    assert isinstance(result, dict)
    assert result["host"] == "https://wiki.example.com"
    assert result["formats"] == ["markdown"]


@pytest.mark.parametrize("content", ["", "   \n  \n"])
def test_load_yaml_config_raises_value_error_on_empty_file(tmp_path, content):
    """An empty / whitespace-only config yields a clear ValueError, not AttributeError."""
    empty = tmp_path / "empty.yml"
    empty.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="empty"):
        load_yaml_config(str(empty))


def test_load_yaml_config_raises_yaml_error_on_invalid_yaml(tmp_path):
    """load_yaml_config must propagate yaml.YAMLError for malformed YAML."""
    bad_yaml = tmp_path / "bad.yml"
    # Tabs are not allowed in YAML indentation; this reliably causes a scanner error.
    bad_yaml.write_text("key:\n\t- broken", encoding="utf-8")

    with pytest.raises(yaml.YAMLError):
        load_yaml_config(str(bad_yaml))


def test_load_yaml_config_logs_error_on_yaml_failure(tmp_path, caplog):
    """load_yaml_config logs an error message before re-raising yaml.YAMLError."""
    bad_yaml = tmp_path / "bad.yml"
    bad_yaml.write_text("key:\n\t- broken", encoding="utf-8")

    logger_name = "bookstack_file_exporter.config_helper.config_helper"
    with caplog.at_level(logging.ERROR, logger=logger_name):
        with pytest.raises(yaml.YAMLError):
            load_yaml_config(str(bad_yaml))

    assert any(
        "Failed to load yaml configuration file" in r.message
        for r in caplog.records
        if r.name == logger_name
    )


# ---------------------------------------------------------------------------
# build_user_input
# ---------------------------------------------------------------------------

def test_build_user_input_returns_user_input_for_valid_dict():
    """build_user_input returns a models.UserInput instance for a valid raw dict."""
    result = build_user_input(dict(_VALID_RAW))

    assert isinstance(result, models.UserInput)
    assert result.host == "https://wiki.example.com"
    assert "markdown" in result.formats


def test_build_user_input_raises_on_invalid_schema():
    """build_user_input raises (pydantic ValidationError) for a dict with bad values."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        build_user_input(dict(_INVALID_RAW))


def test_build_user_input_logs_error_on_schema_failure(caplog):
    """build_user_input logs the schema validation error message before re-raising."""
    from pydantic import ValidationError

    logger_name = "bookstack_file_exporter.config_helper.config_helper"
    with caplog.at_level(logging.ERROR, logger=logger_name):
        with pytest.raises(ValidationError):
            build_user_input(dict(_INVALID_RAW))

    assert any(
        "Yaml configuration failed schema validation" in r.message
        for r in caplog.records
        if r.name == logger_name
    )


def test_build_user_input_emits_deprecation_warning_for_legacy_key(caplog):
    """build_user_input emits a DEPRECATED warning when modify_markdown is present."""
    raw = dict(_VALID_RAW)
    raw["assets"] = {"modify_markdown": True}

    logger_name = "bookstack_file_exporter.config_helper.config_helper"
    with caplog.at_level(logging.WARNING, logger=logger_name):
        build_user_input(raw)

    warning_messages = [
        r.message for r in caplog.records
        if r.levelno == logging.WARNING and r.name == logger_name
    ]
    assert any(
        "DEPRECATED" in m and "modify_markdown" in m
        for m in warning_messages
    ), f"Expected deprecation warning; got: {warning_messages}"


def test_build_user_input_no_warning_without_legacy_key(caplog):
    """build_user_input must not emit a deprecation warning when only modify_links is used."""
    raw = dict(_VALID_RAW)
    raw["assets"] = {"modify_links": True}

    logger_name = "bookstack_file_exporter.config_helper.config_helper"
    with caplog.at_level(logging.WARNING, logger=logger_name):
        build_user_input(raw)

    deprecation_warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and r.name == logger_name
        and "DEPRECATED" in r.message
    ]
    assert deprecation_warnings == []


# ---------------------------------------------------------------------------
# _generate_urls — scheme detection (Fix-1)
# ---------------------------------------------------------------------------
def _config_with_host(host: str) -> ConfigNode:
    """Build a bare ConfigNode exposing only what _generate_urls reads."""
    node = ConfigNode.__new__(ConfigNode)
    node.user_inputs = SimpleNamespace(host=host)
    return node


@pytest.mark.parametrize("host", [
    "myhttphost.local",       # contains 'http' but no scheme
    "wiki.example.com",       # plain host, no scheme
    "https-portal.internal",  # contains 'https' but no scheme
])
def test_generate_urls_adds_https_when_no_scheme(host):
    """Hosts without an http(s):// scheme get the https:// default,
    even when 'http' appears as a substring of the hostname (Fix-1)."""
    urls = _config_with_host(host)._generate_urls()
    assert urls["books"] == f"https://{host}/api/books"


@pytest.mark.parametrize("host", [
    "http://wiki.example.com",
    "https://wiki.example.com",
])
def test_generate_urls_preserves_existing_scheme(host):
    """Hosts that already carry a scheme are left untouched (no prefix added)."""
    urls = _config_with_host(host)._generate_urls()
    assert urls["books"] == f"{host}/api/books"
