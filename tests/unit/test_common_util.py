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
    """Env var unset, no default, can_error=True → returns empty string, no exception."""
    monkeypatch.delenv("MY_TEST_CAN_ERROR_TRUE", raising=False)
    result = check_var("MY_TEST_CAN_ERROR_TRUE", "", can_error=True)
    assert result == ""


def test_check_var_unset_no_default_raises(monkeypatch):
    """Env var unset, no default, can_error=False → ValueError raised."""
    monkeypatch.delenv("MY_TEST_RAISES", raising=False)
    with pytest.raises(ValueError):
        check_var("MY_TEST_RAISES", "")


def test_check_var_unset_list_default_returns_list(monkeypatch):
    """Env var unset, list default → list returned as-is."""
    monkeypatch.delenv("MY_TEST_LIST_DEFAULT", raising=False)
    result = check_var("MY_TEST_LIST_DEFAULT", ["a", "b"], can_error=False)
    assert result == ["a", "b"]
