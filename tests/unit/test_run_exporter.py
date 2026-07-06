"""Tests for run.exporter() -- export_level dispatch, shared archive tail,
return value, stop-flag wiring -- plus run()-level notification behavior driven
through the same exporter collaborators (split out of test_run.py)."""
# pylint: disable=missing-class-docstring,missing-function-docstring,unused-argument,protected-access
import logging
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from bookstack_file_exporter import run
from bookstack_file_exporter.archiver.archiver import AggregateUploadError
from bookstack_file_exporter.archiver.util import ArchiveWriteError
from bookstack_file_exporter.notify.models import ExportStatus, NotifyResult, UploadOutcome

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
    # real Archiver returns empty ledgers by default; a bare MagicMock attribute
    # is truthy and would wrongly downgrade every test run to PARTIAL
    mock_archiver.failed_nodes = []
    mock_archiver.failed_assets = []
    mock_archiver.content_written = True
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
        early return, run() must still call do_notify() with an EMPTY result
        (not None -- None is reserved for shutdown cancellation)."""
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

        mock_notif_instance.do_notify.assert_called_once()
        result_arg = mock_notif_instance.do_notify.call_args.kwargs.get("result")
        assert isinstance(result_arg, NotifyResult)
        assert result_arg.status is ExportStatus.EMPTY
        assert result_arg.export_level == "pages"

    def test_empty_archive_early_return_fires_success_notification(self, monkeypatch):
        """Second early-return site: nodes existed but nothing landed in the tar
        (has_exported_content False). run() must still call do_notify() with an
        EMPTY result, and the downstream archive steps must be skipped."""
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
        mock_notif_instance.do_notify.assert_called_once()
        result_arg = mock_notif_instance.do_notify.call_args.kwargs.get("result")
        assert isinstance(result_arg, NotifyResult)
        assert result_arg.status is ExportStatus.EMPTY

    def test_cancelled_run_does_not_notify(self, monkeypatch):
        """exporter() returning None means the cycle was cancelled by shutdown,
        not that it produced an outcome -- run() must skip notification
        entirely rather than report a cancellation as a success."""
        config = _make_exporter_config("pages")
        config.user_inputs.notifications = {"apprise_urls": ["mock://notify"]}

        monkeypatch.setattr("bookstack_file_exporter.run.exporter", lambda cfg, stop=None: None)

        mock_notif_instance = MagicMock()
        mock_notif_cls = MagicMock(return_value=mock_notif_instance)
        monkeypatch.setattr("bookstack_file_exporter.run.NotifyHandler", mock_notif_cls)

        result = run.run(config)

        assert result is None
        mock_notif_instance.do_notify.assert_not_called()


# ---------------------------------------------------------------------------
# exporter() return value: EMPTY NotifyResult on nothing-to-archive early
# returns, populated NotifyResult on success. None is reserved exclusively for
# shutdown cancellation (see TestExporterStopWiring below).
# ---------------------------------------------------------------------------

class TestExporterReturnValue:
    def test_empty_nodes_returns_empty_status(self, monkeypatch):
        """empty nodes early return → exporter() returns an EMPTY NotifyResult."""
        config = _make_exporter_config("pages")
        _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={}
        )
        result = run.exporter(config)
        assert isinstance(result, NotifyResult)
        assert result.status is ExportStatus.EMPTY
        assert result.export_level == "pages"

    def test_no_exported_content_returns_empty_status(self, monkeypatch):
        """has_exported_content=False early return → exporter() returns an
        EMPTY NotifyResult."""
        config = _make_exporter_config("pages")
        mock_archiver, _ = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={10: MagicMock()}
        )
        mock_archiver.has_exported_content = False
        result = run.exporter(config)
        assert isinstance(result, NotifyResult)
        assert result.status is ExportStatus.EMPTY
        assert result.export_level == "pages"

    def test_success_returns_notify_result(self, monkeypatch):
        """Happy path → exporter() returns a populated NotifyResult."""
        config = _make_exporter_config("pages")
        mock_archiver, _ = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={10: MagicMock()}
        )
        mock_archiver.has_exported_content = True
        mock_archiver.archive_remote.return_value = [
            UploadOutcome("s3/b", "bucket/export.tgz", None)]
        mock_archiver.resolve_remote_status.return_value = ExportStatus.SUCCESS
        mock_archiver.clean_up.return_value = ["/local/export.tgz"]
        mock_archiver.archive_file = "/local/export.tgz"

        result = run.exporter(config)

        assert isinstance(result, NotifyResult)
        assert result.local == "/local/export.tgz"
        assert result.status is ExportStatus.SUCCESS
        assert [o.dest for o in result.uploads] == ["bucket/export.tgz"]
        assert result.removed == ["/local/export.tgz"]
        assert result.cleanup_error is None

    def test_local_cleanup_failure_downgrades_to_partial(self, monkeypatch):
        """clean_up() raising must not fail the run: the export and uploads already
        produced durable copies, so a failed local prune is housekeeping (mirrors the
        remote retention-failure pattern in archiver._upload)."""
        config = _make_exporter_config("pages")
        mock_archiver, _ = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={10: MagicMock()}
        )
        mock_archiver.has_exported_content = True
        mock_archiver.archive_remote.return_value = [
            UploadOutcome("s3/b", "bucket/export.tgz", None)]
        mock_archiver.resolve_remote_status.return_value = ExportStatus.SUCCESS
        mock_archiver.clean_up.side_effect = OSError("permission denied")
        mock_archiver.archive_file = "/local/export.tgz"

        result = run.exporter(config)

        assert isinstance(result, NotifyResult)
        assert result.status is ExportStatus.PARTIAL
        assert not result.removed
        assert "permission denied" in result.cleanup_error

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
        mock_archiver.resolve_remote_status.return_value = ExportStatus.SUCCESS
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

    def test_success_path_notify_failure_does_not_fail_run(self, monkeypatch, caplog):
        """B2: a notification-send exception on the success path must not turn a
        successful export into a failed run (mirrors the failure-path wrapper)."""
        config = _make_exporter_config("pages")
        config.user_inputs.notifications = {"apprise_urls": ["mock://notify"]}
        mock_archiver, _ = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={10: MagicMock()}
        )
        mock_archiver.has_exported_content = True
        mock_archiver.archive_remote.return_value = []
        mock_archiver.resolve_remote_status.return_value = ExportStatus.SUCCESS
        mock_archiver.clean_up.return_value = []
        mock_archiver.archive_file = "/local/export.tgz"

        mock_notif_instance = MagicMock()
        mock_notif_instance.do_notify.side_effect = RuntimeError("notify boom")
        monkeypatch.setattr(
            "bookstack_file_exporter.run.NotifyHandler",
            MagicMock(return_value=mock_notif_instance),
        )

        with caplog.at_level(logging.ERROR, logger="bookstack_file_exporter.run"):
            result = run.run(config)

        assert isinstance(result, NotifyResult)
        assert result.status is ExportStatus.SUCCESS
        assert any("Failed to send notification" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# exporter() — stop-flag wiring (set_stop / sweep_orphans / discard_incomplete)
# ---------------------------------------------------------------------------

class TestExporterStopWiring:
    def _cfg(self):
        # NOTE: unassigned_book_dir is read TOP-LEVEL by exporter()
        # (`config.unassigned_book_dir`, run.py -> config_helper), NOT off
        # user_inputs. Putting it under ui raises AttributeError.
        ui = SimpleNamespace(
            http_config=MagicMock(), filters=None, export_level="pages",
            notifications=None, export_workers=1)
        return SimpleNamespace(
            user_inputs=ui, headers={}, urls={}, unassigned_book_dir=None)

    def test_exporter_injects_stop_into_node_exporter(self):
        cfg = self._cfg()
        stop = threading.Event()
        archive = MagicMock()
        with patch.object(run, "HttpHelper"), \
             patch.object(run, "NodeExporter") as mock_exp, \
             patch.object(run, "Archiver", return_value=archive):
            mock_exp.return_value.get_all_shelves.return_value = {}
            mock_exp.return_value.get_all_books.return_value = {}
            mock_exp.return_value.get_all_pages.return_value = {}
            run.exporter(cfg, stop)

        # the fetch layer must receive the same shutdown flag the archiver does
        _, kwargs = mock_exp.call_args
        assert kwargs["stop"] is stop

    def test_exporter_skips_archive_when_stop_set_after_fetch(self):
        cfg = self._cfg()
        stop = threading.Event()
        stop.set()
        archive = MagicMock()
        with patch.object(run, "HttpHelper"), \
             patch.object(run, "NodeExporter") as mock_exp, \
             patch.object(run, "Archiver", return_value=archive):
            mock_exp.return_value.get_all_shelves.return_value = {}
            mock_exp.return_value.get_all_books.return_value = {1: MagicMock()}
            mock_exp.return_value.get_all_pages.return_value = {1: MagicMock()}
            result = run.exporter(cfg, stop)

        archive.set_stop.assert_called_once_with(stop)
        archive.sweep_orphans.assert_called_once()
        # cancelled during fetch -> skip the archive phase entirely (truncated tree)
        archive.get_bookstack_exports.assert_not_called()
        archive.create_archive.assert_not_called()
        assert result is None

    def test_exporter_discards_incomplete_on_mid_archive_stop(self):
        cfg = self._cfg()
        stop = threading.Event()  # not set during fetch
        archive = MagicMock()
        # simulate a signal landing while the archive loop runs
        archive.get_bookstack_exports.side_effect = lambda _nodes: stop.set()
        with patch.object(run, "HttpHelper"), \
             patch.object(run, "NodeExporter") as mock_exp, \
             patch.object(run, "Archiver", return_value=archive):
            mock_exp.return_value.get_all_shelves.return_value = {}
            mock_exp.return_value.get_all_books.return_value = {1: MagicMock()}
            mock_exp.return_value.get_all_pages.return_value = {1: MagicMock()}
            result = run.exporter(cfg, stop)

        archive.get_bookstack_exports.assert_called_once()
        # mid-cycle stop -> discard the incomplete tar, never gzip/upload
        archive.create_archive.assert_not_called()
        archive.discard_incomplete.assert_called_once()
        assert result is None

    def test_exporter_discards_incomplete_on_exception(self):
        cfg = self._cfg()
        archive = MagicMock()
        archive.get_bookstack_exports.side_effect = RuntimeError("mid-cycle boom")
        with patch.object(run, "HttpHelper"), \
             patch.object(run, "NodeExporter") as mock_exp, \
             patch.object(run, "Archiver", return_value=archive):
            mock_exp.return_value.get_all_shelves.return_value = {}
            mock_exp.return_value.get_all_books.return_value = {1: MagicMock()}
            mock_exp.return_value.get_all_pages.return_value = {1: MagicMock()}
            with pytest.raises(RuntimeError):
                run.exporter(cfg, None)
        archive.discard_incomplete.assert_called_once()


# ---------------------------------------------------------------------------
# Content loss downgrades the run to PARTIAL
# ---------------------------------------------------------------------------

class TestExporterContentLoss:
    def _happy_archiver(self, mock_archiver):
        mock_archiver.has_exported_content = True
        mock_archiver.archive_remote.return_value = []
        mock_archiver.resolve_remote_status.return_value = ExportStatus.SUCCESS
        mock_archiver.clean_up.return_value = []
        mock_archiver.archive_file = "/local/export.tgz"

    def test_failed_nodes_downgrade_to_partial(self, monkeypatch):
        config = _make_exporter_config("pages")
        mock_archiver, _ = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={10: MagicMock()}
        )
        self._happy_archiver(mock_archiver)
        mock_archiver.failed_nodes = ["my-book/secret.md"]

        result = run.exporter(config)

        assert result.status is ExportStatus.PARTIAL
        assert result.failed_nodes == ["my-book/secret.md"]
        assert not result.failed_assets

    def test_failed_assets_downgrade_to_partial(self, monkeypatch):
        config = _make_exporter_config("pages")
        mock_archiver, _ = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={10: MagicMock()}
        )
        self._happy_archiver(mock_archiver)
        mock_archiver.failed_assets = ["images/gallery/broken.png"]

        result = run.exporter(config)

        assert result.status is ExportStatus.PARTIAL
        assert result.failed_assets == ["images/gallery/broken.png"]

    def test_no_content_loss_stays_success(self, monkeypatch):
        config = _make_exporter_config("pages")
        mock_archiver, _ = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={10: MagicMock()}
        )
        self._happy_archiver(mock_archiver)

        result = run.exporter(config)

        assert result.status is ExportStatus.SUCCESS
        assert not result.failed_nodes
        assert result.export_level == "pages"

    def test_no_document_archived_raises_hard_failure(self, monkeypatch):
        """Failures recorded and zero node exports landed: NO restorable backup
        exists -- hard failure (exit 1 / failure notification), never Partial
        and never a silent None. Gate is document content, not the tar file:
        holds even when meta/asset writes produced a tar."""
        config = _make_exporter_config("pages")
        mock_archiver, _ = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={10: MagicMock()}
        )
        mock_archiver.has_exported_content = True  # meta-only tar exists
        mock_archiver.content_written = False
        mock_archiver.failed_nodes = ["my-book/secret.md"]

        with pytest.raises(run.NoContentArchivedError) as exc_info:
            run.exporter(config)

        # counts in the message: it becomes the failure notification body
        assert "1 node export(s)" in str(exc_info.value)
        assert "0 asset download(s)" in str(exc_info.value)

    def test_assets_survive_but_no_documents_still_raises(self, monkeypatch):
        """Assets alone are not a restorable backup: node exports all failed ->
        hard failure even though asset downloads succeeded."""
        config = _make_exporter_config("pages")
        mock_archiver, _ = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={10: MagicMock()}
        )
        mock_archiver.has_exported_content = True
        mock_archiver.content_written = False
        mock_archiver.failed_nodes = ["my-book/a.md", "my-book/b.md"]

        with pytest.raises(run.NoContentArchivedError):
            run.exporter(config)

    def test_truly_empty_archive_still_returns_empty_status(self, monkeypatch):
        """Empty ledger + no tar = benign empty instance: EMPTY status, not None."""
        config = _make_exporter_config("pages")
        mock_archiver, _ = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={10: MagicMock()}
        )
        mock_archiver.has_exported_content = False

        result = run.exporter(config)

        assert isinstance(result, NotifyResult)
        assert result.status is ExportStatus.EMPTY


# ---------------------------------------------------------------------------
# A poisoned archive stream must hard-fail the run, never publish as PARTIAL
# ---------------------------------------------------------------------------

class TestExporterPoisonedStream:  # pylint: disable=too-few-public-methods
    def test_poisoned_stream_fails_run_even_with_partial_content(self, monkeypatch):
        """A poisoned archive stream must hard-fail the run, never publish as PARTIAL.

        Earlier nodes succeeded (content_written True, ledger non-empty), so run.py
        would otherwise downgrade to PARTIAL -- but create_archive (finalize) raises
        because the stream is poisoned, and the finally block discards the incomplete
        archive.
        """
        config = _make_exporter_config("pages")
        mock_archiver, _ = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={10: MagicMock()}
        )
        mock_archiver.failed_nodes = ["book/page.md (worker error)"]
        mock_archiver.failed_assets = []
        mock_archiver.content_written = True
        mock_archiver.has_exported_content = True
        mock_archiver.create_archive.side_effect = ArchiveWriteError("poisoned")

        with pytest.raises(ArchiveWriteError):
            run.exporter(config)

        mock_archiver.discard_incomplete.assert_called_once()
        mock_archiver.archive_remote.assert_not_called()


# ---------------------------------------------------------------------------
# Partial run + keep_last<0: retention now always runs (Task 4 removed the
# prune_allowed/allow_prune gate), so a partial run wipes local -- but only
# after a durable remote copy survives. resolve_remote_status raises
# AggregateUploadError (archiver.py) BEFORE _run_local_cleanup runs whenever
# every upload target fails, so local cleanup never executes in that case.
# ---------------------------------------------------------------------------

class TestExporterPartialKeepLastNegativeWipe:
    def test_partial_keep_last_negative_one_upload_ok_wipes_local(self, monkeypatch):
        """partial run (failed_nodes non-empty) + keep_last<0 + >=1 upload OK ->
        local archive still gets wiped (clean_up runs and reports it removed), and
        the run reports PARTIAL (content loss, not the upload outcome, drives the
        downgrade -- see exporter()'s failed_nodes/failed_assets downgrade, run.py:374-375)."""
        config = _make_exporter_config("pages")
        mock_archiver, _ = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={10: MagicMock()}
        )
        mock_archiver.has_exported_content = True
        mock_archiver.failed_nodes = ["my-book/secret.md"]
        mock_archiver.archive_remote.return_value = [
            UploadOutcome("s3/a", "bucket/export.tgz", None),
            UploadOutcome("s3/b", None, "connection refused"),
        ]
        mock_archiver.resolve_remote_status.return_value = ExportStatus.PARTIAL
        mock_archiver.clean_up.return_value = ["/local/export.tgz"]
        mock_archiver.archive_file = "/local/export.tgz"

        result = run.exporter(config)

        mock_archiver.clean_up.assert_called_once()
        assert result.status is ExportStatus.PARTIAL
        assert result.removed == ["/local/export.tgz"]

    def test_partial_keep_last_negative_all_uploads_fail_raises_before_cleanup(
        self, monkeypatch
    ):
        """Same partial run, but every upload target fails: resolve_remote_status
        raises AggregateUploadError (no durable copy survives with keep_last<0)
        BEFORE _run_local_cleanup runs (run.py:369-380), so the local archive is
        never deleted."""
        config = _make_exporter_config("pages")
        mock_archiver, _ = _patch_exporter_collaborators(
            monkeypatch, config, book_nodes={1: MagicMock()},
            chapter_nodes={}, page_nodes={10: MagicMock()}
        )
        mock_archiver.has_exported_content = True
        mock_archiver.failed_nodes = ["my-book/secret.md"]
        mock_archiver.archive_remote.return_value = [
            UploadOutcome("s3/a", None, "connection refused"),
            UploadOutcome("s3/b", None, "timeout"),
        ]
        mock_archiver.resolve_remote_status.side_effect = AggregateUploadError(
            "all upload targets failed; only the local copy remains and keep_last<0 "
            "means a later successful run will prune it: s3/a, s3/b")

        with pytest.raises(AggregateUploadError):
            run.exporter(config)

        mock_archiver.clean_up.assert_not_called()
