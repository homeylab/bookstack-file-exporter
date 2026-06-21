"""Tests for run.entrypoint dispatch (single run vs interval loop) and
export-level node selection in run.exporter."""
# pylint: disable=missing-class-docstring,missing-function-docstring,unused-argument
import logging
import signal
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from bookstack_file_exporter import run
from bookstack_file_exporter.notify.models import NotifyResult


def _config(run_interval, run_once=False, run_schedule=None):
    """Return a minimal fake args + config pair for entrypoint tests."""
    return SimpleNamespace(
        user_inputs=SimpleNamespace(run_interval=run_interval, run_schedule=run_schedule)
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
             patch.object(run, "run"):
            result = run.entrypoint(args=_args())
        assert result == 0

    def test_run_raises_exception_returns_1(self, caplog):
        cfg = self._cfg_no_interval()
        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch.object(run, "run", side_effect=RuntimeError("export boom")), \
             caplog.at_level(logging.ERROR, logger="bookstack_file_exporter.run"):
            result = run.entrypoint(args=_args())
        assert result == 1
        assert any("Export failed" in r.message for r in caplog.records)

    def test_run_raises_exception_no_traceback_propagated(self):
        """Exception must NOT escape entrypoint."""
        cfg = self._cfg_no_interval()
        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch.object(run, "run", side_effect=RuntimeError("boom")):
            # should not raise
            result = run.entrypoint(args=_args())
        assert result == 1

    def test_keyboard_interrupt_returns_130(self):
        cfg = self._cfg_no_interval()
        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch.object(run, "run", side_effect=KeyboardInterrupt):
            result = run.entrypoint(args=_args())
        assert result == 130


# ---------------------------------------------------------------------------
# run_once flag forces _run_once even when run_interval is set
# ---------------------------------------------------------------------------

class TestRunOnceFlag:
    def test_run_once_flag_true_forces_single_run_even_with_interval(self):
        cfg = _config(run_interval=60)
        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch.object(run, "run") as mock_run:
            result = run.entrypoint(args=_args(run_once=True))
        assert result == 0
        assert mock_run.call_count == 1

    def test_run_once_flag_false_with_no_interval_still_runs_once(self):
        cfg = _config(run_interval=0)
        with patch.object(run, "ConfigNode", return_value=cfg), \
             patch.object(run, "run") as mock_run:
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

        def _run_side_effect(_config):
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

        def _run_side_effect(_config):
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

        def _run_side_effect(_config):
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

        def _run_side_effect(_config):
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
         patch.object(run, "run") as mock_run:
        result = run.entrypoint(args=_args())
    assert result == 0
    assert mock_run.call_count == 1


def test_entrypoint_loops_when_interval_set():
    cfg = _config(run_interval=5)
    stop_event = threading.Event()
    call_count = 0

    def _run_side_effect(_config):
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

    def _run_side_effect(_config):
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
# Helpers for exporter() dispatch tests
# ---------------------------------------------------------------------------

def _make_exporter_config(export_level: str):
    """Return a MagicMock config suitable for run.exporter()."""
    config = MagicMock()
    config.user_inputs.export_level = export_level
    config.user_inputs.run_interval = 0
    config.user_inputs.notifications = None
    return config


def _patch_exporter_collaborators(monkeypatch, config, book_nodes, chapter_nodes, page_nodes):
    """Patch all external collaborators used by run.exporter().

    Returns (mock_archiver, mock_export_helper).
    """
    # HttpHelper
    monkeypatch.setattr("bookstack_file_exporter.run.HttpHelper", MagicMock())

    mock_export_helper = MagicMock()
    mock_export_helper.get_all_shelves.return_value = {"shelf1": MagicMock()}
    mock_export_helper.get_all_books.return_value = book_nodes
    mock_export_helper.get_chapter_nodes.return_value = chapter_nodes
    mock_export_helper.get_all_pages.return_value = page_nodes
    monkeypatch.setattr("bookstack_file_exporter.run.NodeExporter",
                        MagicMock(return_value=mock_export_helper))

    mock_archiver = MagicMock()
    monkeypatch.setattr("bookstack_file_exporter.run.Archiver",
                        MagicMock(return_value=mock_archiver))

    return mock_archiver, mock_export_helper


# ---------------------------------------------------------------------------
# export_level dispatch: pages (default)
# ---------------------------------------------------------------------------

class TestExporterDispatchPages:
    def test_pages_level_calls_get_all_pages(self, monkeypatch):
        config = _make_exporter_config("pages")
        book_nodes = {1: MagicMock()}
        page_nodes = {10: MagicMock()}
        mock_archiver, mock_export_helper = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes, chapter_nodes={}, page_nodes=page_nodes
        )
        run.exporter(config)
        mock_export_helper.get_all_pages.assert_called_once_with(book_nodes)
        mock_export_helper.get_chapter_nodes.assert_not_called()
        mock_archiver.get_bookstack_exports.assert_called_once_with(page_nodes)

    def test_pages_level_empty_nodes_returns_early(self, monkeypatch, caplog):
        config = _make_exporter_config("pages")
        mock_archiver, _ = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={}
        )
        with caplog.at_level(logging.WARNING, logger="bookstack_file_exporter.run"):
            run.exporter(config)
        # took the empty-nodes branch specifically (not some other early path)
        assert any("Nothing to archive" in r.message for r in caplog.records)
        mock_archiver.get_bookstack_exports.assert_not_called()


# ---------------------------------------------------------------------------
# export_level dispatch: books
# ---------------------------------------------------------------------------

class TestExporterDispatchBooks:
    def test_books_level_uses_book_nodes_directly(self, monkeypatch):
        config = _make_exporter_config("books")
        book_nodes = {1: MagicMock(), 2: MagicMock()}
        mock_archiver, mock_export_helper = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes=book_nodes,
            chapter_nodes={}, page_nodes={}
        )
        run.exporter(config)
        mock_export_helper.get_all_pages.assert_not_called()
        mock_export_helper.get_chapter_nodes.assert_not_called()
        mock_archiver.get_bookstack_exports.assert_called_once_with(book_nodes)

    def test_books_level_empty_nodes_returns_early(self, monkeypatch, caplog):
        config = _make_exporter_config("books")
        mock_archiver, _ = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={},
            chapter_nodes={}, page_nodes={}
        )
        with caplog.at_level(logging.WARNING, logger="bookstack_file_exporter.run"):
            run.exporter(config)
        # took the empty-nodes branch specifically (not some other early path)
        assert any("Nothing to archive" in r.message for r in caplog.records)
        mock_archiver.get_bookstack_exports.assert_not_called()


# ---------------------------------------------------------------------------
# export_level dispatch: chapters
# ---------------------------------------------------------------------------

class TestExporterDispatchChapters:
    def test_chapters_level_calls_get_chapter_nodes(self, monkeypatch):
        config = _make_exporter_config("chapters")
        book_nodes = {1: MagicMock()}
        chapter_nodes = {200: MagicMock()}
        mock_archiver, mock_export_helper = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes=book_nodes,
            chapter_nodes=chapter_nodes, page_nodes={}
        )
        run.exporter(config)
        mock_export_helper.get_chapter_nodes.assert_called_once_with(book_nodes)
        mock_export_helper.get_all_pages.assert_not_called()
        mock_archiver.get_bookstack_exports.assert_called_once_with(chapter_nodes)

    def test_chapters_level_empty_nodes_returns_early(self, monkeypatch, caplog):
        config = _make_exporter_config("chapters")
        mock_archiver, _ = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={}
        )
        with caplog.at_level(logging.WARNING, logger="bookstack_file_exporter.run"):
            run.exporter(config)
        # took the empty-nodes branch specifically (not some other early path)
        assert any("Nothing to archive" in r.message for r in caplog.records)
        mock_archiver.get_bookstack_exports.assert_not_called()


# ---------------------------------------------------------------------------
# Shared tail: create_archive / archive_remote / clean_up always called
# ---------------------------------------------------------------------------

class TestExporterSharedTail:
    def test_shared_tail_called_for_pages_level(self, monkeypatch):
        config = _make_exporter_config("pages")
        mock_archiver, _ = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={10: MagicMock()}
        )
        run.exporter(config)
        mock_archiver.create_archive.assert_called_once()
        mock_archiver.archive_remote.assert_called_once()
        mock_archiver.clean_up.assert_called_once()

    def test_shared_tail_called_for_books_level(self, monkeypatch):
        config = _make_exporter_config("books")
        mock_archiver, _ = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={}
        )
        run.exporter(config)
        mock_archiver.create_archive.assert_called_once()
        mock_archiver.archive_remote.assert_called_once()
        mock_archiver.clean_up.assert_called_once()

    def test_shared_tail_called_for_chapters_level(self, monkeypatch):
        config = _make_exporter_config("chapters")
        mock_archiver, _ = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={10: MagicMock()}, page_nodes={}
        )
        run.exporter(config)
        mock_archiver.create_archive.assert_called_once()
        mock_archiver.archive_remote.assert_called_once()
        mock_archiver.clean_up.assert_called_once()

    def test_skips_shared_tail_when_archiver_exports_nothing(self, monkeypatch):
        config = _make_exporter_config("books")
        mock_archiver, _ = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={}
        )
        # nothing landed in the tar → no content to upload
        mock_archiver.has_exported_content = False

        run.exporter(config)

        mock_archiver.create_archive.assert_not_called()
        mock_archiver.archive_remote.assert_not_called()
        mock_archiver.clean_up.assert_not_called()


# ---------------------------------------------------------------------------
# NodeFilter wiring: filters config → NodeExporter receives node_filter
# ---------------------------------------------------------------------------

class TestExporterNodeFilterWiring:
    def test_node_filter_built_and_passed_when_filters_configured(self, monkeypatch):
        config = _make_exporter_config("books")
        config.user_inputs.filters = {"books": {"include": ["My Book"]}}

        mock_filter_instance = MagicMock()
        mock_node_filter_cls = MagicMock(return_value=mock_filter_instance)
        monkeypatch.setattr("bookstack_file_exporter.run.NodeFilter", mock_node_filter_cls)

        mock_node_exporter_cls = MagicMock()
        mock_node_exporter_cls.return_value.get_all_shelves.return_value = {}
        mock_node_exporter_cls.return_value.get_all_books.return_value = {1: MagicMock()}
        monkeypatch.setattr("bookstack_file_exporter.run.NodeExporter", mock_node_exporter_cls)
        monkeypatch.setattr("bookstack_file_exporter.run.HttpHelper", MagicMock())
        monkeypatch.setattr("bookstack_file_exporter.run.Archiver", MagicMock(
            return_value=MagicMock(has_exported_content=True)
        ))

        run.exporter(config)

        mock_node_filter_cls.assert_called_once_with(config.user_inputs.filters)
        _, kwargs = mock_node_exporter_cls.call_args
        assert kwargs.get("node_filter") is mock_filter_instance

    def test_node_filter_is_none_when_filters_not_configured(self, monkeypatch):
        config = _make_exporter_config("books")
        config.user_inputs.filters = None

        mock_node_filter_cls = MagicMock()
        monkeypatch.setattr("bookstack_file_exporter.run.NodeFilter", mock_node_filter_cls)

        mock_node_exporter_cls = MagicMock()
        mock_node_exporter_cls.return_value.get_all_shelves.return_value = {}
        mock_node_exporter_cls.return_value.get_all_books.return_value = {1: MagicMock()}
        monkeypatch.setattr("bookstack_file_exporter.run.NodeExporter", mock_node_exporter_cls)
        monkeypatch.setattr("bookstack_file_exporter.run.HttpHelper", MagicMock())
        monkeypatch.setattr("bookstack_file_exporter.run.Archiver", MagicMock(
            return_value=MagicMock(has_exported_content=True)
        ))

        run.exporter(config)

        mock_node_filter_cls.assert_not_called()
        _, kwargs = mock_node_exporter_cls.call_args
        assert kwargs.get("node_filter") is None


# ---------------------------------------------------------------------------
# Notification behavior: empty-nodes early return fires SUCCESS notify
# ---------------------------------------------------------------------------

class TestRunNotificationOnEarlyReturn:
    def test_empty_nodes_early_return_fires_success_notification(self, monkeypatch):
        """When notifications are configured and exporter() hits an empty-nodes
        early return, run() must still call do_notify() with no error argument."""
        config = _make_exporter_config("pages")
        config.user_inputs.notifications = {"apprise_urls": ["mock://notify"]}

        _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={}
        )

        mock_notif_instance = MagicMock()
        mock_notif_cls = MagicMock(return_value=mock_notif_instance)
        monkeypatch.setattr("bookstack_file_exporter.run.NotifyHandler", mock_notif_cls)

        run.run(config)

        mock_notif_instance.do_notify.assert_called_once_with(result=None)

    def test_empty_archive_early_return_fires_success_notification(self, monkeypatch):
        """Second early-return site: nodes existed but nothing landed in the tar
        (has_exported_content False). run() must still call do_notify() with no
        error argument, and the downstream archive steps must be skipped."""
        config = _make_exporter_config("pages")
        config.user_inputs.notifications = {"apprise_urls": ["mock://notify"]}

        mock_archiver, _ = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={10: MagicMock()}
        )
        mock_archiver.has_exported_content = False

        mock_notif_instance = MagicMock()
        mock_notif_cls = MagicMock(return_value=mock_notif_instance)
        monkeypatch.setattr("bookstack_file_exporter.run.NotifyHandler", mock_notif_cls)

        run.run(config)

        mock_archiver.create_archive.assert_not_called()
        mock_notif_instance.do_notify.assert_called_once_with(result=None)


# ---------------------------------------------------------------------------
# exporter() return value: None on early returns, NotifyResult on success
# ---------------------------------------------------------------------------

class TestExporterReturnValue:
    def test_empty_nodes_returns_none(self, monkeypatch):
        """empty nodes early return → exporter() returns None."""
        config = _make_exporter_config("pages")
        _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={}
        )
        result = run.exporter(config)
        assert result is None

    def test_no_exported_content_returns_none(self, monkeypatch):
        """has_exported_content=False early return → exporter() returns None."""
        config = _make_exporter_config("pages")
        mock_archiver, _ = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={10: MagicMock()}
        )
        mock_archiver.has_exported_content = False
        result = run.exporter(config)
        assert result is None

    def test_success_returns_notify_result(self, monkeypatch):
        """Happy path → exporter() returns a populated NotifyResult."""
        config = _make_exporter_config("pages")
        mock_archiver, _ = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={10: MagicMock()}
        )
        mock_archiver.has_exported_content = True
        mock_archiver.archive_remote.return_value = ["bucket/export.tgz"]
        mock_archiver.clean_up.return_value = ["/local/export.tgz"]
        mock_archiver.archive_file = "/local/export.tgz"

        result = run.exporter(config)

        assert isinstance(result, NotifyResult)
        assert result.local == "/local/export.tgz"
        assert result.remote == ["bucket/export.tgz"]
        assert result.removed == ["/local/export.tgz"]

    def test_success_path_do_notify_called_with_result(self, monkeypatch):
        """On success, run() calls do_notify(result=<NotifyResult>)."""
        config = _make_exporter_config("pages")
        config.user_inputs.notifications = {"apprise_urls": ["mock://notify"]}
        mock_archiver, _ = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={10: MagicMock()}
        )
        mock_archiver.has_exported_content = True
        mock_archiver.archive_remote.return_value = []
        mock_archiver.clean_up.return_value = []
        mock_archiver.archive_file = "/local/export.tgz"

        mock_notif_instance = MagicMock()
        monkeypatch.setattr(
            "bookstack_file_exporter.run.NotifyHandler",
            MagicMock(return_value=mock_notif_instance),
        )

        run.run(config)

        call_kwargs = mock_notif_instance.do_notify.call_args
        assert call_kwargs is not None
        result_arg = call_kwargs.kwargs.get("result")
        assert isinstance(result_arg, NotifyResult)
        assert result_arg.local == "/local/export.tgz"
