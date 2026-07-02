# pylint: disable=missing-function-docstring
"""Unit tests for AppRiseNotifyConfig validation in models.py."""
import pytest
from pydantic import ValidationError

from bookstack_file_exporter.config_helper.models import AppRiseNotifyConfig


def test_body_format_defaults_to_text():
    cfg = AppRiseNotifyConfig(service_urls=["json://localhost"])
    assert cfg.body_format == "text"


def test_body_format_accepts_markdown():
    cfg = AppRiseNotifyConfig(service_urls=["json://localhost"], body_format="markdown")
    assert cfg.body_format == "markdown"


def test_body_format_rejects_unknown():
    with pytest.raises(ValidationError):
        AppRiseNotifyConfig(service_urls=["json://localhost"], body_format="html")
