"""Lock-guarded mutable run status behind the /healthz JSON body (F4).

Plain dataclass + threading.Lock (NOT pydantic): pydantic is for parse/validate,
this is mutable shared state read by the health-server thread while the scheduled
loop writes it. All timestamps are UTC; snapshot() emits ISO-8601 'Z' strings.
"""
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

from bookstack_file_exporter.notify.models import NotifyResult


def _iso(value: datetime | None) -> str | None:
    """Format a UTC datetime as ISO-8601 with a trailing Z, or None."""
    if value is None:
        return None
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RunStatus:  # pylint: disable=too-many-instance-attributes
    """Thread-safe last-run/next-run status for the health endpoint."""
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _last_run_status: str = "never"   # never -> running -> success | failed
    _started_at: datetime | None = None
    _finished_at: datetime | None = None
    _archive_file: str | None = None
    _error: str | None = None
    _next_run: datetime | None = None
    _run_count: int = 0
    _failure_count: int = 0

    def mark_running(self) -> None:
        """Transition to running state and record the start timestamp."""
        with self._lock:
            self._last_run_status = "running"
            self._started_at = _now()
            self._finished_at = None
            self._archive_file = None
            self._error = None

    def mark_success(self, result: NotifyResult | None) -> None:
        """Transition to success state, record finish time, and increment run count."""
        with self._lock:
            self._last_run_status = "success"
            self._finished_at = _now()
            self._error = None
            self._archive_file = (
                os.path.basename(result.local)
                if result is not None and result.local
                else None
            )
            self._run_count += 1

    def mark_failed(self, err: Exception) -> None:
        """Transition to failed state, record error message, and increment both counters."""
        with self._lock:
            self._last_run_status = "failed"
            self._finished_at = _now()
            self._archive_file = None
            self._error = str(err)
            self._run_count += 1
            self._failure_count += 1

    def set_next_run(self, next_run: datetime) -> None:
        """Store the UTC datetime of the next scheduled run."""
        with self._lock:
            self._next_run = next_run

    def _duration_seconds(self) -> int | None:
        if self._started_at is None or self._finished_at is None:
            return None
        return int(round((self._finished_at - self._started_at).total_seconds()))

    def snapshot(self) -> dict:
        """Build the JSON-ready body under the lock. All keys always present."""
        with self._lock:
            return {
                "status": "healthy",
                "last_run": {
                    "status": self._last_run_status,
                    "started_at": _iso(self._started_at),
                    "finished_at": _iso(self._finished_at),
                    "duration_seconds": self._duration_seconds(),
                    "archive_file": self._archive_file,
                    "error": self._error,
                },
                "next_run": _iso(self._next_run),
                "run_count": self._run_count,
                "failure_count": self._failure_count,
            }
