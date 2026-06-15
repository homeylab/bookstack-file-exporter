"""Tests for run.entrypoint dispatch (single run vs interval loop) and
export-level node selection in run.exporter."""
# pylint: disable=missing-class-docstring,missing-function-docstring,unused-argument
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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

        mock_notif_instance.do_notify.assert_called_once_with()

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
        mock_notif_instance.do_notify.assert_called_once_with()
