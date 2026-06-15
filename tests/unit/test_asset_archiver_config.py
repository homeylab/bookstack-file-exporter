# pylint: disable=missing-class-docstring,missing-function-docstring
# pylint: disable=protected-access
"""Unit tests for Assets pydantic model and config_helper deprecation warning (Phase 2)."""
import argparse
import logging

from bookstack_file_exporter.config_helper.models import Assets
from bookstack_file_exporter.config_helper.config_helper import (
    ConfigNode,
    check_legacy_modify_markdown,
)


# ---------------------------------------------------------------------------
# Phase 2 — Assets model + alias
# ---------------------------------------------------------------------------

class TestPhase2AssetsModel:
    """Tests for pydantic Assets model with modify_links / modify_markdown alias."""

    def test_assets_accepts_modify_links(self):
        assets = Assets(modify_links=True)
        assert assets.modify_links is True

    def test_assets_accepts_legacy_modify_markdown(self):
        assets = Assets(modify_markdown=True)
        assert assets.modify_links is True

    def test_assets_default_modify_links_is_false(self):
        assets = Assets()
        assert assets.modify_links is False

    def test_assets_modify_links_wins_when_both_keys_present(self):
        # modify_links=False should win over modify_markdown=True
        assets = Assets(**{"modify_links": False, "modify_markdown": True})
        assert assets.modify_links is False


class TestPhase2ConfigHelperDeprecationWarning:
    """Tests for deprecation warning in config_helper.py."""

    def _write_config(self, tmp_path, content: str) -> str:
        config_file = tmp_path / "config.yml"
        config_file.write_text(content)
        return str(config_file)

    def test_deprecation_warning_emitted_when_legacy_key_present(self, tmp_path, caplog):
        config_content = """
host: https://wiki.example.com
credentials:
  token_id: abc
  token_secret: def
formats:
  - markdown
assets:
  modify_markdown: true
"""
        config_file = self._write_config(tmp_path, config_content)
        args = argparse.Namespace(config_file=config_file, output_dir=None)

        logger_name = "bookstack_file_exporter.config_helper.config_helper"
        with caplog.at_level(logging.WARNING, logger=logger_name):
            ConfigNode(args)

        warning_msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("DEPRECATED" in m and "modify_markdown" in m for m in warning_msgs)

    def test_deprecation_warning_emitted_exactly_once(self, tmp_path, caplog):
        config_content = """
host: https://wiki.example.com
credentials:
  token_id: abc
  token_secret: def
formats:
  - markdown
assets:
  modify_markdown: true
"""
        config_file = self._write_config(tmp_path, config_content)
        args = argparse.Namespace(config_file=config_file, output_dir=None)

        logger_name = "bookstack_file_exporter.config_helper.config_helper"
        with caplog.at_level(logging.WARNING, logger=logger_name):
            ConfigNode(args)

        deprecation_warnings = [
            r for r in caplog.records
            if r.levelno == logging.WARNING and "DEPRECATED" in r.message
        ]
        assert len(deprecation_warnings) == 1

    def test_second_warning_when_both_keys_present_different_values(self, tmp_path, caplog):
        config_content = """
host: https://wiki.example.com
credentials:
  token_id: abc
  token_secret: def
formats:
  - markdown
assets:
  modify_links: false
  modify_markdown: true
"""
        config_file = self._write_config(tmp_path, config_content)
        args = argparse.Namespace(config_file=config_file, output_dir=None)

        logger_name = "bookstack_file_exporter.config_helper.config_helper"
        with caplog.at_level(logging.WARNING, logger=logger_name):
            ConfigNode(args)

        warning_msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        # Should have the deprecation warning + ignored legacy warning
        assert len(warning_msgs) >= 2
        assert any("ignored" in m.lower() for m in warning_msgs)

    def test_check_legacy_modify_markdown_non_dict_assets_does_not_crash(self, caplog):
        """assets: true (or other non-dict) must not crash before pydantic validates."""
        logger_name = "bookstack_file_exporter.config_helper.config_helper"
        with caplog.at_level(logging.WARNING, logger=logger_name):
            check_legacy_modify_markdown({"assets": True})
            check_legacy_modify_markdown({"assets": "bad_string"})
            check_legacy_modify_markdown({"assets": 42})
        our_records = [r for r in caplog.records if r.name == logger_name]
        assert our_records == [], (
            f"non-dict assets must produce zero warnings from this logger; "
            f"got: {[r.message for r in our_records]}"
        )
