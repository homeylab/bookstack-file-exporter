# pylint: disable=missing-class-docstring,missing-function-docstring
"""Unit tests for common utility functions."""
import json
from typing import get_args

import pytest
from pydantic import ValidationError

from bookstack_file_exporter.common.util import (
    EXPORT_BASENAME,
    _LEVEL_TOKENS,
    check_var,
    resolve_env_json,
    same_export_level,
)
from bookstack_file_exporter.config_helper.models import UserInput


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


@pytest.mark.parametrize("basename, level, expected", [
    # pages: no infix -> matches pages, not books/chapters
    (f"{EXPORT_BASENAME}_2026-07-05_00-00-00.tgz", "pages", True),
    (f"{EXPORT_BASENAME}_2026-07-05_00-00-00_partial.tgz", "pages", True),
    (f"{EXPORT_BASENAME}_2026-07-05_00-00-00.tgz", "books", False),
    (f"{EXPORT_BASENAME}_2026-07-05_00-00-00.tgz", "chapters", False),
    # books infix
    (f"{EXPORT_BASENAME}_books_2026-07-05_00-00-00.tgz", "books", True),
    (f"{EXPORT_BASENAME}_books_2026-07-05_00-00-00_partial.tgz", "books", True),
    (f"{EXPORT_BASENAME}_books_2026-07-05_00-00-00.tgz", "pages", False),
    (f"{EXPORT_BASENAME}_books_2026-07-05_00-00-00.tgz", "chapters", False),
    # chapters infix
    (f"{EXPORT_BASENAME}_chapters_2026-07-05_00-00-00.tgz", "chapters", True),
    (f"{EXPORT_BASENAME}_chapters_2026-07-05_00-00-00.tgz", "pages", False),
    # non-managed name never matches any level
    ("unrelated_2026-07-05_00-00-00.tgz", "pages", False),
])
def test_same_export_level(basename, level, expected):
    assert same_export_level(basename, level) is expected


def test_level_tokens_track_export_level_literal():
    """Drift guard: a level added to the export_level Literal must be added to
    _LEVEL_TOKENS, else its archives fall through the pages exclusion branch and a
    pages run would prune them."""
    # pylint false positive: model_fields is a pydantic ClassVar[Dict], pylint's
    # type inference doesn't resolve it as subscriptable without the pydantic plugin.
    literal_levels = set(
        get_args(UserInput.model_fields["export_level"].annotation)  # pylint: disable=unsubscriptable-object
    )
    assert _LEVEL_TOKENS == literal_levels - {"pages"}
