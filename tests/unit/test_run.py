"""Tests for run.entrypoint dispatch (single run vs interval loop), the
scheduled-mode health server and signal handling, and _run_once exit codes.
Exporter-level tests live in test_run_exporter.py."""
# pylint: disable=missing-class-docstring,missing-function-docstring,unused-argument,protected-access
import logging
import signal
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from bookstack_file_exporter import run
from bookstack_file_exporter.notify.models import ExportStatus, NotifyResult


def _config(run_interval, run_once=False, run_schedule=None, health_port=None):
    """Return a minimal fake args + config pair for entrypoint tests."""
    return SimpleNamespace(
        user_inputs=SimpleNamespace(
            run_interval=run_interval,
            run_schedule=run_schedule,
            health_port=health_port,
            health_host="0.0.0.0",
        )
    )


def _args(run_once=False):
    return SimpleNamespace(run_once=run_once)


# ---------------------------------------------------------------------------
# entrypoint() — config build failure
# ---------------------------------------------------------------------------

class TestEntrypointConfigError:
    def test_config_error_returns_1(self, caplog):
        with patch.object(run, "ConfigNode", side_effect=ValueError("bad config")), \
             caplog.at_level(logging.ERROR, logger="bookstack_file_exporter.run"):
            result = run.entrypoint(args=_args())
        assert result == 1
        assert any("Configuration error" in r.message for r in caplog.records)

    def test_config_error_does_not_propagate(self):
        with patch.object(run, "ConfigNode", side_effect=RuntimeError("boom")):
            result = run.entrypoint(args=_args())
        assert result == 1


# ---------------------------------------------------------------------------
# _run_once() via entrypoint() — one-shot path
# ---------------------------------------------------------------------------

class TestRunOncePath:
    def _cfg_no_interval(self):
        return _config(run_interval=0)

    def test_success_returns_0(self):
        cfg = self._cfg_no_interval()
        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch("bookstack_file_exporter.run.signal.signal"), \
             patch.object(run, "run", return_value=None):
            result = run.entrypoint(args=_args())
        assert result == 0

    def test_run_raises_exception_returns_1(self, caplog):
        cfg = self._cfg_no_interval()
        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch("bookstack_file_exporter.run.signal.signal"), \
             patch.object(run, "run", side_effect=RuntimeError("export boom")), \
             caplog.at_level(logging.ERROR, logger="bookstack_file_exporter.run"):
            result = run.entrypoint(args=_args())
        assert result == 1
        assert any("Export failed" in r.message for r in caplog.records)

    def test_run_raises_exception_no_traceback_propagated(self):
        """Exception must NOT escape entrypoint."""
        cfg = self._cfg_no_interval()
        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch("bookstack_file_exporter.run.signal.signal"), \
             patch.object(run, "run", side_effect=RuntimeError("boom")):
            # should not raise
            result = run.entrypoint(args=_args())
        assert result == 1

    def test_keyboard_interrupt_returns_130(self):
        """A bare KeyboardInterrupt (no signal recorded) defaults to SIGINT->130."""
        cfg = self._cfg_no_interval()
        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch("bookstack_file_exporter.run.signal.signal"), \
             patch.object(run, "run", side_effect=KeyboardInterrupt):
            result = run.entrypoint(args=_args())
        assert result == 130

    def test_sigterm_during_run_cleans_up_and_returns_143(self):
        """SIGTERM mid-run -> KeyboardInterrupt -> finally cleanup -> exit 143."""
        cfg = self._cfg_no_interval()
        captured = {}

        def _capture(signum, handler):
            if callable(handler):
                captured[signum] = handler

        def _signal_mid_run(_config, _stop=None):
            captured[signal.SIGTERM](signal.SIGTERM, None)

        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch("bookstack_file_exporter.run.signal.signal", side_effect=_capture), \
             patch.object(run, "run", side_effect=_signal_mid_run):
            result = run.entrypoint(args=_args())
        assert result == 143

    def test_sigint_during_run_returns_130(self):
        cfg = self._cfg_no_interval()
        captured = {}

        def _capture(signum, handler):
            if callable(handler):
                captured[signum] = handler

        def _signal_mid_run(_config, _stop=None):
            captured[signal.SIGINT](signal.SIGINT, None)

        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch("bookstack_file_exporter.run.signal.signal", side_effect=_capture), \
             patch.object(run, "run", side_effect=_signal_mid_run):
            result = run.entrypoint(args=_args())
        assert result == 130

    def test_first_signal_restores_sig_dfl_for_both_signals(self):
        """Force-kill escape hatch: first signal restores default for both."""
        cfg = self._cfg_no_interval()
        captured = {}
        calls = []

        def _capture(signum, handler):
            calls.append((signum, handler))
            if callable(handler):
                captured[signum] = handler

        def _signal_mid_run(_config, _stop=None):
            captured[signal.SIGTERM](signal.SIGTERM, None)

        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch("bookstack_file_exporter.run.signal.signal", side_effect=_capture), \
             patch.object(run, "run", side_effect=_signal_mid_run):
            run.entrypoint(args=_args())

        assert (signal.SIGTERM, signal.SIG_DFL) in calls
        assert (signal.SIGINT, signal.SIG_DFL) in calls


# ---------------------------------------------------------------------------
# run_once flag forces _run_once even when run_interval is set
# ---------------------------------------------------------------------------

class TestRunOnceFlag:
    def test_run_once_flag_true_forces_single_run_even_with_interval(self):
        cfg = _config(run_interval=60)
        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch("bookstack_file_exporter.run.signal.signal"), \
             patch.object(run, "run", return_value=None) as mock_run:
            result = run.entrypoint(args=_args(run_once=True))
        assert result == 0
        assert mock_run.call_count == 1

    def test_run_once_flag_false_with_no_interval_still_runs_once(self):
        cfg = _config(run_interval=0)
        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch("bookstack_file_exporter.run.signal.signal"), \
             patch.object(run, "run", return_value=None) as mock_run:
            result = run.entrypoint(args=_args(run_once=False))
        assert result == 0
        assert mock_run.call_count == 1


# ---------------------------------------------------------------------------
# _run_scheduled() via entrypoint() — daemon path
# ---------------------------------------------------------------------------

class TestRunScheduledPath:
    def _cfg_with_interval(self, interval=5):
        return _config(run_interval=interval)

    def test_sigterm_and_sigint_handlers_installed(self):
        """signal.signal must be called for both SIGTERM and SIGINT."""
        cfg = self._cfg_with_interval()
        stop_event = threading.Event()

        def _run_side_effect(_config, _stop=None):
            stop_event.set()  # signal stop after first call so loop exits

        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch.object(run, "run", side_effect=_run_side_effect), \
             patch("bookstack_file_exporter.run.signal.signal") as mock_signal, \
             patch("bookstack_file_exporter.run.threading.Event", return_value=stop_event):
            result = run.entrypoint(args=_args(run_once=False))

        assert result == 0
        installed_signals = {c.args[0] for c in mock_signal.call_args_list}
        assert signal.SIGTERM in installed_signals
        assert signal.SIGINT in installed_signals

    def test_cycle_exception_loop_continues(self):
        """A per-cycle Exception must not kill the scheduled loop; run() is called again."""
        cfg = self._cfg_with_interval(interval=1)
        stop_event = threading.Event()
        call_count = 0

        def _run_side_effect(_config, _stop=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient failure")
            stop_event.set()  # exit on second call

        # no-op wait so the inter-cycle interval does not actually block the test
        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch.object(run, "run", side_effect=_run_side_effect), \
             patch("bookstack_file_exporter.run.signal.signal"), \
             patch.object(stop_event, "wait", return_value=False), \
             patch("bookstack_file_exporter.run.threading.Event", return_value=stop_event):
            result = run.entrypoint(args=_args(run_once=False))

        assert result == 0
        assert call_count == 2

    def test_failed_cycle_still_waits_before_retry(self):
        """A failed cycle must wait the interval before retrying (no busy-loop).

        Regression guard: an earlier draft used `continue` after logging the
        error, skipping stop.wait() — so a persistently failing Bookstack would
        hammer run() with zero delay. The failed cycle must reach stop.wait().
        """
        cfg = self._cfg_with_interval(interval=5)
        stop_event = threading.Event()
        call_count = 0

        def _run_side_effect(_config, _stop=None):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("persistent failure")

        def _wait_side_effect(timeout=None):
            # stop the loop on the wait that follows the failed cycle
            stop_event.set()
            return False

        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch.object(run, "run", side_effect=_run_side_effect), \
             patch("bookstack_file_exporter.run.signal.signal"), \
             patch.object(stop_event, "wait", side_effect=_wait_side_effect) as mock_wait, \
             patch("bookstack_file_exporter.run.threading.Event", return_value=stop_event):
            result = run.entrypoint(args=_args(run_once=False))

        assert result == 0
        # the failed cycle reached the interval wait rather than spinning
        mock_wait.assert_called_once_with(5)
        assert call_count == 1

    def test_stop_event_exits_loop_with_0(self):
        """When stop event is set (e.g. via signal), _run_scheduled returns 0."""
        cfg = self._cfg_with_interval()
        stop_event = threading.Event()

        def _run_side_effect(_config, _stop=None):
            stop_event.set()

        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch.object(run, "run", side_effect=_run_side_effect), \
             patch("bookstack_file_exporter.run.signal.signal"), \
             patch("bookstack_file_exporter.run.threading.Event", return_value=stop_event):
            result = run.entrypoint(args=_args(run_once=False))

        assert result == 0

    def test_stop_wait_used_not_time_sleep(self):
        """The scheduled loop must use stop.wait(interval) not time.sleep.

        Simulate: run() completes normally; then stop.wait() is called and the
        wait itself sets the event (as if a signal arrived mid-wait), causing
        the next loop check to exit.
        """
        cfg = self._cfg_with_interval(interval=5)
        stop_event = threading.Event()

        # Patch stop_event.wait so that calling it sets the event (simulating
        # SIGINT arriving during the sleep interval), then delegates to the real wait.
        real_wait = stop_event.wait

        def _wait_side_effect(timeout=None):
            stop_event.set()
            return real_wait(0)  # return immediately

        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch.object(run, "run"), \
             patch("bookstack_file_exporter.run.signal.signal"), \
             patch.object(stop_event, "wait", side_effect=_wait_side_effect) as mock_wait, \
             patch("bookstack_file_exporter.run.threading.Event", return_value=stop_event):
            result = run.entrypoint(args=_args(run_once=False))

        assert result == 0
        # wait should have been called with the interval value
        mock_wait.assert_called_with(5)


# ---------------------------------------------------------------------------
# Legacy entrypoint tests — updated for int-returning API + Event.wait loop
# ---------------------------------------------------------------------------

def test_entrypoint_runs_once_when_no_interval():
    cfg = _config(run_interval=0)
    with patch.object(run, "ConfigNode", return_value=cfg), \
         patch.object(run, "run", return_value=None) as mock_run:
        result = run.entrypoint(args=_args())
    assert result == 0
    assert mock_run.call_count == 1


def test_entrypoint_loops_when_interval_set():
    cfg = _config(run_interval=5)
    stop_event = threading.Event()
    call_count = 0

    def _run_side_effect(_config, _stop=None):
        nonlocal call_count
        call_count += 1
        stop_event.set()  # exit after first iteration

    with patch.object(run, "ConfigNode", return_value=cfg), \
         patch.object(run, "run", side_effect=_run_side_effect), \
         patch("bookstack_file_exporter.run.signal.signal"), \
         patch("bookstack_file_exporter.run.threading.Event", return_value=stop_event):
        result = run.entrypoint(args=_args())

    assert result == 0
    assert call_count == 1


# ---------------------------------------------------------------------------
# Branch selection: cron vs interval vs run-once
# ---------------------------------------------------------------------------

def test_entrypoint_uses_cron_when_schedule_set():
    """run_schedule set + run_interval falsy → cron-based next_wait passed to _run_scheduled."""
    cfg = _config(run_interval=0, run_schedule="0 2 * * *")
    with patch.object(run, "ConfigNode", return_value=cfg), \
         patch.object(run, "_run_scheduled", return_value=0) as mock_scheduled:
        result = run.entrypoint(args=_args(run_once=False))
    assert result == 0
    mock_scheduled.assert_called_once()
    # exercise the injected provider to prove the CRON branch (not interval) was wired:
    # the cron lambda calls seconds_until_next_cron(now), always strictly positive.
    next_wait = mock_scheduled.call_args.args[1]
    assert next_wait() > 0


def test_entrypoint_uses_interval_when_interval_set():
    """run_interval set + run_schedule None → interval next_wait passed to _run_scheduled."""
    cfg = _config(run_interval=60, run_schedule=None)
    with patch.object(run, "ConfigNode", return_value=cfg), \
         patch.object(run, "_run_scheduled", return_value=0) as mock_scheduled:
        result = run.entrypoint(args=_args(run_once=False))
    assert result == 0
    mock_scheduled.assert_called_once()
    # exercise the injected provider to prove the INTERVAL branch was wired:
    # the interval lambda returns the configured run_interval verbatim.
    next_wait = mock_scheduled.call_args.args[1]
    assert next_wait() == 60


def test_scheduled_loop_uses_injected_wait_provider():
    """_run_scheduled calls stop.wait with the value returned by next_wait."""
    cfg = _config(run_interval=0)
    stop_event = threading.Event()
    call_count = 0

    def _run_side_effect(_config, _stop=None):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("transient failure")

    def _wait_side_effect(timeout=None):
        stop_event.set()
        return False

    with patch.object(run, "run", side_effect=_run_side_effect), \
         patch("bookstack_file_exporter.run.signal.signal"), \
         patch.object(stop_event, "wait", side_effect=_wait_side_effect) as mock_wait, \
         patch("bookstack_file_exporter.run.threading.Event", return_value=stop_event):
        result = run._run_scheduled(cfg, lambda: 5)

    assert result == 0
    mock_wait.assert_called_once_with(5)


# ---------------------------------------------------------------------------
# Health server wiring in _run_scheduled (F4)
# ---------------------------------------------------------------------------

class TestScheduledHealthServer:
    def test_no_health_port_does_not_start_server(self):
        cfg = _config(run_interval=5, health_port=None)
        stop_event = threading.Event()

        def _run_side_effect(_config, _stop=None):
            stop_event.set()

        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch.object(run, "run", side_effect=_run_side_effect), \
             patch("bookstack_file_exporter.run.signal.signal"), \
             patch("bookstack_file_exporter.run.start_health_server") as mock_start, \
             patch("bookstack_file_exporter.run.threading.Event", return_value=stop_event):
            result = run.entrypoint(args=_args(run_once=False))

        assert result == 0
        mock_start.assert_not_called()

    def test_health_port_starts_and_shuts_down_server(self):
        cfg = _config(run_interval=5, health_port=8080)
        stop_event = threading.Event()
        fake_server = MagicMock()

        def _run_side_effect(_config, _stop=None):
            stop_event.set()

        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch.object(run, "run", side_effect=_run_side_effect), \
             patch("bookstack_file_exporter.run.signal.signal"), \
             patch("bookstack_file_exporter.run.start_health_server",
                   return_value=fake_server) as mock_start, \
             patch("bookstack_file_exporter.run.threading.Event", return_value=stop_event):
            result = run.entrypoint(args=_args(run_once=False))

        assert result == 0
        mock_start.assert_called_once()
        assert mock_start.call_args.args[0] == "0.0.0.0"
        assert mock_start.call_args.args[1] == 8080
        fake_server.shutdown.assert_called_once()

    def test_health_status_marks_cycle_outcome(self):
        cfg = _config(run_interval=5, health_port=8080)
        stop_event = threading.Event()
        captured = {}

        def _run_side_effect(_config, _stop=None):
            stop_event.set()
            return NotifyResult(local="/bkps/export.tgz")

        def _fake_start(host, port, status):
            captured["status"] = status
            return MagicMock()

        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch.object(run, "run", side_effect=_run_side_effect), \
             patch("bookstack_file_exporter.run.signal.signal"), \
             patch("bookstack_file_exporter.run.start_health_server", side_effect=_fake_start), \
             patch("bookstack_file_exporter.run.threading.Event", return_value=stop_event):
            result = run.entrypoint(args=_args(run_once=False))

        assert result == 0
        snap = captured["status"].snapshot()
        assert snap["run_count"] == 1
        assert snap["last_run"]["status"] == "success"
        assert snap["last_run"]["archive_file"] == "export.tgz"

    def test_cancelled_cycle_marks_neither_success_nor_degraded(self):
        """run() returning None means the cycle was cancelled by shutdown, not
        that it finished -- health must keep its last real state rather than
        being marked for a cycle that never completed."""
        cfg = _config(run_interval=5, health_port=8080)
        stop_event = threading.Event()

        def _run_side_effect(_config, _stop=None):
            stop_event.set()

        fake_status = MagicMock()

        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch.object(run, "run", side_effect=_run_side_effect), \
             patch("bookstack_file_exporter.run.signal.signal"), \
             patch("bookstack_file_exporter.run.RunStatus", return_value=fake_status), \
             patch("bookstack_file_exporter.run.start_health_server", return_value=MagicMock()), \
             patch("bookstack_file_exporter.run.threading.Event", return_value=stop_event):
            result = run.entrypoint(args=_args(run_once=False))

        assert result == 0
        fake_status.mark_success.assert_not_called()
        fake_status.mark_degraded.assert_not_called()

    def test_empty_cycle_marks_success(self):
        """An EMPTY-status cycle (nothing to archive) is a real outcome, not a
        cancellation -- it must still be marked via mark_success."""
        cfg = _config(run_interval=5, health_port=8080)
        stop_event = threading.Event()
        empty_result = NotifyResult(status=ExportStatus.EMPTY, export_level="pages")

        def _run_side_effect(_config, _stop=None):
            stop_event.set()
            return empty_result

        fake_status = MagicMock()

        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch.object(run, "run", side_effect=_run_side_effect), \
             patch("bookstack_file_exporter.run.signal.signal"), \
             patch("bookstack_file_exporter.run.RunStatus", return_value=fake_status), \
             patch("bookstack_file_exporter.run.start_health_server", return_value=MagicMock()), \
             patch("bookstack_file_exporter.run.threading.Event", return_value=stop_event):
            result = run.entrypoint(args=_args(run_once=False))

        assert result == 0
        fake_status.mark_success.assert_called_once_with(empty_result)
        fake_status.mark_degraded.assert_not_called()

    def test_partial_cycle_marks_degraded(self):
        """A PARTIAL cycle (content loss, archive survived) must degrade health,
        never mark_success."""
        cfg = _config(run_interval=5, health_port=8080)
        stop_event = threading.Event()
        partial_result = NotifyResult(status=ExportStatus.PARTIAL, local="bkps/a.tgz",
                                      failed_assets=["images/a.png"], export_level="pages")

        def _run_side_effect(_config, _stop=None):
            stop_event.set()
            return partial_result

        fake_status = MagicMock()

        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch.object(run, "run", side_effect=_run_side_effect), \
             patch("bookstack_file_exporter.run.signal.signal"), \
             patch("bookstack_file_exporter.run.RunStatus", return_value=fake_status), \
             patch("bookstack_file_exporter.run.start_health_server", return_value=MagicMock()), \
             patch("bookstack_file_exporter.run.threading.Event", return_value=stop_event):
            result = run.entrypoint(args=_args(run_once=False))

        assert result == 0
        fake_status.mark_degraded.assert_called_once_with(partial_result)
        fake_status.mark_success.assert_not_called()


# ---------------------------------------------------------------------------
# _run_scheduled() — double-signal force-kill (SIG_DFL restore)
# ---------------------------------------------------------------------------

class TestDoubleSignalForceKill:
    def test_first_signal_restores_default_handler(self):
        cfg = _config(run_interval=5)
        stop_event = threading.Event()
        captured = {}

        def _capture_signal(signum, handler):
            # remember the handler installed for SIGTERM so we can invoke it
            if signum == signal.SIGTERM and callable(handler):
                captured["handler"] = handler

        def _run_side_effect(_config, _stop=None):
            stop_event.set()

        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch.object(run, "run", side_effect=_run_side_effect), \
             patch("bookstack_file_exporter.run.signal.signal",
                   side_effect=_capture_signal) as mock_signal, \
             patch("bookstack_file_exporter.run.threading.Event", return_value=stop_event):
            run.entrypoint(args=_args(run_once=False))
            # simulate first SIGTERM arriving: invoke the installed handler
            mock_signal.reset_mock()
            captured["handler"](signal.SIGTERM, None)

        # handler must (a) set stop, (b) restore SIG_DFL for BOTH catchable
        # signals so any second signal (not just an identical repeat) force-kills
        assert stop_event.is_set()
        mock_signal.assert_any_call(signal.SIGTERM, signal.SIG_DFL)
        mock_signal.assert_any_call(signal.SIGINT, signal.SIG_DFL)

    def test_run_called_with_stop_event(self):
        cfg = _config(run_interval=5)
        stop_event = threading.Event()

        def _run_side_effect(_config, _stop=None):
            assert _stop is stop_event
            stop_event.set()

        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch.object(run, "run", side_effect=_run_side_effect) as mock_run, \
             patch("bookstack_file_exporter.run.signal.signal"), \
             patch("bookstack_file_exporter.run.threading.Event", return_value=stop_event):
            result = run.entrypoint(args=_args(run_once=False))

        assert result == 0
        # run() received the stop event positionally or by keyword
        assert mock_run.call_count == 1


# ---------------------------------------------------------------------------
# _run_once() — direct status/exit-code tests
# ---------------------------------------------------------------------------

def test_run_once_returns_zero_on_success():
    with patch("bookstack_file_exporter.run.signal.signal"), \
         patch.object(run, "run",
                      return_value=NotifyResult(status=ExportStatus.SUCCESS, local="/a/b.tgz")):
        assert run._run_once(MagicMock()) == 0


def test_run_once_returns_three_on_partial():
    with patch("bookstack_file_exporter.run.signal.signal"), \
         patch.object(run, "run",
                      return_value=NotifyResult(status=ExportStatus.PARTIAL, local="/a/b.tgz")):
        assert run._run_once(MagicMock()) == 3


def test_run_once_returns_one_on_exception():
    with patch("bookstack_file_exporter.run.signal.signal"), \
         patch.object(run, "run", side_effect=RuntimeError("boom")):
        assert run._run_once(MagicMock()) == 1


def test_run_once_returns_zero_when_result_none():
    """Defensive guard only: one-shot mode never passes a stop flag, so run()
    cannot actually return None here (that path requires cooperative shutdown).
    The guard exists purely to avoid a KeyError if that ever changes."""
    with patch("bookstack_file_exporter.run.signal.signal"), \
         patch.object(run, "run", return_value=None):
        assert run._run_once(MagicMock()) == 0


def test_run_once_returns_zero_on_empty():
    """Nothing-to-archive is a clean outcome (exit 0), same as SUCCESS."""
    with patch("bookstack_file_exporter.run.signal.signal"), \
         patch.object(run, "run",
                      return_value=NotifyResult(status=ExportStatus.EMPTY,
                                                export_level="pages")):
        assert run._run_once(MagicMock()) == 0
