# pylint: disable=missing-class-docstring,missing-function-docstring
"""Unit tests for common utility functions."""
import pytest

from bookstack_file_exporter.common.util import check_var


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


def test_check_var_unset_list_default_returns_list(monkeypatch):
    """Env var unset, list default → list returned as-is."""
    monkeypatch.delenv("MY_TEST_LIST_DEFAULT", raising=False)
    result = check_var("MY_TEST_LIST_DEFAULT", ["a", "b"], required=True)
    assert result == ["a", "b"]


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
    assert check_var("MY_KEY", [], required=False) == []
