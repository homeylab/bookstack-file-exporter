# pylint: disable=missing-class-docstring,missing-function-docstring
"""Unit tests for common utility functions."""
import json

import pytest
from pydantic import ValidationError

from bookstack_file_exporter.common.util import check_var, resolve_env_json


def test_check_var_env_wins_over_default(monkeypatch):
    """Env var set and default also set → env value returned."""
    monkeypatch.setenv("MY_TEST_ENV_WINS", "env_value")
    assert check_var("MY_TEST_ENV_WINS", "default_value") == "env_value"


def test_check_var_unset_returns_default(monkeypatch):
    """Env var unset, default set → default returned."""
    monkeypatch.delenv("MY_TEST_UNSET_KEY", raising=False)
    assert check_var("MY_TEST_UNSET_KEY", "my_default") == "my_default"


def test_check_var_env_set_no_default(monkeypatch):
    """Env var set, empty default → env value returned."""
    monkeypatch.setenv("MY_TEST_NO_DEFAULT", "env_only")
    assert check_var("MY_TEST_NO_DEFAULT", "") == "env_only"


def test_check_var_unset_no_default_can_error_true(monkeypatch):
    """Env var unset, no default, required=False → returns empty string, no exception."""
    monkeypatch.delenv("MY_TEST_CAN_ERROR_TRUE", raising=False)
    result = check_var("MY_TEST_CAN_ERROR_TRUE", "", required=False)
    assert result == ""


def test_check_var_unset_no_default_raises(monkeypatch):
    """Env var unset, no default, required=True (default) → ValueError raised."""
    monkeypatch.delenv("MY_TEST_RAISES", raising=False)
    with pytest.raises(ValueError):
        check_var("MY_TEST_RAISES", "")


def test_check_var_env_takes_precedence(monkeypatch):
    monkeypatch.setenv("MY_KEY", "from-env")
    assert check_var("MY_KEY", "from-config") == "from-env"


def test_check_var_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("MY_KEY", raising=False)
    assert check_var("MY_KEY", "from-config") == "from-config"


def test_check_var_required_missing_raises(monkeypatch):
    monkeypatch.delenv("MY_KEY", raising=False)
    with pytest.raises(ValueError):
        check_var("MY_KEY", "", required=True)


def test_check_var_optional_missing_returns_default(monkeypatch):
    monkeypatch.delenv("MY_KEY", raising=False)
    assert check_var("MY_KEY", "", required=False) == ""


class TestResolveEnvJson:
    def test_env_json_parsed(self, monkeypatch):
        monkeypatch.setenv("MY_URLS", json.dumps(["mailto://a", "mailto://b"]))
        assert resolve_env_json("MY_URLS", list[str], []) == ["mailto://a", "mailto://b"]

    def test_env_wins_over_default(self, monkeypatch):
        monkeypatch.setenv("MY_URLS", json.dumps(["mailto://env"]))
        assert resolve_env_json("MY_URLS", list[str], ["mailto://file"]) == ["mailto://env"]

    def test_env_unset_returns_default(self, monkeypatch):
        monkeypatch.delenv("MY_URLS", raising=False)
        assert resolve_env_json("MY_URLS", list[str], ["mailto://file"]) == ["mailto://file"]

    def test_env_empty_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("MY_URLS", "")
        assert resolve_env_json("MY_URLS", list[str], ["mailto://file"]) == ["mailto://file"]

    def test_default_returned_unchanged(self, monkeypatch):
        # helper is pure: it returns default_val as-is (no None->[] coercion;
        # that now lives at the caller). See test_notifications for the []-guard.
        monkeypatch.delenv("MY_URLS", raising=False)
        assert resolve_env_json("MY_URLS", list[str], None) is None

    def test_bad_json_raises(self, monkeypatch):
        monkeypatch.setenv("MY_URLS", "{not valid json")
        with pytest.raises(ValidationError):
            resolve_env_json("MY_URLS", list[str], [])

    def test_non_list_json_raises(self, monkeypatch):
        # valid JSON but wrong shape: a bare str must not pass as list[str]
        monkeypatch.setenv("MY_URLS", '"mailto://a"')
        with pytest.raises(ValidationError):
            resolve_env_json("MY_URLS", list[str], [])

    def test_wrong_element_type_raises(self, monkeypatch):
        monkeypatch.setenv("MY_URLS", json.dumps([1, 2]))
        with pytest.raises(ValidationError):
            resolve_env_json("MY_URLS", list[str], [])
