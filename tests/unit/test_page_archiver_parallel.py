# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name,unused-argument,protected-access,too-few-public-methods,duplicate-code
"""Cooperative-cancellation, parallel-export, and failure-ledger tests for PageArchiver."""
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest
from requests.exceptions import HTTPError

from bookstack_file_exporter.archiver.node_archiver import PageArchiver
from bookstack_file_exporter.archiver.util import ArchiveWriteError
from tests.fixtures.mock_config import make_mock_config as _make_config


# ---------------------------------------------------------------------------
# 0. Cooperative-shutdown stop flag
# ---------------------------------------------------------------------------

class TestStopFlag:
    def test_stop_requested_false_when_unset(self, page_archiver):
        assert page_archiver._stop_requested() is False

    def test_stop_requested_false_when_event_clear(self, page_archiver):
        page_archiver.set_stop(threading.Event())
        assert page_archiver._stop_requested() is False

    def test_stop_requested_true_when_event_set(self, page_archiver):
        ev = threading.Event()
        ev.set()
        page_archiver.set_stop(ev)
        assert page_archiver._stop_requested() is True


class TestCooperativeCancellation:
    def test_export_nodes_bails_before_first_node_when_stopped(self, page_archiver):
        ev = threading.Event()
        ev.set()
        page_archiver.set_stop(ev)
        page_archiver._download_node_assets = MagicMock()
        page_archiver._get_node_data = MagicMock()

        nodes = {1: MagicMock(), 2: MagicMock()}
        page_archiver._export_nodes(nodes, "pages", {}, {})

        page_archiver._download_node_assets.assert_not_called()
        page_archiver._get_node_data.assert_not_called()

    def test_export_nodes_stops_between_nodes(self, page_archiver):
        ev = threading.Event()
        page_archiver.set_stop(ev)
        page_archiver._download_node_assets = MagicMock(return_value=({}, []))
        # set the flag the moment the first node's data is fetched
        page_archiver._get_node_data = MagicMock(side_effect=lambda url: ev.set() or b"data")
        page_archiver._archive_node = MagicMock()
        page_archiver._archive_node_meta = MagicMock()
        page_archiver.export_formats = ["markdown"]
        page_archiver.export_meta = False

        n1, n2 = MagicMock(), MagicMock()
        n1.id_, n2.id_ = 1, 2
        page_archiver._export_nodes({1: n1, 2: n2}, "pages", {}, {})

        # only the first node was fetched; loop broke before the second
        assert page_archiver._get_node_data.call_count == 1

    def test_download_node_assets_breaks_asset_type_loop_when_stopped(self, page_archiver):
        ev = threading.Event()
        ev.set()
        page_archiver.set_stop(ev)
        page_archiver._archive_node_assets = MagicMock(return_value=set())
        page_archiver._asset_page_map = MagicMock(return_value={1: "page-1"})

        # non-empty maps so the early `return {}` guard does NOT short-circuit;
        # the stop guard at the asset-type loop must break instead.
        result = page_archiver._download_node_assets(
            MagicMock(), {1: ["img"]}, {1: ["att"]})

        page_archiver._archive_node_assets.assert_not_called()
        assert result == ({"images": {}, "attachments": {}}, [])

    def test_archive_node_assets_breaks_asset_loop_when_stopped(self, page_archiver):
        ev = threading.Event()
        ev.set()
        page_archiver.set_stop(ev)
        # asset nodes present; the per-asset guard must break before the first one.
        page_archiver.asset_archiver = MagicMock()
        failed = page_archiver._archive_node_assets(
            "images", "parent/path", "page-1", [MagicMock(), MagicMock()])

        # broke immediately: no asset bytes were fetched (real download call is
        # asset_archiver.get_asset_bytes, node_archiver.py:144)
        page_archiver.asset_archiver.get_asset_bytes.assert_not_called()
        assert failed == set()


# ---------------------------------------------------------------------------
# 14. Parallel export (export_workers > 1)
# ---------------------------------------------------------------------------

class TestParallelExport:
    def _collect_writes(self, archiver):
        """Replace write_data with a thread-safe path collector; returns the list.

        The lock matters: with export_workers>1 several pool threads call write_data
        concurrently, and list.append from multiple threads can race — guard it so
        the test harness itself is sound.
        """
        collected = []
        lock = threading.Lock()

        def _record(path, data):
            with lock:
                collected.append(path)

        archiver.write_data = _record
        return collected

    def test_parallel_writes_all_pages_all_formats(self, tmp_path, build_node):
        """workers>1 over several nodes writes every expected entry (order-independent)."""
        config = _make_config(formats=["markdown", "html"], export_images=False,
                              export_attachments=False, export_meta=False,
                              export_workers=4)
        archiver = PageArchiver(str(tmp_path / "bs"), config, MagicMock(),
                                asset_archiver=MagicMock())
        archiver.asset_archiver.get_asset_nodes.return_value = {}
        assert archiver.export_workers == 4

        parent = build_node(id=1, name="bk", slug="bk")
        pages = {i: build_node(id=i, name=f"p{i}", slug=f"p{i}", parent=parent)
                 for i in range(2, 12)}  # 10 pages

        collected = self._collect_writes(archiver)
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"data",
        ):
            archiver.archive(pages)

        expected = set()
        for i in range(2, 12):
            expected.add(f"{archiver.archive_base_path}/bk/p{i}.md")
            expected.add(f"{archiver.archive_base_path}/bk/p{i}.html")
        assert set(collected) == expected

    def test_parallel_uses_thread_pool(self, tmp_path, build_node):
        """workers>1 routes through ThreadPoolExecutor (serial branch is not taken)."""
        config = _make_config(formats=["markdown"], export_workers=3)
        archiver = PageArchiver(str(tmp_path / "bs"), config, MagicMock(),
                                asset_archiver=MagicMock())
        archiver.asset_archiver.get_asset_nodes.return_value = {}
        parent = build_node(id=1, name="bk", slug="bk")
        pages = {2: build_node(id=2, name="p2", slug="p2", parent=parent)}

        self._collect_writes(archiver)
        # wraps= spies on the call (records max_workers) while still running the
        # real pool, so the export actually executes — we assert it was constructed
        # rather than stubbing it out.
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.ThreadPoolExecutor",
            wraps=ThreadPoolExecutor,
        ) as mock_pool, patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"data",
        ):
            archiver.archive(pages)
        mock_pool.assert_called_once_with(max_workers=3)

    def test_parallel_node_failure_isolated_run_continues(self, tmp_path, build_node):
        """A worker raising a NON-HTTP error skips that node; others still written."""
        config = _make_config(formats=["markdown"], export_workers=4)
        archiver = PageArchiver(str(tmp_path / "bs"), config, MagicMock(),
                                asset_archiver=MagicMock())
        archiver.asset_archiver.get_asset_nodes.return_value = {}
        parent = build_node(id=1, name="bk", slug="bk")
        pages = {i: build_node(id=i, name=f"p{i}", slug=f"p{i}", parent=parent)
                 for i in range(2, 7)}  # 5 pages; id 4 will blow up

        def _byte_response(url, http_client):  # pylint: disable=unused-argument
            if "/pages/4/" in url:
                raise KeyError("malformed attachment payload")  # non-HTTP, not swallowed
            return b"data"

        collected = self._collect_writes(archiver)
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            side_effect=_byte_response,
        ):
            archiver.archive(pages)  # must NOT raise

        # Assert full paths (set-membership) rather than string-splitting the id out;
        # node 4 raised KeyError -> skipped, every other node still written.
        expected = {f"{archiver.archive_base_path}/bk/p{i}.md" for i in (2, 3, 5, 6)}
        assert set(collected) == expected

    def test_parallel_archive_write_error_aborts_run(self, tmp_path, build_node):
        """ArchiveWriteError from a worker aborts the export: the stream is
        poisoned, so remaining nodes can't be written - cancel queued futures
        and propagate instead of logging N per-node failures."""
        config = _make_config(formats=["markdown"], export_workers=2)
        archiver = PageArchiver(str(tmp_path / "bs"), config, MagicMock(),
                                asset_archiver=MagicMock())
        archiver.asset_archiver.get_asset_nodes.return_value = {}
        parent = build_node(id=1, name="bk", slug="bk")
        pages = {i: build_node(id=i, name=f"p{i}", slug=f"p{i}", parent=parent)
                 for i in range(2, 22)}  # 20 pages

        def _boom(path, data):
            raise ArchiveWriteError("archive write failed for x: disk full")
        archiver.write_data = _boom

        cancel_calls = []

        class SpyExecutor(ThreadPoolExecutor):
            def shutdown(self, wait=True, *, cancel_futures=False):
                cancel_calls.append(cancel_futures)
                super().shutdown(wait, cancel_futures=cancel_futures)

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.ThreadPoolExecutor",
            SpyExecutor,
        ), patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"data",
        ):
            with pytest.raises(ArchiveWriteError):
                archiver.archive(pages)

        # The abort path must cancel queued futures (True), not just the
        # with-exit shutdown (False).
        assert True in cancel_calls
        # The aborting error is propagated, not folded into the per-node ledger.
        assert not archiver.failed_node_exports

    def test_parallel_stop_mid_run_does_not_crash(self, tmp_path, build_node):
        """Stop Event set mid-run: no crash, run exits cleanly (partial discarded upstream)."""
        config = _make_config(formats=["markdown"], export_workers=2)
        archiver = PageArchiver(str(tmp_path / "bs"), config, MagicMock(),
                                asset_archiver=MagicMock())
        archiver.asset_archiver.get_asset_nodes.return_value = {}
        ev = threading.Event()
        archiver.set_stop(ev)
        parent = build_node(id=1, name="bk", slug="bk")
        pages = {i: build_node(id=i, name=f"p{i}", slug=f"p{i}", parent=parent)
                 for i in range(2, 22)}  # 20 pages

        def _byte_response(url, http_client):  # pylint: disable=unused-argument
            ev.set()  # trip the stop flag as soon as any fetch happens
            return b"data"

        self._collect_writes(archiver)
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            side_effect=_byte_response,
        ):
            archiver.archive(pages)  # must not raise or hang

    def test_parallel_stop_before_run_writes_and_fetches_nothing(self, tmp_path, build_node):
        """Stop flag already set BEFORE archive(): the submit loop's _stop_requested()
        check breaks on the first node, so no future is submitted -> nothing is
        fetched or written. Deterministic (no scheduling race), unlike the mid-run
        smoke test above: it pins the cooperative-stop short-circuit."""
        config = _make_config(formats=["markdown"], export_workers=4)
        archiver = PageArchiver(str(tmp_path / "bs"), config, MagicMock(),
                                asset_archiver=MagicMock())
        archiver.asset_archiver.get_asset_nodes.return_value = {}
        ev = threading.Event()
        ev.set()  # stop requested up front
        archiver.set_stop(ev)
        parent = build_node(id=1, name="bk", slug="bk")
        pages = {i: build_node(id=i, name=f"p{i}", slug=f"p{i}", parent=parent)
                 for i in range(2, 12)}  # 10 pages

        fetched = []

        def _byte_response(url, http_client):  # pylint: disable=unused-argument
            fetched.append(url)
            return b"data"

        collected = self._collect_writes(archiver)
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            side_effect=_byte_response,
        ):
            archiver.archive(pages)

        assert not collected  # no node written
        assert not fetched    # no node even fetched

    def test_parallel_completed_node_recorded_even_when_stop_set(self, tmp_path, build_node):
        """The node whose future completes in the same as_completed iteration that
        observes the stop flag must still be merged into the ledger. Its bytes are
        already written to the tar by the time the future is done (the worker
        function returns only after the write), so dropping the merge here would
        leave content_written out of sync with what is actually on disk.

        Only one node is submitted, so as_completed has exactly one future to
        yield: whenever the loop observes it as done, ev is already set (the
        worker sets it before returning), which is what made this racy under
        the OLD stop-check-first order and deterministic here.
        """
        config = _make_config(formats=["markdown"], export_images=False,
                              export_attachments=False, export_meta=False,
                              export_workers=2)
        archiver = PageArchiver(str(tmp_path / "bookstack-completed"), config, MagicMock(),
                                asset_archiver=MagicMock())
        archiver.asset_archiver.get_asset_nodes.return_value = {}
        ev = threading.Event()
        archiver.set_stop(ev)

        parent = build_node(id=1, name="bk", slug="bk")
        page = build_node(id=2, name="p2", slug="p2", parent=parent)

        def _byte_response(url, http_client):  # pylint: disable=unused-argument
            ev.set()  # trip stop as the (only) worker is about to return
            return b"data"

        collected = self._collect_writes(archiver)
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            side_effect=_byte_response,
        ):
            archiver.archive({2: page})

        # The write reached the tar...
        assert collected == [f"{archiver.archive_base_path}/bk/p2.md"]
        # ...so the ledger must agree: dropping the merge would strand this
        # False even though content was actually written.
        assert archiver.content_written is True


# ---------------------------------------------------------------------------
# 15. Content-loss ledger: failed node exports / asset downloads are recorded
# ---------------------------------------------------------------------------

class TestFailureLedger:
    def test_ledgers_start_empty(self, page_archiver):
        assert page_archiver.failed_node_exports == []
        assert page_archiver.failed_asset_downloads == []

    def test_failed_node_format_recorded_as_archive_path(self, tmp_path, build_node):
        """The skipped page-format export lands in the ledger as its would-be
        archive path (extension identifies the format)."""
        config = _make_config(formats=["markdown"], export_images=False,
                              export_attachments=False, export_meta=False)
        archiver = PageArchiver(str(tmp_path / "bookstack-ledger"), config, MagicMock(),
                                asset_archiver=MagicMock())
        archiver.asset_archiver.get_asset_nodes.return_value = {}

        parent_node = build_node(id=1, name="a-book", slug="a-book")
        good = build_node(id=30, name="ok", slug="ok", parent=parent_node)
        forbidden = build_node(id=3, name="secret", slug="secret", parent=parent_node)

        def _byte_response(url, http_client):
            if "/pages/3/" in url:
                raise HTTPError("403 Forbidden")
            return b"page bytes"

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            side_effect=_byte_response,
        ), patch(
            "bookstack_file_exporter.archiver.util.TarStream.write"
        ):
            archiver.archive({30: good, 3: forbidden})

        # PageArchiver._node_output_path is node.file_path; markdown ext is .md
        assert archiver.failed_node_exports == [f"{forbidden.file_path}.md"]
        assert not archiver.failed_asset_downloads

    def test_failed_asset_download_recorded_as_relative_path(self, tmp_path, build_node):
        """An asset whose download raises is recorded via get_relative_path
        (images/<page>/<name> — the prefix identifies the asset kind); survivors
        are not recorded."""
        config = _make_config(formats=["markdown"], export_images=True,
                              export_attachments=False, export_meta=False)
        mock_asset_archiver = MagicMock()
        archiver = PageArchiver(str(tmp_path / "bookstack-assets"), config, MagicMock(),
                                asset_archiver=mock_asset_archiver)

        parent_node = build_node(id=1, name="a-book", slug="a-book")
        page = build_node(id=40, name="gallery", slug="gallery", parent=parent_node)

        bad = MagicMock()
        bad.id_ = 100
        bad.get_relative_path.return_value = "images/gallery/broken.png"
        ok = MagicMock()
        ok.id_ = 101
        ok.get_relative_path.return_value = "images/gallery/fine.png"

        mock_asset_archiver.get_asset_nodes.return_value = {40: [bad, ok]}

        def _get_bytes(asset_type, url):
            if url is bad.download_url:
                raise HTTPError("404")
            return b"img"

        mock_asset_archiver.get_asset_bytes.side_effect = _get_bytes

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"page bytes",
        ), patch(
            "bookstack_file_exporter.archiver.util.TarStream.write"
        ):
            archiver.archive({40: page})

        assert archiver.failed_asset_downloads == ["images/gallery/broken.png"]
        assert not archiver.failed_node_exports

    def test_parallel_worker_exception_records_node(self, tmp_path, build_node):
        """A non-HTTP worker crash names the lost node in the ledger."""
        config = _make_config(formats=["markdown"], export_images=False,
                              export_attachments=False, export_meta=False,
                              export_workers=2)
        archiver = PageArchiver(str(tmp_path / "bookstack-par"), config, MagicMock(),
                                asset_archiver=MagicMock())
        archiver.asset_archiver.get_asset_nodes.return_value = {}

        parent_node = build_node(id=1, name="a-book", slug="a-book")
        good = build_node(id=50, name="fine", slug="fine", parent=parent_node)
        crasher = build_node(id=51, name="doomed", slug="doomed", parent=parent_node)

        def _byte_response(url, http_client):
            if "/pages/51/" in url:
                raise RuntimeError("worker boom")  # non-HTTP: not swallowed per-format
            return b"page bytes"

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            side_effect=_byte_response,
        ), patch(
            "bookstack_file_exporter.archiver.util.TarStream.write"
        ):
            archiver.archive({50: good, 51: crasher})

        assert archiver.failed_node_exports == [f"{crasher.file_path} (export error)"]

    def test_serial_node_exception_records_node_and_continues(self, tmp_path, build_node):
        """Serial (default workers=1) now shares the parallel contract: a non-HTTP
        node crash is recorded in the ledger and later nodes still export."""
        config = _make_config(formats=["markdown"], export_images=False,
                              export_attachments=False, export_meta=False)
        archiver = PageArchiver(str(tmp_path / "bookstack-ser"), config, MagicMock(),
                                asset_archiver=MagicMock())
        archiver.asset_archiver.get_asset_nodes.return_value = {}

        parent_node = build_node(id=1, name="a-book", slug="a-book")
        crasher = build_node(id=51, name="doomed", slug="doomed", parent=parent_node)
        good = build_node(id=50, name="fine", slug="fine", parent=parent_node)

        def _byte_response(url, http_client):  # pylint: disable=unused-argument
            if "/pages/51/" in url:
                raise RuntimeError("boom")  # non-HTTP: not swallowed per-format
            return b"page bytes"

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            side_effect=_byte_response,
        ), patch("bookstack_file_exporter.archiver.util.TarStream.write") as mock_write:
            # crasher FIRST: the run must continue past it to the good node
            archiver.archive({51: crasher, 50: good})

        assert archiver.failed_node_exports == [f"{crasher.file_path} (export error)"]
        assert mock_write.call_count == 1  # good page still written

    def test_serial_archive_write_error_still_aborts(self, tmp_path, build_node):
        """ArchiveWriteError means the shared tar stream is poisoned; serial must
        propagate it (same as parallel), not swallow it into the ledger."""
        config = _make_config(formats=["markdown"], export_images=False,
                              export_attachments=False, export_meta=False)
        archiver = PageArchiver(str(tmp_path / "bookstack-ser2"), config, MagicMock(),
                                asset_archiver=MagicMock())
        archiver.asset_archiver.get_asset_nodes.return_value = {}

        parent_node = build_node(id=1, name="a-book", slug="a-book")
        page = build_node(id=50, name="fine", slug="fine", parent=parent_node)

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"page bytes",
        ), patch(
            "bookstack_file_exporter.archiver.util.TarStream.write",
            side_effect=ArchiveWriteError("stream poisoned"),
        ):
            with pytest.raises(ArchiveWriteError):
                archiver.archive({50: page})

    def test_content_written_false_when_all_formats_fail_meta_only(self, tmp_path, build_node):
        """Meta sidecars land in the tar even when every format fetch fails; the
        content flag must stay False so upstream treats the run as a hard
        failure, not a partial backup of metadata."""
        config = _make_config(formats=["markdown"], export_images=False,
                              export_attachments=False, export_meta=True)
        archiver = PageArchiver(str(tmp_path / "bookstack-meta-only"), config, MagicMock(),
                                asset_archiver=MagicMock())
        archiver.asset_archiver.get_asset_nodes.return_value = {}

        parent_node = build_node(id=1, name="a-book", slug="a-book")
        page = build_node(id=60, name="doomed", slug="doomed", parent=parent_node)

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            side_effect=HTTPError("500"),
        ), patch(
            "bookstack_file_exporter.archiver.util.TarStream.write"
        ) as mock_stream_write:
            archiver.archive({60: page})

        # meta WAS written (tar exists) but no document content did
        assert mock_stream_write.call_count == 1
        assert archiver.content_written is False
        assert archiver.failed_node_exports == [f"{page.file_path}.md"]

    def test_content_written_true_when_any_format_lands(self, tmp_path, build_node):
        config = _make_config(formats=["markdown"], export_images=False,
                              export_attachments=False, export_meta=False)
        archiver = PageArchiver(str(tmp_path / "bookstack-content"), config, MagicMock(),
                                asset_archiver=MagicMock())
        archiver.asset_archiver.get_asset_nodes.return_value = {}

        parent_node = build_node(id=1, name="a-book", slug="a-book")
        page = build_node(id=61, name="fine", slug="fine", parent=parent_node)

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"page bytes",
        ), patch(
            "bookstack_file_exporter.archiver.util.TarStream.write"
        ):
            archiver.archive({61: page})

        assert archiver.content_written is True
