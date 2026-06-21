# pylint: disable=missing-class-docstring,missing-function-docstring
"""Tests for the opt-in /healthz health server (F4): RunStatus transitions
and the real HTTP surface."""
import json

from bookstack_file_exporter.health.status import RunStatus
from bookstack_file_exporter.notify.models import NotifyResult


# ---------------------------------------------------------------------------
# RunStatus: snapshot shape + transitions
# ---------------------------------------------------------------------------

class TestRunStatusSnapshot:
    def test_initial_snapshot_all_keys_present_never(self):
        snap = RunStatus().snapshot()
        assert snap["status"] == "healthy"
        assert snap["next_run"] is None
        assert snap["run_count"] == 0
        assert snap["failure_count"] == 0
        last = snap["last_run"]
        assert last == {
            "status": "never",
            "started_at": None,
            "finished_at": None,
            "duration_seconds": None,
            "archive_file": None,
            "error": None,
        }

    def test_mark_running_sets_running_and_started(self):
        status = RunStatus()
        status.mark_running()
        last = status.snapshot()["last_run"]
        assert last["status"] == "running"
        assert last["started_at"] is not None
        assert last["finished_at"] is None
        assert last["duration_seconds"] is None

    def test_mark_success_populates_archive_and_counts(self):
        status = RunStatus()
        status.mark_running()
        status.mark_success(NotifyResult(local="/bkps/bookstack_export_2026.tgz"))
        snap = status.snapshot()
        last = snap["last_run"]
        assert last["status"] == "success"
        assert last["finished_at"] is not None
        assert last["duration_seconds"] is not None
        assert last["archive_file"] == "bookstack_export_2026.tgz"
        assert last["error"] is None
        assert snap["run_count"] == 1
        assert snap["failure_count"] == 0

    def test_mark_success_none_result_archive_null(self):
        status = RunStatus()
        status.mark_running()
        status.mark_success(None)
        assert status.snapshot()["last_run"]["archive_file"] is None

    def test_mark_success_none_local_archive_null(self):
        status = RunStatus()
        status.mark_running()
        status.mark_success(NotifyResult(local=None))
        assert status.snapshot()["last_run"]["archive_file"] is None

    def test_mark_failed_sets_error_and_counts(self):
        status = RunStatus()
        status.mark_running()
        status.mark_failed(RuntimeError("export boom"))
        snap = status.snapshot()
        last = snap["last_run"]
        assert last["status"] == "failed"
        assert last["error"] == "export boom"
        assert last["archive_file"] is None
        assert snap["run_count"] == 1
        assert snap["failure_count"] == 1

    def test_set_next_run_reflected(self):
        from datetime import datetime, timezone
        status = RunStatus()
        status.set_next_run(datetime(2026, 6, 22, 2, 0, 0, tzinfo=timezone.utc))
        assert status.snapshot()["next_run"] == "2026-06-22T02:00:00Z"

    def test_mark_running_clears_prior_error(self):
        status = RunStatus()
        status.mark_running()
        status.mark_failed(RuntimeError("boom"))
        status.mark_running()
        assert status.snapshot()["last_run"]["error"] is None

    def test_counts_accumulate_across_cycles(self):
        status = RunStatus()
        for _ in range(2):
            status.mark_running()
            status.mark_success(None)
        status.mark_running()
        status.mark_failed(RuntimeError("x"))
        snap = status.snapshot()
        assert snap["run_count"] == 3
        assert snap["failure_count"] == 1

    def test_snapshot_is_json_serializable(self):
        status = RunStatus()
        status.mark_running()
        status.mark_success(NotifyResult(local="/a/b.tgz"))
        json.dumps(status.snapshot())  # must not raise
