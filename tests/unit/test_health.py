# pylint: disable=missing-class-docstring,missing-function-docstring
"""Tests for the opt-in /healthz health server (F4): RunStatus transitions
and the real HTTP surface."""
import contextlib
import http.client
import json
from datetime import datetime, timezone

from bookstack_file_exporter.health.server import start_health_server
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
        # liveness invariant: a failed cycle must NOT flip the top-level status
        assert snap["status"] == "healthy"
        last = snap["last_run"]
        assert last["status"] == "failed"
        assert last["error"] == "export boom"
        assert last["archive_file"] is None
        assert snap["run_count"] == 1
        assert snap["failure_count"] == 1

    def test_set_next_run_reflected(self):
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


# ---------------------------------------------------------------------------
# Health server: real HTTP surface (ephemeral port, real GET)
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _running_server(status):
    server = start_health_server("127.0.0.1", 0, status)
    try:
        host, port = server.server_address
        yield host, port
    finally:
        server.shutdown()


def _get(host, port, path):
    conn = http.client.HTTPConnection(host, port, timeout=5)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        return resp.status, resp.getheader("Content-Type"), resp.read()
    finally:
        conn.close()


class TestHealthServer:
    def test_healthz_returns_200_json_snapshot(self):
        status = RunStatus()
        status.mark_running()
        status.mark_success(NotifyResult(local="/bkps/export.tgz"))
        with _running_server(status) as (host, port):
            code, ctype, raw = _get(host, port, "/healthz")
        assert code == 200
        assert ctype == "application/json"
        body = json.loads(raw)
        assert body["status"] == "healthy"
        assert body["last_run"]["status"] == "success"
        assert body["last_run"]["archive_file"] == "export.tgz"

    def test_unknown_path_returns_404(self):
        with _running_server(RunStatus()) as (host, port):
            code, _ctype, _raw = _get(host, port, "/nope")
        assert code == 404

    def test_snapshot_reflects_live_transitions(self):
        status = RunStatus()
        with _running_server(status) as (host, port):
            code, _c, raw = _get(host, port, "/healthz")
            assert json.loads(raw)["last_run"]["status"] == "never"
            status.mark_running()
            status.mark_failed(RuntimeError("boom"))
            code, _c, raw = _get(host, port, "/healthz")
        assert code == 200
        body = json.loads(raw)
        assert body["last_run"]["status"] == "failed"
        assert body["last_run"]["error"] == "boom"
        assert body["failure_count"] == 1
