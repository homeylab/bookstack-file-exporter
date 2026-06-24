# pylint: disable=missing-function-docstring,missing-module-docstring
import pytest
from pydantic import ValidationError

from bookstack_file_exporter.config_helper.models import UserInput

_BASE = {"host": "https://wiki.example", "formats": ["markdown"]}


def test_export_workers_defaults_to_one():
    cfg = UserInput(**_BASE)
    assert cfg.export_workers == 1


def test_export_workers_accepts_positive_int():
    cfg = UserInput(**_BASE, export_workers=8)
    assert cfg.export_workers == 8


@pytest.mark.parametrize("bad", [0, -1, -5])
def test_export_workers_rejects_below_one(bad):
    with pytest.raises(ValidationError):
        UserInput(**_BASE, export_workers=bad)


def test_export_workers_accepts_large_value_no_hard_cap():
    cfg = UserInput(**_BASE, export_workers=64)
    assert cfg.export_workers == 64
