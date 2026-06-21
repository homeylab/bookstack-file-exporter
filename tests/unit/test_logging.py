"""Tests for the JSON logging formatter and handler factory."""
# pylint: disable=missing-class-docstring,missing-function-docstring
import json
import logging
import re
import sys

from bookstack_file_exporter.common.logging import JsonFormatter


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

    def test_timestamp_is_iso8601_utc(self):
        out = json.loads(JsonFormatter().format(_record()))
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", out["timestamp"])

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
        out = json.loads(JsonFormatter().format(rec))
        assert "exc_info" in out
        assert "ValueError: boom" in out["exc_info"]

    def test_exc_info_field_absent_when_no_exception(self):
        out = json.loads(JsonFormatter().format(_record()))
        assert "exc_info" not in out
