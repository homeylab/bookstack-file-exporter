# pylint: disable=missing-class-docstring,missing-function-docstring
# pylint: disable=protected-access
"""Unit tests for the Assets pydantic model and removed 'modify_markdown' key handling."""
import pytest
from pydantic import ValidationError

from bookstack_file_exporter.config_helper.models import Assets
from bookstack_file_exporter.config_helper.config_helper import build_user_input

_VALID_RAW = {
    "host": "https://wiki.example.com",
    "credentials": {"token_id": "abc", "token_secret": "def"},
    "formats": ["markdown"],
}


# ---------------------------------------------------------------------------
# Phase 2 — Assets model + alias
# ---------------------------------------------------------------------------

class TestPhase2AssetsModel:
    """Tests for pydantic Assets model; 'modify_markdown' was removed in v3.0.0."""

    def test_assets_accepts_modify_links(self):
        assets = Assets(modify_links=True)
        assert assets.modify_links is True

    def test_assets_default_modify_links_is_false(self):
        assets = Assets()
        assert assets.modify_links is False

    def test_assets_rejects_removed_modify_markdown(self):
        # v2.3.0 deprecated the alias with a removal promise; v3.0.0 completes it
        with pytest.raises(ValidationError, match="modify_links"):
            Assets(modify_markdown=True)

    def test_assets_rejects_modify_markdown_even_with_modify_links(self):
        # both keys present is still an error — the removed key must never be silently ignored
        with pytest.raises(ValidationError, match="modify_markdown"):
            Assets(**{"modify_links": False, "modify_markdown": True})


class TestModifyMarkdownRemoved:
    """'modify_markdown' is removed in v3.0.0: presence is a hard error with a rename hint."""

    def test_rejected_with_rename_hint(self):
        raw = dict(_VALID_RAW)
        raw["assets"] = {"modify_markdown": True}
        with pytest.raises(ValidationError, match="modify_links"):
            build_user_input(raw)

    def test_rejected_even_when_modify_links_also_present(self):
        raw = dict(_VALID_RAW)
        raw["assets"] = {"modify_links": False, "modify_markdown": True}
        with pytest.raises(ValidationError, match="modify_markdown"):
            build_user_input(raw)

    @pytest.mark.parametrize("bad_assets", [True, "bad_string", 42])
    def test_non_dict_assets_raises_clean_validation_error(self, bad_assets):
        """assets: true (or other non-dict) must surface as a pydantic ValidationError,
        not an AttributeError from the removed-key validator's dict access."""
        raw = dict(_VALID_RAW)
        raw["assets"] = bad_assets
        with pytest.raises(ValidationError):
            build_user_input(raw)
