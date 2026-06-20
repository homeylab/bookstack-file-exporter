# pylint: disable=missing-class-docstring,missing-function-docstring
# pylint: disable=redefined-outer-name,protected-access
"""Unit tests for PageArchiver._modify_html dispatch and E2E HTML rewrite pipeline (Phase 4)."""
import logging
import re
from unittest.mock import MagicMock, patch

from requests.exceptions import HTTPError

from bookstack_file_exporter.archiver.asset_archiver import AssetArchiver, ImageNode
from bookstack_file_exporter.archiver.node_archiver import PageArchiver
from bookstack_file_exporter.common.util import HttpHelper

from tests.fixtures.mock_config import make_mock_config


# ---------------------------------------------------------------------------
# Phase 4 — PageArchiver dispatch
# ---------------------------------------------------------------------------

class TestPhase4PageArchiverDispatch:  # pylint: disable=too-few-public-methods
    """Tests for _check_links_modify, _modify_html, and archive dispatch.

    test scaffolding stub — PageArchiver tests intentionally cover a single entry point.
    """

    def _make_archiver(self, tmp_path, **config_kwargs):
        config = make_mock_config(**config_kwargs)
        archive_dir = str(tmp_path / "bookstack-test")
        return PageArchiver(archive_dir, config, MagicMock(), asset_archiver=MagicMock())

    def test_check_links_modify_true_for_html_format(self, tmp_path):
        archiver = self._make_archiver(
            tmp_path,
            formats=["html"],
            modify_links=True,
            export_images=True,
        )
        assert archiver.modify_links is True

    def test_check_links_modify_true_for_markdown_format(self, tmp_path):
        archiver = self._make_archiver(
            tmp_path,
            formats=["markdown"],
            modify_links=True,
            export_images=True,
        )
        assert archiver.modify_links is True

    def test_check_links_modify_true_for_both_formats(self, tmp_path):
        archiver = self._make_archiver(
            tmp_path,
            formats=["markdown", "html"],
            modify_links=True,
            export_images=True,
        )
        assert archiver.modify_links is True

    def test_check_links_modify_false_when_no_assets(self, tmp_path):
        archiver = self._make_archiver(
            tmp_path,
            formats=["html"],
            modify_links=True,
            export_images=False,
            export_attachments=False,
        )
        assert archiver.modify_links is False

    def test_check_links_modify_false_when_format_not_rewritable(self, tmp_path):
        archiver = self._make_archiver(
            tmp_path,
            formats=["pdf"],
            modify_links=True,
            export_images=True,
        )
        assert archiver.modify_links is False

    def test_warning_when_modify_links_true_but_no_rewritable_format(
        self, tmp_path, caplog
    ):
        logger_name = "bookstack_file_exporter.archiver.node_archiver"
        with caplog.at_level(logging.WARNING, logger=logger_name):
            self._make_archiver(
                tmp_path,
                formats=["pdf"],
                modify_links=True,
                export_images=True,
            )
        warning_msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("MODIFY_LINKS" in m or "rewritable" in m.lower() for m in warning_msgs)

    def test_archive_dispatches_html_branch(
        self, tmp_path, build_node
    ):
        """archive should invoke html rewrite (update_asset_links_html) when format='html' and modify_links=True."""
        mock_asset = MagicMock()
        config = make_mock_config(
            formats=["html"],
            modify_links=True,
            export_images=True,
        )
        archive_dir = str(tmp_path / "bookstack-test")
        archiver = PageArchiver(archive_dir, config, MagicMock(), asset_archiver=mock_asset)

        # Set up mock asset nodes
        mock_image_node = MagicMock()
        mock_image_node.id_ = 1
        mock_asset.get_asset_nodes.side_effect = lambda asset_type: (
            {5: [mock_image_node]} if asset_type == "images" else {}
        )
        mock_asset.get_asset_bytes.return_value = b"img_bytes"
        mock_asset.update_asset_links_html.return_value = b"<html>rewritten</html>"

        parent_node = build_node(id=1, name="my-book", slug="my-book")
        page = build_node(id=5, name="test-page", slug="test-page", parent=parent_node)

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"<html><body>content</body></html>",
        ), patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ):
            archiver.archive({5: page})

        mock_asset.update_asset_links_html.assert_called_once()

    def test_modify_html_short_circuits_when_modify_links_false(
        self, tmp_path, build_node
    ):
        """When modify_links is False, archive must not call update_asset_links_html."""
        mock_asset = MagicMock()
        config = make_mock_config(formats=["html"], modify_links=False,
                                  export_images=True)
        archive_dir = str(tmp_path / "bookstack-test")
        archiver = PageArchiver(archive_dir, config, MagicMock(), asset_archiver=mock_asset)

        mock_image_node = MagicMock()
        mock_image_node.id_ = 1
        mock_asset.get_asset_nodes.side_effect = lambda asset_type: (
            {5: [mock_image_node]} if asset_type == "images" else {}
        )
        mock_asset.get_asset_bytes.return_value = b"img_bytes"

        parent_node = build_node(id=1, name="my-book", slug="my-book")
        page = build_node(id=5, name="test-page", slug="test-page", parent=parent_node)

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"<html><body>test</body></html>",
        ), patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ):
            archiver.archive({5: page})

        # modify_links=False: html rewrite must not be invoked
        mock_asset.update_asset_links_html.assert_not_called()

    def test_failed_assets_filtered_from_html_rewrite(
        self, tmp_path, build_node
    ):
        """Failed assets should be excluded from both md and html rewrite paths."""
        mock_asset = MagicMock()
        config = make_mock_config(
            formats=["html"],
            modify_links=True,
            export_images=True,
        )
        archive_dir = str(tmp_path / "bookstack-test")
        archiver = PageArchiver(archive_dir, config, MagicMock(), asset_archiver=mock_asset)

        mock_image_node = MagicMock()
        mock_image_node.id_ = 42
        mock_asset.get_asset_nodes.side_effect = lambda asset_type: (
            {5: [mock_image_node]} if asset_type == "images" else {}
        )
        # Simulate asset download failure
        mock_asset.get_asset_bytes.side_effect = HTTPError("404")

        parent_node = build_node(id=1, name="my-book", slug="my-book")
        page = build_node(id=5, name="test-page", slug="test-page", parent=parent_node)

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"<html><body>content</body></html>",
        ), patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ):
            archiver.archive({5: page})

        # When all assets fail, _rewrite_page_data short-circuits on empty nodes list
        # and never calls update_asset_links_html.
        calls = mock_asset.update_asset_links_html.call_args_list
        assert calls == [], (
            f"expected no html rewrite calls when all assets fail, got {len(calls)}"
        )

    def test_partially_failed_assets_excluded_from_html_rewrite(  # pylint: disable=too-many-locals
        self, tmp_path, build_node
    ):
        """When some assets fail, only successful nodes are passed to update_asset_links_html."""
        mock_asset = MagicMock()
        config = make_mock_config(
            formats=["html"],
            modify_links=True,
            export_images=True,
        )
        archive_dir = str(tmp_path / "bookstack-test")
        archiver = PageArchiver(archive_dir, config, MagicMock(), asset_archiver=mock_asset)

        good_node = MagicMock(spec=ImageNode)
        good_node.id_ = 10
        good_node.download_url = "https://wiki.example.com/uploads/images/10/good.png"
        bad_node = MagicMock(spec=ImageNode)
        bad_node.id_ = 99
        bad_node.download_url = "https://wiki.example.com/uploads/images/99/bad.png"

        mock_asset.get_asset_nodes.side_effect = lambda asset_type: (
            {5: [good_node, bad_node]} if asset_type == "images" else {}
        )

        def _fail_bad_node(_asset_type, url):
            if "99" in url:
                raise HTTPError("404")
            return b"img_bytes"

        mock_asset.get_asset_bytes.side_effect = _fail_bad_node

        parent_node = build_node(id=1, name="my-book", slug="my-book")
        page = build_node(id=5, name="test-page", slug="test-page", parent=parent_node)

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"<html><body>content</body></html>",
        ), patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ):
            archiver.archive({5: page})

        calls = mock_asset.update_asset_links_html.call_args_list
        assert len(calls) >= 1, (
            "update_asset_links_html should be called when some assets succeed"
        )
        for c in calls:
            nodes_arg = c.args[3] if len(c.args) > 3 else c.kwargs.get("asset_nodes", [])
            assert bad_node not in nodes_arg, "failed node must not be passed to html rewrite"
            assert good_node in nodes_arg, "successful node must be passed to html rewrite"


# ---------------------------------------------------------------------------
# E2E — full pipeline integration
# ---------------------------------------------------------------------------

class TestE2eHtmlRewrite:  # pylint: disable=too-few-public-methods
    """Full pipeline: PageArchiver → AssetArchiver → bytes.replace, HTTP mocked only.

    test scaffolding stub — this class covers the single end-to-end pipeline scenario.

    Verifies that archive rewrites image URLs in HTML exports
    to local relative paths end-to-end without mocking internal components.
    Requires Task 1 fix (skip redundant API call for ImageNode in HTML mode).

    PAGE_HTML uses a base64 data: URI for img src — matching how real
    BookStack page exports embed images. This is fixture realism only.

    Task 1's optimization is proven by the http_get_request.call_count
    assertion below, NOT by the base64 src. With Task 1: 1 HTTP call
    (asset bytes only). Without Task 1: 2 HTTP calls (asset bytes +
    redundant get_asset_data). The other assertions (anchor rewritten,
    IMAGE_URL absent) pass in both states because 'content' in MagicMock()
    is False, so _get_html_url_strs returns [] and url_map falls back to
    {page_url: local_path} either way.
    """

    IMAGE_ID = 42
    PAGE_ID = 5
    IMAGE_URL = "https://wiki.example.com/uploads/images/gallery/2024-01/photo.png"
    PAGE_HTML = (
        '<html><body>'
        f'<a href="{IMAGE_URL}">'
        '<img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==" alt="photo">'
        '</a></body></html>'
    )

    def _make_config(self):
        config = make_mock_config(
            formats=["html"],
            export_images=True,
            export_attachments=False,
            export_meta=False,
            modify_links=True,
        )
        # Override urls to use the E2E-specific wiki URL
        config.urls = {
            "pages": "https://wiki.example.com/api/pages",
            "images": "https://wiki.example.com/api/image-gallery",
            "attachments": "https://wiki.example.com/api/attachments",
        }
        return config

    def test_html_image_url_rewritten_to_local_path(self, tmp_path, build_node):
        """Full pipeline rewrites remote image URL in HTML export to local relative path.
        Phase 2: the anchor-wrapped base64 img src is also slimmed to the local path.
        Both href and src point at images/test-page/photo.png; the data: blob is gone.
        """
        config = self._make_config()
        archive_dir = str(tmp_path / "bookstack-test")

        http_client = MagicMock(spec=HttpHelper)
        http_client.http_get_all.return_value = [{
            "id": self.IMAGE_ID,
            "uploaded_to": self.PAGE_ID,
            "url": self.IMAGE_URL,
        }]
        http_client.http_get_request.return_value.content = b"fake_png_bytes"

        written: dict = {}

        def capture_write(_base_tar_dir: str, file_path: str, data: bytes) -> None:
            written[file_path] = data

        parent = build_node(id=1, name="my-book", slug="my-book")
        page = build_node(
            id=self.PAGE_ID, name="test-page", slug="test-page", parent=parent
        )

        archiver = PageArchiver(archive_dir, config, http_client)

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=self.PAGE_HTML.encode(),
        ), patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar",
            side_effect=capture_write,
        ):
            archiver.archive({self.PAGE_ID: page})

        html_files = {k: v for k, v in written.items() if k.endswith(".html")}
        assert len(html_files) == 1, (
            f"expected exactly one HTML file; got {len(html_files)}: {list(html_files)}"
        )

        html_bytes = next(iter(html_files.values()))

        assert re.search(
            rb'<a href="images/test-page/photo\.png">',
            html_bytes,
        ), "anchor href must be rewritten to local relative path"

        assert self.IMAGE_URL.encode() not in html_bytes, (
            "remote URL must be fully removed from HTML output"
        )

        # Phase 2: wrapped base64 src is slimmed to the same local file as the anchor href.
        local_path = b'images/test-page/photo.png'
        assert re.search(rb'src="images/test-page/photo\.png"', html_bytes), (
            f"wrapped base64 src must be rewritten to local path; got: {html_bytes!r}"
        )
        assert b'data:image/png;base64,' not in html_bytes, (
            "base64 blob must be replaced by local path (Phase 2)"
        )
        _ = local_path  # referenced above via re.search for clarity

        assert http_client.http_get_request.call_count == 1, (
            f"expected 1 HTTP call (asset bytes only); "
            f"got {http_client.http_get_request.call_count} — "
            f"Task 1 short-circuit not firing"
        )


# ---------------------------------------------------------------------------
# Remote-scaled img src — three-branch resolver (Step 1 / Phase 1)
# ---------------------------------------------------------------------------

class TestRemoteScaledImgSrc:
    """update_asset_links_html must rewrite a remote scaled <img src> to local path.

    BookStack's most common html export shape wraps images in a click-to-zoom anchor:
        <a href=".../gallery/2023-07/foo.png">
          <img src=".../gallery/2023-07/scaled-1680-/foo.png" alt="foo">
        </a>
    url_map (html mode) keys on the canonical page_url (.../foo.png, no scaled segment).
    Branch 3 of the resolver strips /scaled-\\d+-/ from src and retries the lookup,
    localizing the displayed image as well as the click-through link.
    """

    CANONICAL_URL = (
        "https://wiki.example.com/uploads/images/gallery/2023-07/foo.png"
    )
    SCALED_URL = (
        "https://wiki.example.com/uploads/images/gallery/2023-07/scaled-1680-/foo.png"
    )
    PAGE_HTML = (
        '<html><body>'
        f'<a href="{CANONICAL_URL}">'
        f'<img src="{SCALED_URL}" alt="foo">'
        '</a></body></html>'
    )

    def test_remote_scaled_src_and_href_rewritten_to_local(self):
        """Both scaled img src and canonical anchor href are rewritten to images/test-page/foo.png."""
        http_client = MagicMock(spec=HttpHelper)
        archiver = AssetArchiver(
            {
                "images": "https://wiki.example.com/api/image-gallery",
                "attachments": "https://wiki.example.com/api/attachments",
            },
            http_client,
        )
        node = ImageNode({"id": 1, "uploaded_to": 5, "url": self.CANONICAL_URL})
        result = archiver.update_asset_links_html(
            "images", "test-page", self.PAGE_HTML.encode(), [node]
        )

        local_path = b"images/test-page/foo.png"
        assert local_path in result, (
            f"expected local path {local_path!r} in output; got: {result!r}"
        )
        assert self.SCALED_URL.encode() not in result, (
            f"scaled img src must be rewritten; still present in: {result!r}"
        )
        assert self.CANONICAL_URL.encode() not in result, (
            f"canonical anchor href must be rewritten; still present in: {result!r}"
        )


# ---------------------------------------------------------------------------
# Base64 img src slimming — Phase 2 (Option 1, reuse-only)
# ---------------------------------------------------------------------------

class TestBase64ImgSrcSlimming:
    """update_asset_links_html must slim wrapped base64 img src by reusing the anchor's local file.

    BookStack's click-to-zoom shape for recently-added images:
        <a href=".../gallery/2026-06/bar.png">
          <img src="data:image/png;base64,..." alt="bar">
        </a>
    The anchor href is already downloaded (url_map has it). The inline data: blob is replaced
    by the same local path. Bare base64 (no anchor, or anchor href not in url_map) is left inline.
    """

    CANONICAL_URL = (
        "https://wiki.example.com/uploads/images/gallery/2026-06/bar.png"
    )
    BASE64_BLOB = (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
        "AAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )

    def _make_archiver(self):
        http_client = MagicMock(spec=HttpHelper)
        return AssetArchiver(
            {
                "images": "https://wiki.example.com/api/image-gallery",
                "attachments": "https://wiki.example.com/api/attachments",
            },
            http_client,
        )

    def test_wrapped_base64_src_and_href_rewritten_to_local(self):
        """Wrapped base64 img (<a href=canonical><img src=data:...>): src rewritten to local path,
        data: blob gone, href also localized — both point at one shared local file."""
        archiver = self._make_archiver()
        node = ImageNode({"id": 2, "uploaded_to": 5, "url": self.CANONICAL_URL})
        page_html = (
            '<html><body>'
            f'<a href="{self.CANONICAL_URL}">'
            f'<img src="{self.BASE64_BLOB}" alt="bar">'
            '</a></body></html>'
        ).encode()

        result = archiver.update_asset_links_html(
            "images", "test-page", page_html, [node]
        )

        local_path = b"images/test-page/bar.png"
        assert local_path in result, (
            f"expected local path {local_path!r} in output; got: {result!r}"
        )
        assert self.BASE64_BLOB.encode() not in result, (
            f"data: blob must be replaced; still present in: {result!r}"
        )
        assert self.CANONICAL_URL.encode() not in result, (
            f"canonical anchor href must be localized; still present in: {result!r}"
        )

    def test_bare_base64_src_left_inline(self):
        """Bare base64 img (no anchor): src must be left unchanged (Option-1 boundary)."""
        archiver = self._make_archiver()
        node = ImageNode({"id": 2, "uploaded_to": 5, "url": self.CANONICAL_URL})
        page_html = (
            '<html><body>'
            f'<img src="{self.BASE64_BLOB}" alt="bar">'
            '</body></html>'
        ).encode()

        result = archiver.update_asset_links_html(
            "images", "test-page", page_html, [node]
        )

        assert self.BASE64_BLOB.encode() in result, (
            f"bare base64 must remain inline (Option-1 boundary); missing from: {result!r}"
        )
