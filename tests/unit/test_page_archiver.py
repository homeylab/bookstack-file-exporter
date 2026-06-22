# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name,unused-argument,protected-access,too-few-public-methods
"""Happy-path unit tests for PageArchiver."""
from typing import Dict
from unittest.mock import MagicMock, patch

import pytest
from requests.exceptions import HTTPError

from bookstack_file_exporter.archiver.node_archiver import NodeArchiver, PageArchiver
from bookstack_file_exporter.exporter.node import Node


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

from tests.fixtures.mock_config import make_mock_config as _make_config


def _make_page_node(build_node, page_id: int, slug: str, parent: Node) -> Node:
    """Construct a leaf page Node with the given parent."""
    return build_node(id=page_id, name=slug, slug=slug, parent=parent)


@pytest.fixture
def page_archiver(tmp_path):
    """Construct a PageArchiver with all external collaborators mocked."""
    config = _make_config()
    http_client = MagicMock()
    archive_dir = str(tmp_path / "bookstack-20260514")
    return PageArchiver(archive_dir, config, http_client, asset_archiver=MagicMock())


# ---------------------------------------------------------------------------
# 0. Cooperative-shutdown stop flag
# ---------------------------------------------------------------------------

class TestStopFlag:
    def test_stop_defaults_to_none(self, page_archiver):
        assert page_archiver._stop is None

    def test_stop_requested_false_when_unset(self, page_archiver):
        assert page_archiver._stop_requested() is False

    def test_stop_requested_false_when_event_clear(self, page_archiver):
        import threading
        page_archiver._stop = threading.Event()
        assert page_archiver._stop_requested() is False

    def test_stop_requested_true_when_event_set(self, page_archiver):
        import threading
        ev = threading.Event()
        ev.set()
        page_archiver._stop = ev
        assert page_archiver._stop_requested() is True


class TestCooperativeCancellation:
    def test_export_nodes_bails_before_first_node_when_stopped(self, page_archiver):
        import threading
        ev = threading.Event(); ev.set()
        page_archiver._stop = ev
        page_archiver._download_node_assets = MagicMock()
        page_archiver._get_node_data = MagicMock()

        nodes = {1: MagicMock(), 2: MagicMock()}
        page_archiver._export_nodes(nodes, "pages", {}, {})

        page_archiver._download_node_assets.assert_not_called()
        page_archiver._get_node_data.assert_not_called()

    def test_export_nodes_stops_between_nodes(self, page_archiver):
        import threading
        ev = threading.Event()
        page_archiver._stop = ev
        page_archiver._download_node_assets = MagicMock(return_value={})
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
        import threading
        ev = threading.Event(); ev.set()
        page_archiver._stop = ev
        page_archiver._archive_node_assets = MagicMock(return_value=set())
        page_archiver._asset_page_map = MagicMock(return_value={1: "page-1"})

        # non-empty maps so the early `return {}` guard does NOT short-circuit;
        # the stop guard at the asset-type loop must break instead.
        result = page_archiver._download_node_assets(
            MagicMock(), {1: ["img"]}, {1: ["att"]})

        page_archiver._archive_node_assets.assert_not_called()
        assert result == {"images": {}, "attachments": {}}

    def test_archive_node_assets_breaks_asset_loop_when_stopped(self, page_archiver):
        import threading
        ev = threading.Event(); ev.set()
        page_archiver._stop = ev
        # asset nodes present; the per-asset guard must break before the first one.
        page_archiver.asset_archiver = MagicMock()
        failed = page_archiver._archive_node_assets(
            "images", "parent/path", "page-1", [MagicMock(), MagicMock()])

        # broke immediately: no asset bytes were fetched (real download call is
        # asset_archiver.get_asset_bytes, node_archiver.py:144)
        page_archiver.asset_archiver.get_asset_bytes.assert_not_called()
        assert failed == set()


# ---------------------------------------------------------------------------
# 1. Construction
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_archive_file_ends_with_tgz(self, tmp_path):
        archive_dir = str(tmp_path / "bookstack-20260514")
        archiver = PageArchiver(archive_dir, _make_config(), MagicMock(),
                                asset_archiver=MagicMock())
        assert archiver.archive_file == f"{archive_dir}.tgz"

    def test_tar_file_ends_with_tar(self, tmp_path):
        archive_dir = str(tmp_path / "bookstack-20260514")
        archiver = PageArchiver(archive_dir, _make_config(), MagicMock(),
                                asset_archiver=MagicMock())
        assert archiver.tar_file == f"{archive_dir}.tar"

    def test_archive_base_path_is_last_segment(self, tmp_path):
        archive_dir = str(tmp_path / "bookstack-20260514")
        archiver = PageArchiver(archive_dir, _make_config(), MagicMock(),
                                asset_archiver=MagicMock())
        assert archiver.archive_base_path == "bookstack-20260514"

    def test_http_client_stored(self, tmp_path):
        http_client = MagicMock()
        archive_dir = str(tmp_path / "bookstack-20260514")
        archiver = PageArchiver(archive_dir, _make_config(), http_client,
                                asset_archiver=MagicMock())
        assert archiver.http_client is http_client


# ---------------------------------------------------------------------------
# 2. Export URL formation (via archive → _export_nodes)
# ---------------------------------------------------------------------------

class TestExportUrl:
    @pytest.mark.parametrize("export_format", ["markdown", "html", "pdf", "plaintext", "zip"])
    def test_url_contains_export_api_path(self, tmp_path, build_node, export_format):
        """archive should call get_byte_response with the correct pages export URL."""
        config = _make_config(formats=[export_format], export_images=False,
                              export_attachments=False, export_meta=False)
        archiver = PageArchiver(str(tmp_path / "bs"), config, MagicMock(),
                                asset_archiver=MagicMock())
        archiver.asset_archiver.get_asset_nodes.return_value = {}
        parent_node = build_node(id=1, name="my-book", slug="my-book")
        page = build_node(id=42, name="my-page", slug="my-page", parent=parent_node)

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response"
        ) as mock_get_bytes, patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ):
            mock_get_bytes.return_value = b"page content"
            archiver.archive({42: page})
            called_url = mock_get_bytes.call_args.kwargs["url"]

        expected = f"https://wiki.test.example/api/pages/42/export/{export_format}"
        assert called_url == expected


# ---------------------------------------------------------------------------
# 3. File extension map property
# ---------------------------------------------------------------------------

class TestFileExtensionMap:
    def test_markdown_extension(self, page_archiver):
        assert page_archiver.file_extension_map["markdown"] == ".md"

    def test_html_extension(self, page_archiver):
        assert page_archiver.file_extension_map["html"] == ".html"

    def test_pdf_extension(self, page_archiver):
        assert page_archiver.file_extension_map["pdf"] == ".pdf"

    def test_plaintext_extension(self, page_archiver):
        assert page_archiver.file_extension_map["plaintext"] == ".txt"

    def test_zip_extension(self, page_archiver):
        assert page_archiver.file_extension_map["zip"] == ".zip"

    def test_tgz_extension(self, page_archiver):
        assert page_archiver.file_extension_map["tgz"] == ".tgz"

    def test_meta_extension(self, page_archiver):
        assert page_archiver.file_extension_map["meta"] == "_meta.json"


# ---------------------------------------------------------------------------
# 4. gzip_archive delegates to archiver_util.create_gzip
# ---------------------------------------------------------------------------

class TestGzipArchive:  # pylint: disable=too-few-public-methods  # test scaffolding stub
    def test_create_gzip_called_with_tar_and_partial_then_renamed(self, page_archiver):
        # gzip writes to the .partial path; os.rename promotes it to the final .tgz.
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.create_gzip"
        ) as mock_create_gzip, patch(
            "bookstack_file_exporter.archiver.node_archiver.os.rename"
        ) as mock_rename:
            page_archiver.gzip_archive()
            partial = f"{page_archiver.archive_file}.partial"
            mock_create_gzip.assert_called_once_with(page_archiver.tar_file, partial)
            mock_rename.assert_called_once_with(partial, page_archiver.archive_file)


class TestAtomicGzip:  # pylint: disable=too-few-public-methods
    def test_gzip_writes_via_partial_then_renames(self, page_archiver, tmp_path, monkeypatch):
        import os
        from bookstack_file_exporter.archiver import util as archiver_util

        tar = tmp_path / "bkps_2026.tar"
        tar.write_bytes(b"tar-bytes")
        page_archiver.tar_file = str(tar)
        page_archiver.archive_file = str(tmp_path / "bkps_2026.tgz")

        seen_target = {}
        real_create_gzip = archiver_util.create_gzip
        def spy(file_path, gzip_file, remove_old=True):
            seen_target["gzip_file"] = gzip_file
            return real_create_gzip(file_path, gzip_file, remove_old)
        monkeypatch.setattr(archiver_util, "create_gzip", spy)

        page_archiver.gzip_archive()

        # gzip was written to the .partial path, not the final name
        assert seen_target["gzip_file"].endswith(".tgz.partial")
        # final archive exists; no partial left behind
        assert os.path.exists(page_archiver.archive_file)
        assert not os.path.exists(page_archiver.archive_file + ".partial")


# ---------------------------------------------------------------------------
# 5. write_data delegates to archiver_util.write_tar
# ---------------------------------------------------------------------------

class TestWriteData:  # pylint: disable=too-few-public-methods  # test scaffolding stub
    def test_write_tar_called_with_correct_args(self, page_archiver):
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ) as mock_write_tar:
            page_archiver.write_data("some/path/file.md", b"content")
            mock_write_tar.assert_called_once_with(
                page_archiver.tar_file, "some/path/file.md", b"content"
            )


# ---------------------------------------------------------------------------
# 6. archive iterates every page node
# ---------------------------------------------------------------------------

class TestArchivePages:
    def test_each_page_node_written_once_per_format(self, tmp_path, build_node):
        """archive should write one file per page per format."""
        mock_asset = MagicMock()
        config = _make_config(formats=["markdown"], export_images=False,
                               export_attachments=False, export_meta=False)
        http_client = MagicMock()
        archive_dir = str(tmp_path / "bookstack-test")
        archiver = PageArchiver(archive_dir, config, http_client, asset_archiver=mock_asset)

        # Make asset_archiver return empty dicts (no images / attachments)
        archiver.asset_archiver.get_asset_nodes.return_value = {}

        # Build a simple parent node and two page nodes
        parent_node = build_node(id=1, name="my-book", slug="my-book")
        page1 = build_node(id=10, name="page-one", slug="page-one", parent=parent_node)
        page2 = build_node(id=11, name="page-two", slug="page-two", parent=parent_node)

        page_nodes: Dict[int, Node] = {10: page1, 11: page2}

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"page bytes",
        ), patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ) as mock_write_tar:
            archiver.archive(page_nodes)

        # 2 pages × 1 format = 2 write_tar calls
        assert mock_write_tar.call_count == 2

    def test_archive_respects_multiple_formats(self, tmp_path, build_node):
        """archive should call write_tar once per page per format."""
        mock_asset = MagicMock()
        config = _make_config(formats=["markdown", "html"], export_images=False,
                               export_attachments=False, export_meta=False)
        http_client = MagicMock()
        archive_dir = str(tmp_path / "bookstack-multi")
        archiver = PageArchiver(archive_dir, config, http_client, asset_archiver=mock_asset)
        archiver.asset_archiver.get_asset_nodes.return_value = {}

        parent_node = build_node(id=1, name="a-book", slug="a-book")
        page1 = build_node(id=20, name="intro", slug="intro", parent=parent_node)
        page_nodes = {20: page1}

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"content",
        ), patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ) as mock_write_tar:
            archiver.archive(page_nodes)

        # 1 page × 2 formats = 2 write_tar calls
        assert mock_write_tar.call_count == 2

    def test_failed_page_format_skipped_run_continues(self, tmp_path, build_node):
        """A 403/404 on one page-format export is skipped, not fatal; others still written."""
        mock_asset = MagicMock()
        config = _make_config(formats=["markdown"], export_images=False,
                              export_attachments=False, export_meta=False)
        archiver = PageArchiver(str(tmp_path / "bookstack-skip"), config, MagicMock(),
                                asset_archiver=mock_asset)
        archiver.asset_archiver.get_asset_nodes.return_value = {}

        parent_node = build_node(id=1, name="a-book", slug="a-book")
        good = build_node(id=30, name="ok", slug="ok", parent=parent_node)
        forbidden = build_node(id=3, name="secret", slug="secret", parent=parent_node)

        def _byte_response(url, http_client):  # pylint: disable=unused-argument
            if "/pages/3/" in url:
                raise HTTPError("403 Forbidden")
            return b"page bytes"

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            side_effect=_byte_response,
        ), patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ) as mock_write_tar:
            archiver.archive({30: good, 3: forbidden})  # must not raise

        # forbidden page skipped, good page written → 1 write
        assert mock_write_tar.call_count == 1


# ---------------------------------------------------------------------------
# 7. Regression: broken verify_ssl property must not exist on PageArchiver
# ---------------------------------------------------------------------------

def test_page_archiver_has_no_verify_ssl_property():
    """verify_ssl was broken (read nonexistent Assets field); confirm it is gone."""
    assert not hasattr(PageArchiver, "verify_ssl")


# ---------------------------------------------------------------------------
# 8. R8: asset_archiver injection seam
# ---------------------------------------------------------------------------

class TestAssetArchiverInjection:
    """Constructor-injected asset_archiver double is stored as self.asset_archiver."""

    def test_injected_double_is_stored(self, tmp_path):
        """When asset_archiver= is supplied, NodeArchiver stores it
        without constructing a real one."""
        double = MagicMock()
        config = _make_config(export_images=True)
        archive_dir = str(tmp_path / "bookstack-r8")
        archiver = PageArchiver(archive_dir, config, MagicMock(), asset_archiver=double)
        assert archiver.asset_archiver is double

    def test_no_injection_no_asset_config_is_none(self, tmp_path):
        """When asset_archiver= not supplied and asset_config=None, asset_archiver is None."""
        archive_dir = str(tmp_path / "bookstack-r8-none")
        # Direct NodeArchiver construction: asset_config=None => no AssetArchiver built
        archiver = NodeArchiver(
            archive_dir=archive_dir,
            api_urls={"images": "https://x", "attachments": "https://y"},
            export_formats=["markdown"],
            http_client=MagicMock(),
            export_meta=False,
            asset_config=None,
        )
        assert archiver.asset_archiver is None

    def test_injected_double_overrides_real_construction(self, tmp_path):
        """When asset_archiver= injected and asset_config is truthy, the injected double wins."""
        double = MagicMock()
        archive_dir = str(tmp_path / "bookstack-r8-override")
        archiver = NodeArchiver(
            archive_dir=archive_dir,
            api_urls={"images": "https://x", "attachments": "https://y"},
            export_formats=["markdown"],
            http_client=MagicMock(),
            export_meta=False,
            asset_config=MagicMock(),  # truthy: without injection, would build real AssetArchiver
            asset_archiver=double,
        )
        assert archiver.asset_archiver is double


# ---------------------------------------------------------------------------
# 9. R5: page output path = page.file_path (no /name double-suffix)
# ---------------------------------------------------------------------------

class TestPageOutputPath:
    def test_page_content_written_to_file_path_not_file_path_slash_name(
            self, tmp_path, build_node):
        """Page export must be written to <base>/<page.file_path>.md, NOT <base>/<fp>/<name>.md."""
        config = _make_config(formats=["markdown"], export_images=False,
                              export_attachments=False, export_meta=False)
        archiver = PageArchiver(str(tmp_path / "bs"), config, MagicMock(),
                                asset_archiver=MagicMock())
        archiver.asset_archiver.get_asset_nodes.return_value = {}

        parent_node = build_node(id=1, name="my-book", slug="my-book")
        page = build_node(id=7, name="my-page", slug="my-page", parent=parent_node)
        # page.file_path = "my-book/my-page"

        written = {}
        archiver.write_data = written.__setitem__
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"data",
        ):
            archiver.archive({7: page})

        expected_key = f"{archiver.archive_base_path}/my-book/my-page.md"
        assert expected_key in written, f"Expected key {expected_key!r}, got {list(written)}"

    def test_page_meta_written_to_file_path(self, tmp_path, build_node):
        """Page meta must be <base>/<page.file_path>_meta.json."""
        config = _make_config(formats=["markdown"], export_images=False,
                              export_attachments=False, export_meta=True)
        archiver = PageArchiver(str(tmp_path / "bs"), config, MagicMock(),
                                asset_archiver=MagicMock())
        archiver.asset_archiver.get_asset_nodes.return_value = {}

        parent_node = build_node(id=1, name="my-book", slug="my-book")
        page = build_node(id=7, name="my-page", slug="my-page", parent=parent_node)

        written = {}
        archiver.write_data = written.__setitem__
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"data",
        ):
            archiver.archive({7: page})

        expected_meta_key = f"{archiver.archive_base_path}/my-book/my-page_meta.json"
        assert expected_meta_key in written, (
            f"Expected meta key {expected_meta_key!r}, got {list(written)}"
        )


# ---------------------------------------------------------------------------
# 10. R5: page assets written under parent.file_path
# ---------------------------------------------------------------------------

class TestPageAssetParentPath:
    def test_page_image_written_under_parent_file_path(self, tmp_path, build_node):
        """Image assets for a page must be stored under the parent book/chapter path."""
        config = _make_config(formats=["markdown"], export_images=True,
                              export_attachments=False, export_meta=False,
                              modify_links=True)
        archiver = PageArchiver(str(tmp_path / "bs"), config, MagicMock(),
                                asset_archiver=MagicMock())

        parent_node = build_node(id=1, name="my-book", slug="my-book")
        page = build_node(id=7, name="my-page", slug="my-page", parent=parent_node)

        img = MagicMock(id_=42, download_url="http://x/img", uploaded_to=7)
        img.get_relative_path = lambda page_name: f"images/{page_name}/img.png"

        archiver.asset_archiver.get_asset_nodes.side_effect = (
            lambda kind: {7: [img]} if kind == "images" else {}
        )
        archiver.asset_archiver.get_asset_bytes.return_value = b"PNGDATA"
        archiver.asset_archiver.update_asset_links.side_effect = lambda *a, **kw: a[2]

        written = {}
        archiver.write_data = written.__setitem__
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"data",
        ):
            archiver.archive({7: page})

        # asset must live under parent.file_path ("my-book"), NOT page.file_path ("my-book/my-page")
        expected_asset_key = f"{archiver.archive_base_path}/my-book/images/my-page/img.png"
        assert expected_asset_key in written, (
            f"Expected {expected_asset_key!r} in written; got {list(written)}"
        )


# ---------------------------------------------------------------------------
# 11. R5: modify_links=False still downloads assets but does NOT rewrite
# ---------------------------------------------------------------------------

class TestModifyLinksFalseStillDownloads:
    def test_assets_downloaded_rewrite_not_called(self, tmp_path, build_node):
        """When modify_links is False, assets are downloaded but update_asset_links
        is not called."""
        # export_images=True but modify_links=False → no rewrite
        config = _make_config(formats=["markdown"], export_images=True,
                              export_attachments=False, export_meta=False,
                              modify_links=False)
        archiver = PageArchiver(str(tmp_path / "bs"), config, MagicMock(),
                                asset_archiver=MagicMock())

        parent_node = build_node(id=1, name="my-book", slug="my-book")
        page = build_node(id=7, name="my-page", slug="my-page", parent=parent_node)

        img = MagicMock(id_=42, download_url="http://x/img", uploaded_to=7)
        img.get_relative_path = lambda page_name: f"images/{page_name}/img.png"

        archiver.asset_archiver.get_asset_nodes.side_effect = (
            lambda kind: {7: [img]} if kind == "images" else {}
        )
        archiver.asset_archiver.get_asset_bytes.return_value = b"PNGDATA"

        written = {}
        archiver.write_data = written.__setitem__
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"data",
        ):
            archiver.archive({7: page})

        # Asset should still be downloaded
        archiver.asset_archiver.get_asset_bytes.assert_called_once()
        # But rewrite must NOT be called
        archiver.asset_archiver.update_asset_links.assert_not_called()


# ---------------------------------------------------------------------------
# 12. R5: images-then-attachments rewrite order
# ---------------------------------------------------------------------------

class TestRewriteOrder:
    def test_images_rewritten_before_attachments(self, tmp_path, build_node):
        """asset_links rewrite must process images before attachments (same order as old code)."""
        config = _make_config(formats=["markdown"], export_images=True,
                              export_attachments=True, export_meta=False,
                              modify_links=True)
        archiver = PageArchiver(str(tmp_path / "bs"), config, MagicMock(),
                                asset_archiver=MagicMock())

        parent_node = build_node(id=1, name="my-book", slug="my-book")
        page = build_node(id=7, name="my-page", slug="my-page", parent=parent_node)

        img = MagicMock(id_=10, download_url="http://x/img", uploaded_to=7)
        img.get_relative_path = lambda page_name: f"images/{page_name}/img.png"
        att = MagicMock(id_=20, download_url="http://x/att", uploaded_to=7)
        att.get_relative_path = lambda page_name: f"attachments/{page_name}/file.pdf"

        archiver.asset_archiver.get_asset_nodes.side_effect = (
            lambda kind: {7: [img]} if kind == "images" else {7: [att]}
        )
        archiver.asset_archiver.get_asset_bytes.return_value = b"DATA"

        rewrite_order = []
        def _track_rewrite(asset_type, page_name, data, assets):
            rewrite_order.append(asset_type)
            return data
        archiver.asset_archiver.update_asset_links.side_effect = _track_rewrite

        written = {}
        archiver.write_data = written.__setitem__
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"data",
        ):
            archiver.archive({7: page})

        assert rewrite_order == ["images", "attachments"], (
            f"Expected images before attachments, got {rewrite_order}"
        )
