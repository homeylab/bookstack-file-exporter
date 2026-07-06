# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name,unused-argument,protected-access,too-few-public-methods,duplicate-code
"""Asset download, link-rewrite, and asset-listing tests for PageArchiver."""
from typing import Dict
from unittest.mock import MagicMock, patch

from requests.exceptions import HTTPError

from bookstack_file_exporter.archiver.asset_archiver import AssetDecodeError
from bookstack_file_exporter.archiver.node_archiver import PageArchiver
from bookstack_file_exporter.exporter.node import Node
from tests.fixtures.mock_config import make_mock_config as _make_config


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
            "bookstack_file_exporter.archiver.util.TarStream.write"
        ) as mock_stream_write:
            archiver.archive(page_nodes)

        # 2 pages × 1 format = 2 stream write calls
        assert mock_stream_write.call_count == 2

    def test_archive_respects_multiple_formats(self, tmp_path, build_node):
        """archive should write to the stream once per page per format."""
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
            "bookstack_file_exporter.archiver.util.TarStream.write"
        ) as mock_stream_write:
            archiver.archive(page_nodes)

        # 1 page × 2 formats = 2 stream write calls
        assert mock_stream_write.call_count == 2

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
            "bookstack_file_exporter.archiver.util.TarStream.write"
        ) as mock_stream_write:
            archiver.archive({30: good, 3: forbidden})  # must not raise

        # forbidden page skipped, good page written → 1 write
        assert mock_stream_write.call_count == 1


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


# ---------------------------------------------------------------------------
# 20. A1: asset-listing failure degrades to partial instead of aborting the run
# ---------------------------------------------------------------------------

class TestAssetListingFailureDegrades:
    """A transient failure on the image/attachment LISTING endpoint must not
    hard-fail the whole run; it should log, record a sentinel (-> PARTIAL),
    and return an empty map so nodes still export without asset rewriting."""

    def test_image_listing_failure_degrades_not_aborts(self, tmp_path):
        config = _make_config(export_images=True)
        archiver = PageArchiver(str(tmp_path / "bs-img-listing"), config, MagicMock(),
                                asset_archiver=MagicMock())
        archiver.asset_archiver.get_asset_nodes.side_effect = HTTPError("500 boom")

        result = archiver._get_image_meta()

        assert result == {}
        assert archiver.failed_asset_downloads  # sentinel recorded -> run becomes PARTIAL

    def test_attachment_listing_failure_degrades_not_aborts(self, tmp_path):
        config = _make_config(export_attachments=True)
        archiver = PageArchiver(str(tmp_path / "bs-att-listing"), config, MagicMock(),
                                asset_archiver=MagicMock())
        archiver.asset_archiver.get_asset_nodes.side_effect = HTTPError("500 boom")

        result = archiver._get_attachment_meta()

        assert result == {}
        assert archiver.failed_asset_downloads  # sentinel recorded -> run becomes PARTIAL


# ---------------------------------------------------------------------------
# Task 14: malformed attachment payload -> AssetDecodeError skips the asset
# ---------------------------------------------------------------------------

def test_asset_decode_failure_skips_asset_and_keeps_page(tmp_path, build_node):
    """A malformed attachment payload is recorded like a failed download; the
    page itself still exports and the run continues (-> PARTIAL, not abort)."""
    config = _make_config(formats=["markdown"], export_images=False,
                          export_attachments=True, export_meta=False)
    mock_asset_archiver = MagicMock()
    archiver = PageArchiver(str(tmp_path / "bookstack-decode"), config, MagicMock(),
                            asset_archiver=mock_asset_archiver)

    parent_node = build_node(id=1, name="a-book", slug="a-book")
    page = build_node(id=40, name="gallery", slug="gallery", parent=parent_node)

    bad = MagicMock()
    bad.id_ = 100
    bad.get_relative_path.return_value = "attachments/gallery/broken.dat"
    mock_asset_archiver.get_asset_nodes.return_value = {40: [bad]}
    mock_asset_archiver.get_asset_bytes.side_effect = AssetDecodeError("bad payload")

    with patch(
        "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
        return_value=b"page bytes",
    ), patch("bookstack_file_exporter.archiver.util.TarStream.write") as mock_write:
        archiver.archive({40: page})  # must not raise

    assert archiver.failed_asset_downloads == ["attachments/gallery/broken.dat"]
    assert not archiver.failed_node_exports
    assert mock_write.call_count == 1  # the page export itself still landed


def test_image_validation_failure_skips_asset_and_keeps_page(tmp_path, build_node):
    """A _validate_image_response failure (issue #145 login-HTML detection)
    raises AssetDecodeError, which _archive_node_assets' asset-level
    `except (HTTPError, RetryError, AssetDecodeError)` catches exactly like a
    failed download: the image is recorded as failed, but the page itself
    still exports (-> PARTIAL, not abort)."""
    config = _make_config(formats=["markdown"], export_images=True,
                          export_attachments=False, export_meta=False)
    mock_asset_archiver = MagicMock()
    archiver = PageArchiver(str(tmp_path / "bookstack-image-decode"), config, MagicMock(),
                            asset_archiver=mock_asset_archiver)

    parent_node = build_node(id=1, name="a-book", slug="a-book")
    page = build_node(id=41, name="gallery", slug="gallery", parent=parent_node)

    bad = MagicMock()
    bad.id_ = 200
    bad.get_relative_path.return_value = "images/gallery/broken.png"
    mock_asset_archiver.get_asset_nodes.return_value = {41: [bad]}
    mock_asset_archiver.get_asset_bytes.side_effect = AssetDecodeError(
        "image request was redirected to a login page, not image bytes")

    with patch(
        "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
        return_value=b"page bytes",
    ), patch("bookstack_file_exporter.archiver.util.TarStream.write") as mock_write:
        archiver.archive({41: page})  # must not raise

    assert archiver.failed_asset_downloads == ["images/gallery/broken.png"]
    assert not archiver.failed_node_exports
    assert mock_write.call_count == 1  # the page export itself still landed
