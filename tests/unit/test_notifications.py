# pylint: disable=missing-class-docstring,missing-function-docstring,protected-access
"""Unit tests for AppRiseNotifyConfig env/JSON resolution and validate() purity."""
import json

import pytest

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
        # check_var pulls the raw env string; __init__ resolves it to a list
        assert cfg.service_urls == ["mailto://a", "mailto://b"]

    def test_config_file_urls_untouched_when_env_unset(self, monkeypatch):
        monkeypatch.delenv(_ENV_KEY, raising=False)
        cfg = AppRiseNotifyConfig(_make_config(service_urls=["mailto://from-file"]))
        assert cfg.service_urls == ["mailto://from-file"]

    def test_config_path_skips_url_parse(self, monkeypatch):
        # env set, but config_path present -> no JSON parse; service_urls stays
        # the raw env string (check_var override) rather than raising on bad json
        monkeypatch.setenv(_ENV_KEY, "not-json")
        cfg = AppRiseNotifyConfig(_make_config(config_path="/etc/apprise.yml",
                                               service_urls=["mailto://x"]))
        assert cfg.service_urls == "not-json"

    def test_invalid_env_json_raises_at_construction(self, monkeypatch):
        monkeypatch.setenv(_ENV_KEY, "{not valid json")
        with pytest.raises(json.decoder.JSONDecodeError):
            AppRiseNotifyConfig(_make_config())

    def test_empty_env_with_config_list_raises_typeerror(self, monkeypatch):
        # fidelity edge: APPRISE_URLS="" is falsy so check_var returns the config
        # list, but `os.environ.get(...) is not None` is still True -> json.loads
        # runs on a list -> TypeError. Preserved verbatim from pre-refactor.
        monkeypatch.setenv(_ENV_KEY, "")
        with pytest.raises(TypeError):
            AppRiseNotifyConfig(_make_config(service_urls=["mailto://x"]))


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
