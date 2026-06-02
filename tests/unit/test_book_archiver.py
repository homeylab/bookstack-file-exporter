# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name
# pylint: disable=protected-access,too-few-public-methods,duplicate-code
"""Unit tests for BookArchiver."""
from unittest.mock import MagicMock, patch

import pytest
from requests.exceptions import HTTPError

from bookstack_file_exporter.archiver.node_archiver import BookArchiver
from bookstack_file_exporter.exporter.node import Node


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_BOOKS_URL = "https://wiki.test.example/api/books"
_API_URLS = {
    "books": _BOOKS_URL,
    "chapters": "https://wiki.test.example/api/chapters",
    "pages": "https://wiki.test.example/api/pages",
}


def _make_book_archiver(tmp_path, formats=None, export_meta=False):
    archive_dir = str(tmp_path / "bookstack-20260531")
    http_client = MagicMock()
    return BookArchiver(
        archive_dir=archive_dir,
        api_urls=_API_URLS,
        export_formats=formats or ["pdf"],
        http_client=http_client,
        export_meta=export_meta,
    )


def _make_book_node(book_id: int, slug: str, has_contents: bool = True) -> Node:
    """Build a book Node directly from a fixture-style dict."""
    contents = [{"id": 100, "type": "page", "slug": "page-1"}] if has_contents else []
    meta = {
        "id": book_id,
        "name": slug,
        "slug": slug,
        "contents": contents,
    }
    return Node(meta, parent=None)


# ---------------------------------------------------------------------------
# 1. Construction
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_archive_file_ends_with_tgz(self, tmp_path):
        archiver = _make_book_archiver(tmp_path)
        assert archiver.archive_file.endswith(".tgz")

    def test_tar_file_ends_with_tar(self, tmp_path):
        archiver = _make_book_archiver(tmp_path)
        assert archiver.tar_file.endswith(".tar")

    def test_archive_base_path_is_last_segment(self, tmp_path):
        archiver = _make_book_archiver(tmp_path)
        assert archiver.archive_base_path == "bookstack-20260531"

    def test_export_meta_stored(self, tmp_path):
        archiver = _make_book_archiver(tmp_path, export_meta=True)
        assert archiver.export_meta is True

    def test_export_meta_default_false(self, tmp_path):
        archiver = _make_book_archiver(tmp_path, export_meta=False)
        assert archiver.export_meta is False


# ---------------------------------------------------------------------------
# 2. N books × N formats → N*M write_tar calls
# ---------------------------------------------------------------------------

class TestArchiveMultipleBooksAndFormats:
    @pytest.mark.parametrize("n_books,formats,expected_writes", [
        (1, ["pdf"], 1),
        (2, ["pdf"], 2),
        (2, ["pdf", "html"], 4),
        (3, ["markdown", "html", "pdf"], 9),
    ])
    def test_write_tar_call_count(self, tmp_path, n_books, formats, expected_writes):
        archiver = _make_book_archiver(tmp_path, formats=formats)
        book_nodes = {
            i: _make_book_node(i, f"book-{i}") for i in range(1, n_books + 1)
        }
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"book content",
        ), patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ) as mock_write_tar:
            archiver.archive(book_nodes)
        assert mock_write_tar.call_count == expected_writes


# ---------------------------------------------------------------------------
# 3. Export URL targets /api/books/{id}/export/{fmt}
# ---------------------------------------------------------------------------

class TestExportUrl:
    @pytest.mark.parametrize("export_format", ["pdf", "html", "markdown", "plaintext", "zip"])
    def test_url_contains_books_export_path(self, tmp_path, export_format):
        archiver = _make_book_archiver(tmp_path, formats=[export_format])
        book_node = _make_book_node(42, "my-book")

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"data",
        ) as mock_get_bytes, patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ):
            archiver.archive({42: book_node})

        called_url = mock_get_bytes.call_args.kwargs["url"]
        expected = f"{_BOOKS_URL}/42/export/{export_format}"
        assert called_url == expected


# ---------------------------------------------------------------------------
# 4. One format raises HTTPError → skipped, others written
# ---------------------------------------------------------------------------

class TestHTTPErrorHandling:
    def test_one_format_fails_others_written(self, tmp_path):
        """If pdf raises HTTPError, html should still be written."""
        archiver = _make_book_archiver(tmp_path, formats=["pdf", "html"])
        book_node = _make_book_node(10, "test-book")

        def side_effect(url, http_client):  # pylint: disable=unused-argument
            if "pdf" in url:
                raise HTTPError("pdf failed")
            return b"html content"

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            side_effect=side_effect,
        ), patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ) as mock_write_tar:
            archiver.archive({10: book_node})

        # pdf skipped, html written — 1 write
        assert mock_write_tar.call_count == 1

    def test_all_formats_fail_but_meta_still_written(self, tmp_path):
        """All format fetches fail, but export_meta still writes a meta file to the tar."""
        archiver = _make_book_archiver(tmp_path, formats=["pdf"], export_meta=True)
        book_node = _make_book_node(10, "test-book")

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            side_effect=HTTPError("pdf failed"),
        ), patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ) as mock_write_tar:
            archiver.archive({10: book_node})

        # pdf skipped, but meta still written → 1 write
        assert mock_write_tar.call_count == 1


# ---------------------------------------------------------------------------
# 5. export_meta on → +1 write per book (meta)
# ---------------------------------------------------------------------------

class TestExportMeta:
    def test_meta_written_per_book_when_enabled(self, tmp_path):
        archiver = _make_book_archiver(tmp_path, formats=["pdf"], export_meta=True)
        book_nodes = {
            1: _make_book_node(1, "book-one"),
            2: _make_book_node(2, "book-two"),
        }
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"book data",
        ), patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ) as mock_write_tar:
            archiver.archive(book_nodes)
        # 2 books × 1 format + 2 meta files = 4 writes
        assert mock_write_tar.call_count == 4

    def test_meta_not_written_when_disabled(self, tmp_path):
        archiver = _make_book_archiver(tmp_path, formats=["pdf"], export_meta=False)
        book_nodes = {1: _make_book_node(1, "book-one")}
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"book data",
        ), patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ) as mock_write_tar:
            archiver.archive(book_nodes)
        # 1 book × 1 format only
        assert mock_write_tar.call_count == 1


# ---------------------------------------------------------------------------
# 6. Empty book (no children) → no fetch, no write
# ---------------------------------------------------------------------------

class TestEmptyBook:
    def test_empty_book_skipped(self, tmp_path):
        archiver = _make_book_archiver(tmp_path, formats=["pdf"])
        empty_book = _make_book_node(99, "empty-book", has_contents=False)
        non_empty_book = _make_book_node(100, "full-book")

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"data",
        ) as mock_get_bytes, patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ) as mock_write_tar:
            archiver.archive({99: empty_book, 100: non_empty_book})

        # empty book: no fetch, no write; full book: 1 fetch, 1 write
        assert mock_get_bytes.call_count == 1
        assert mock_write_tar.call_count == 1

    def test_all_empty_books_no_fetch_no_write(self, tmp_path):
        archiver = _make_book_archiver(tmp_path, formats=["pdf"])
        empty_books = {
            99: _make_book_node(99, "empty-book", has_contents=False),
            100: _make_book_node(100, "also-empty", has_contents=False),
        }

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
        ) as mock_get_bytes, patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ) as mock_write_tar:
            archiver.archive(empty_books)

        assert mock_get_bytes.call_count == 0
        assert mock_write_tar.call_count == 0


# ---------------------------------------------------------------------------
# 7. Empty input dict → warn, no writes
# ---------------------------------------------------------------------------

class TestEmptyInput:
    def test_empty_input_no_writes(self, tmp_path):
        archiver = _make_book_archiver(tmp_path, formats=["pdf"])
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
        ) as mock_get_bytes, patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ) as mock_write_tar:
            archiver.archive({})
        assert mock_get_bytes.call_count == 0
        assert mock_write_tar.call_count == 0


# ---------------------------------------------------------------------------
# 8. Asset config defaults (Task 1)
# ---------------------------------------------------------------------------

class TestAssetConfigDefaults:
    def test_no_asset_config_means_modify_links_false(self, tmp_path):
        archiver = _make_book_archiver(tmp_path)
        assert archiver.modify_links is False
        assert archiver.export_images is False
        assert archiver.export_attachments is False


# ---------------------------------------------------------------------------
# 9. Folder layout (Task 2)
# ---------------------------------------------------------------------------

class TestFolderLayout:
    def test_book_content_written_inside_node_folder(self, tmp_path):
        archiver = _make_book_archiver(tmp_path, formats=["markdown"])
        node = _make_book_node(1, "my-book")
        written = {}
        archiver.write_data = written.__setitem__
        archiver._get_node_data = lambda url: b"# combined"
        archiver._archive_level({1: node}, "books", "book")
        assert f"{archiver.archive_base_path}/my-book/my-book.md" in written

    def test_book_meta_written_inside_node_folder(self, tmp_path):
        archiver = _make_book_archiver(tmp_path, formats=["markdown"], export_meta=True)
        node = _make_book_node(1, "my-book")
        written = {}
        archiver.write_data = written.__setitem__
        archiver._get_node_data = lambda url: b"# combined"
        archiver._archive_level({1: node}, "books", "book")
        assert f"{archiver.archive_base_path}/my-book/my-book_meta.json" in written
