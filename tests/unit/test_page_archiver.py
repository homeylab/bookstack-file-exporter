# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name,unused-argument,protected-access
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
# 1. Construction
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_archive_file_ends_with_tgz(self, tmp_path):
        archive_dir = str(tmp_path / "bookstack-20260514")
        archiver = PageArchiver(archive_dir, _make_config(), MagicMock(), asset_archiver=MagicMock())
        assert archiver.archive_file == f"{archive_dir}.tgz"

    def test_tar_file_ends_with_tar(self, tmp_path):
        archive_dir = str(tmp_path / "bookstack-20260514")
        archiver = PageArchiver(archive_dir, _make_config(), MagicMock(), asset_archiver=MagicMock())
        assert archiver.tar_file == f"{archive_dir}.tar"

    def test_archive_base_path_is_last_segment(self, tmp_path):
        archive_dir = str(tmp_path / "bookstack-20260514")
        archiver = PageArchiver(archive_dir, _make_config(), MagicMock(), asset_archiver=MagicMock())
        assert archiver.archive_base_path == "bookstack-20260514"

    def test_http_client_stored(self, tmp_path):
        http_client = MagicMock()
        archive_dir = str(tmp_path / "bookstack-20260514")
        archiver = PageArchiver(archive_dir, _make_config(), http_client, asset_archiver=MagicMock())
        assert archiver.http_client is http_client


# ---------------------------------------------------------------------------
# 2. Export URL formation (_get_page_data)
# ---------------------------------------------------------------------------

class TestGetPageData:  # pylint: disable=too-few-public-methods  # test scaffolding stub
    @pytest.mark.parametrize("export_format", ["markdown", "html", "pdf", "plaintext", "zip"])
    def test_url_contains_export_api_path(self, page_archiver, export_format):
        """_get_page_data should call http_client with the correct export URL."""
        page_archiver.http_client.http_get_request.return_value.content = b"data"
        # patch archiver_util.get_byte_response to capture the url argument
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response"
        ) as mock_get_bytes:
            mock_get_bytes.return_value = b"page content"
            page_archiver._get_page_data(42, export_format)
            called_url = mock_get_bytes.call_args.kwargs["url"]
        expected = (
            f"https://wiki.test.example/api/pages/42/export/{export_format}"
        )
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
    def test_create_gzip_called_with_tar_and_archive_file(self, page_archiver):
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.create_gzip"
        ) as mock_create_gzip:
            page_archiver.gzip_archive()
            mock_create_gzip.assert_called_once_with(
                page_archiver.tar_file, page_archiver.archive_file
            )


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
        """When asset_archiver= is supplied, NodeArchiver stores it without constructing a real one."""
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
