"""Tests for the JSON logging formatter and handler factory."""
# pylint: disable=missing-class-docstring,missing-function-docstring
import json
import logging
import re
import sys

from bookstack_file_exporter.common.logging import JsonFormatter, build_handler


def _record(msg="hello %s", args=("world",), exc_info=None, **extra):
    rec = logging.LogRecord(
        name="mod.sub", level=logging.INFO, pathname="p.py", lineno=10,
        msg=msg, args=args, exc_info=exc_info,
    )
    for key, val in extra.items():
        setattr(rec, key, val)
    return rec


class TestJsonFormatterCore:
    def test_core_fields_present(self):
        out = json.loads(JsonFormatter().format(_record()))
        assert out["level"] == "INFO"
        assert out["logger"] == "mod.sub"
        assert out["message"] == "hello world"
        assert "timestamp" in out

    def test_timestamp_is_iso8601_utc_with_millis(self):
        out = json.loads(JsonFormatter().format(_record()))
        assert re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", out["timestamp"])

    def test_output_is_single_line(self):
        line = JsonFormatter().format(_record())
        assert "\n" not in line


class TestJsonFormatterExtras:
    def test_extra_fields_merged(self):
        out = json.loads(JsonFormatter().format(_record(node_count=314, remote=True)))
        assert out["node_count"] == 314
        assert out["remote"] is True

    def test_non_serializable_extra_coerced_to_str(self):
        out = json.loads(JsonFormatter().format(_record(obj=object())))
        assert isinstance(out["obj"], str)


class TestJsonFormatterExcInfo:
    def test_exc_info_field_present_on_exception(self):
        try:
            raise ValueError("boom")
        except ValueError:
            rec = _record(exc_info=sys.exc_info())
        out = json.loads(JsonFormatter().format(rec))  # pylint: disable=used-before-assignment
        assert "exc_info" in out
        assert "ValueError: boom" in out["exc_info"]

    def test_output_is_single_line_with_exc_info(self):
        try:
            raise ValueError("boom")
        except ValueError:
            rec = _record(exc_info=sys.exc_info())
        line = JsonFormatter().format(rec)  # pylint: disable=used-before-assignment
        assert "\n" not in line

    def test_exc_info_field_absent_when_no_exception(self):
        out = json.loads(JsonFormatter().format(_record()))
        assert "exc_info" not in out


class TestJsonFormatterStackInfo:
    def test_stack_info_field_present_when_set(self):
        out = json.loads(JsonFormatter().format(
            _record(stack_info="Stack (most recent call last):\n  frobnicate")))
        assert "frobnicate" in out["stack_info"]

    def test_stack_info_field_absent_when_unset(self):
        out = json.loads(JsonFormatter().format(_record()))
        assert "stack_info" not in out


class TestBuildHandler:
    def test_json_format_uses_jsonformatter(self):
        handler = build_handler("json")
        assert isinstance(handler.formatter, JsonFormatter)

    def test_text_format_uses_plain_formatter(self):
        handler = build_handler("text")
        assert isinstance(handler.formatter, logging.Formatter)
        assert not isinstance(handler.formatter, JsonFormatter)

    def test_text_handler_renders_classic_line(self):
        handler = build_handler("text")
        rendered = handler.formatter.format(_record(msg="done", args=()))
        assert rendered.endswith("[INFO] done")

    def test_returns_stream_handler(self):
        assert isinstance(build_handler("text"), logging.StreamHandler)
