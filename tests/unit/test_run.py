"""Tests for run.entrypoint dispatch (single run vs interval loop)."""
from types import SimpleNamespace
from unittest.mock import patch

from bookstack_file_exporter import run


def _config(run_interval):
    return SimpleNamespace(user_inputs=SimpleNamespace(run_interval=run_interval))


def test_entrypoint_runs_once_when_no_interval():
    cfg = _config(run_interval=0)
    with patch.object(run, "ConfigNode", return_value=cfg), \
         patch.object(run, "run") as mock_run:
        run.entrypoint(args=object())
    assert mock_run.call_count == 1


def test_entrypoint_loops_when_interval_set():
    cfg = _config(run_interval=5)
    # break out of the infinite loop after the first sleep
    with patch.object(run, "ConfigNode", return_value=cfg), \
         patch.object(run, "run") as mock_run, \
         patch.object(run.time, "sleep", side_effect=InterruptedError):
        try:
            run.entrypoint(args=object())
        except InterruptedError:
            pass
    assert mock_run.call_count == 1
