# pylint: disable=missing-class-docstring,missing-function-docstring
"""Unit tests for seconds_until_next_cron helper."""
from datetime import datetime

from bookstack_file_exporter.common.util import seconds_until_next_cron


def test_seconds_until_next_basic():
    """next fire of '0 2 * * *' from midnight is 2 hours later (same day)."""
    now = datetime(2026, 1, 1, 0, 0, 0)
    assert seconds_until_next_cron("0 2 * * *", now) == 2 * 3600


def test_seconds_until_next_after_tick():
    """A cycle that overran 02:00 waits for tomorrow's 02:00, not immediate fire."""
    now = datetime(2026, 1, 1, 3, 0, 0)
    assert seconds_until_next_cron("0 2 * * *", now) == 23 * 3600


def test_seconds_until_next_nonnegative():
    """Result is always strictly positive."""
    now = datetime(2026, 6, 15, 12, 30, 0)
    result = seconds_until_next_cron("*/5 * * * *", now)
    assert result > 0
