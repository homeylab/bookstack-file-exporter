"""Tests for run_args log-format/log-level flag parsing and precedence resolution."""
# pylint: disable=missing-class-docstring,missing-function-docstring
import argparse
import logging

from bookstack_file_exporter import run_args


def _args(log_format=None):
    return argparse.Namespace(log_format=log_format)


def _lvl_args(log_level=None):
    return argparse.Namespace(log_level=log_level)


class TestLogFormatArg:
    def test_default_is_none(self):
        # --log-format absent -> None (so resolve_log_format can fall to env)
        assert run_args.get_args([]).log_format is None

    def test_flag_parsed_and_lowercased(self):
        assert run_args.get_args(["--log-format", "JSON"]).log_format == "json"


class TestResolveLogFormat:
    def test_cli_overrides_env(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "text")
        assert run_args.resolve_log_format(_args(log_format="json")) == "json"

    def test_env_used_when_no_flag(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "json")
        assert run_args.resolve_log_format(_args()) == "json"

    def test_env_is_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "JSON")
        assert run_args.resolve_log_format(_args()) == "json"

    def test_default_text_when_neither(self, monkeypatch):
        monkeypatch.delenv("LOG_FORMAT", raising=False)
        assert run_args.resolve_log_format(_args()) == "text"

    def test_invalid_env_falls_back_to_text_with_warning(self, monkeypatch, caplog):
        monkeypatch.setenv("LOG_FORMAT", "yaml")
        with caplog.at_level(logging.WARNING):
            assert run_args.resolve_log_format(_args()) == "text"
        assert any("yaml" in r.message and "LOG_FORMAT" in r.message
                   for r in caplog.records)


class TestLogLevelArg:
    def test_default_is_none(self):
        # --log-level absent -> None (so resolve_log_level can fall to env)
        assert run_args.get_args([]).log_level is None

    def test_flag_parsed_and_lowercased(self):
        assert run_args.get_args(["-v", "DEBUG"]).log_level == "debug"


class TestResolveLogLevel:
    def test_cli_overrides_env(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "error")
        assert run_args.resolve_log_level(_lvl_args(log_level="debug")) == "debug"

    def test_env_used_when_no_flag(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "debug")
        assert run_args.resolve_log_level(_lvl_args()) == "debug"

    def test_env_is_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        assert run_args.resolve_log_level(_lvl_args()) == "debug"

    def test_default_info_when_neither(self, monkeypatch):
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        assert run_args.resolve_log_level(_lvl_args()) == "info"

    def test_invalid_env_falls_back_to_info_with_warning(self, monkeypatch, caplog):
        monkeypatch.setenv("LOG_LEVEL", "verbose")
        with caplog.at_level(logging.WARNING):
            assert run_args.resolve_log_level(_lvl_args()) == "info"
        assert any("verbose" in r.message and "LOG_LEVEL" in r.message
                   for r in caplog.records)
