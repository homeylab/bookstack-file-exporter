# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name,unused-argument,protected-access
"""Happy-path unit tests for PageArchiver."""
from typing import Dict
from unittest.mock import MagicMock, patch

import pytest

from bookstack_file_exporter.archiver.page_archiver import PageArchiver
from bookstack_file_exporter.exporter.node import Node


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

from tests.fixtures.mock_config import make_mock_config as _make_config


def _make_page_node(build_node, page_id: int, slug: str, parent: Node) -> Node:
    """Construct a leaf page Node with the given parent."""
    return build_node(id=page_id, name=slug, slug=slug, parent=parent)


@pytest.fixture
def page_archiver(tmp_path, monkeypatch):
    """Construct a PageArchiver with all external collaborators mocked."""
    monkeypatch.setattr(
        "bookstack_file_exporter.archiver.page_archiver.AssetArchiver",
        MagicMock(),
    )
    config = _make_config()
    http_client = MagicMock()
    archive_dir = str(tmp_path / "bookstack-20260514")
    return PageArchiver(archive_dir, config, http_client)


# ---------------------------------------------------------------------------
# 1. Construction
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_archive_file_ends_with_tgz(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "bookstack_file_exporter.archiver.page_archiver.AssetArchiver",
            MagicMock(),
        )
        archive_dir = str(tmp_path / "bookstack-20260514")
        archiver = PageArchiver(archive_dir, _make_config(), MagicMock())
        assert archiver.archive_file == f"{archive_dir}.tgz"

    def test_tar_file_ends_with_tar(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "bookstack_file_exporter.archiver.page_archiver.AssetArchiver",
            MagicMock(),
        )
        archive_dir = str(tmp_path / "bookstack-20260514")
        archiver = PageArchiver(archive_dir, _make_config(), MagicMock())
        assert archiver.tar_file == f"{archive_dir}.tar"

    def test_archive_base_path_is_last_segment(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "bookstack_file_exporter.archiver.page_archiver.AssetArchiver",
            MagicMock(),
        )
        archive_dir = str(tmp_path / "bookstack-20260514")
        archiver = PageArchiver(archive_dir, _make_config(), MagicMock())
        assert archiver.archive_base_path == "bookstack-20260514"

    def test_http_client_stored(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "bookstack_file_exporter.archiver.page_archiver.AssetArchiver",
            MagicMock(),
        )
        http_client = MagicMock()
        archive_dir = str(tmp_path / "bookstack-20260514")
        archiver = PageArchiver(archive_dir, _make_config(), http_client)
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
            "bookstack_file_exporter.archiver.page_archiver.archiver_util.get_byte_response"
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
            "bookstack_file_exporter.archiver.page_archiver.archiver_util.create_gzip"
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
            "bookstack_file_exporter.archiver.page_archiver.archiver_util.write_tar"
        ) as mock_write_tar:
            page_archiver.write_data("some/path/file.md", b"content")
            mock_write_tar.assert_called_once_with(
                page_archiver.tar_file, "some/path/file.md", b"content"
            )


# ---------------------------------------------------------------------------
# 6. archive_pages iterates every page node
# ---------------------------------------------------------------------------

class TestArchivePages:
    def test_each_page_node_written_once_per_format(self, tmp_path, monkeypatch, build_node):
        """archive_pages should write one file per page per format."""
        monkeypatch.setattr(
            "bookstack_file_exporter.archiver.page_archiver.AssetArchiver",
            MagicMock(),
        )
        config = _make_config(formats=["markdown"], export_images=False,
                               export_attachments=False, export_meta=False)
        http_client = MagicMock()
        archive_dir = str(tmp_path / "bookstack-test")
        archiver = PageArchiver(archive_dir, config, http_client)

        # Make asset_archiver return empty dicts (no images / attachments)
        archiver.asset_archiver.get_asset_nodes.return_value = {}

        # Build a simple parent node and two page nodes
        parent_node = build_node(id=1, name="my-book", slug="my-book")
        page1 = build_node(id=10, name="page-one", slug="page-one", parent=parent_node)
        page2 = build_node(id=11, name="page-two", slug="page-two", parent=parent_node)

        page_nodes: Dict[int, Node] = {10: page1, 11: page2}

        with patch(
            "bookstack_file_exporter.archiver.page_archiver.archiver_util.get_byte_response",
            return_value=b"page bytes",
        ), patch(
            "bookstack_file_exporter.archiver.page_archiver.archiver_util.write_tar"
        ) as mock_write_tar:
            archiver.archive_pages(page_nodes)

        # 2 pages × 1 format = 2 write_tar calls
        assert mock_write_tar.call_count == 2

    def test_archive_pages_respects_multiple_formats(self, tmp_path, monkeypatch, build_node):
        """archive_pages should call write_tar once per page per format."""
        monkeypatch.setattr(
            "bookstack_file_exporter.archiver.page_archiver.AssetArchiver",
            MagicMock(),
        )
        config = _make_config(formats=["markdown", "html"], export_images=False,
                               export_attachments=False, export_meta=False)
        http_client = MagicMock()
        archive_dir = str(tmp_path / "bookstack-multi")
        archiver = PageArchiver(archive_dir, config, http_client)
        archiver.asset_archiver.get_asset_nodes.return_value = {}

        parent_node = build_node(id=1, name="a-book", slug="a-book")
        page1 = build_node(id=20, name="intro", slug="intro", parent=parent_node)
        page_nodes = {20: page1}

        with patch(
            "bookstack_file_exporter.archiver.page_archiver.archiver_util.get_byte_response",
            return_value=b"content",
        ), patch(
            "bookstack_file_exporter.archiver.page_archiver.archiver_util.write_tar"
        ) as mock_write_tar:
            archiver.archive_pages(page_nodes)

        # 1 page × 2 formats = 2 write_tar calls
        assert mock_write_tar.call_count == 2
