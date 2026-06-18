# pylint: disable=missing-class-docstring,missing-function-docstring,protected-access
"""Unit tests for AppRiseNotifyConfig env/JSON resolution and validate() purity."""
import json

import pytest
from pydantic import ValidationError

from bookstack_file_exporter.config_helper import models
from bookstack_file_exporter.config_helper.notifications import (
    AppRiseNotifyConfig,
    _APPRISE_FIELDS,
)

_ENV_KEY = _APPRISE_FIELDS["urls"]


def _make_config(**overrides) -> models.AppRiseNotifyConfig:
    base = {"service_urls": [], "config_path": ""}
    base.update(overrides)
    return models.AppRiseNotifyConfig(**base)


class TestServiceUrlResolution:
    def test_env_json_string_parsed_to_list_at_construction(self, monkeypatch):
        monkeypatch.setenv(_ENV_KEY, json.dumps(["mailto://a", "mailto://b"]))
        cfg = AppRiseNotifyConfig(_make_config())
        # __init__ resolves the raw env JSON string into a validated list
        assert cfg.service_urls == ["mailto://a", "mailto://b"]

    def test_config_file_urls_untouched_when_env_unset(self, monkeypatch):
        monkeypatch.delenv(_ENV_KEY, raising=False)
        cfg = AppRiseNotifyConfig(_make_config(service_urls=["mailto://from-file"]))
        assert cfg.service_urls == ["mailto://from-file"]

    def test_none_config_urls_resolve_to_empty_list(self, monkeypatch):
        # caller's `or []` keeps the []-not-None guarantee the helper dropped
        monkeypatch.delenv(_ENV_KEY, raising=False)
        cfg = AppRiseNotifyConfig(_make_config(service_urls=None))
        assert cfg.service_urls == []

    def test_env_parsed_even_with_config_path(self, monkeypatch):
        # env is resolved unconditionally now; config_path no longer suppresses it
        monkeypatch.setenv(_ENV_KEY, json.dumps(["mailto://x"]))
        cfg = AppRiseNotifyConfig(_make_config(config_path="/etc/apprise.yml"))
        assert cfg.service_urls == ["mailto://x"]

    def test_invalid_env_json_raises_at_construction(self, monkeypatch):
        monkeypatch.setenv(_ENV_KEY, "{not valid json")
        with pytest.raises(ValidationError):
            AppRiseNotifyConfig(_make_config())

    def test_non_list_env_json_raises_at_construction(self, monkeypatch):
        # valid JSON but a bare str: must fail loud, not reach apprise as a str
        monkeypatch.setenv(_ENV_KEY, '"mailto://a"')
        with pytest.raises(ValidationError):
            AppRiseNotifyConfig(_make_config())

    def test_empty_env_falls_back_to_config_list(self, monkeypatch):
        # APPRISE_URLS="" (set but empty) falls back to the config list instead
        # of crashing with TypeError (the old double-env-probe bug).
        monkeypatch.setenv(_ENV_KEY, "")
        cfg = AppRiseNotifyConfig(_make_config(service_urls=["mailto://x"]))
        assert cfg.service_urls == ["mailto://x"]


class TestValidate:
    def test_missing_both_raises(self, monkeypatch):
        monkeypatch.delenv(_ENV_KEY, raising=False)
        cfg = AppRiseNotifyConfig(_make_config(service_urls=[], config_path=""))
        with pytest.raises(ValueError):
            cfg.validate()

    def test_config_path_only_passes(self, monkeypatch):
        monkeypatch.delenv(_ENV_KEY, raising=False)
        cfg = AppRiseNotifyConfig(_make_config(config_path="/etc/apprise.yml"))
        cfg.validate()  # no raise

    def test_service_urls_only_passes(self, monkeypatch):
        monkeypatch.delenv(_ENV_KEY, raising=False)
        cfg = AppRiseNotifyConfig(_make_config(service_urls=["mailto://x"]))
        cfg.validate()  # no raise

    def test_validate_is_pure_no_env_read_no_mutation(self, monkeypatch):
        # resolve from env at construction, then change the env: validate() must
        # not re-read it or mutate state. Idempotent across repeated calls.
        monkeypatch.setenv(_ENV_KEY, json.dumps(["mailto://a"]))
        cfg = AppRiseNotifyConfig(_make_config())
        assert cfg.service_urls == ["mailto://a"]
        monkeypatch.setenv(_ENV_KEY, json.dumps(["mailto://changed"]))
        cfg.validate()
        cfg.validate()
        assert cfg.service_urls == ["mailto://a"]
