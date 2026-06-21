# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name
# pylint: disable=protected-access,too-few-public-methods,duplicate-code
"""Unit tests for ChapterArchiver."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from requests.exceptions import HTTPError

from bookstack_file_exporter.archiver.node_archiver import ChapterArchiver
from bookstack_file_exporter.exporter.node import Node

_FIXTURES = Path(__file__).parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_CHAPTERS_URL = "https://wiki.test.example/api/chapters"
_API_URLS = {
    "books": "https://wiki.test.example/api/books",
    "chapters": _CHAPTERS_URL,
    "pages": "https://wiki.test.example/api/pages",
}


def _make_chapter_archiver(tmp_path, formats=None, export_meta=False):
    archive_dir = str(tmp_path / "bookstack-20260531")
    http_client = MagicMock()
    return ChapterArchiver(
        archive_dir=archive_dir,
        api_urls=_API_URLS,
        export_formats=formats or ["pdf"],
        http_client=http_client,
        export_meta=export_meta,
    )


def _make_book_node(book_id: int = 10, slug: str = "test-book") -> Node:
    meta = {"id": book_id, "name": slug, "slug": slug, "contents": []}
    return Node(meta, parent=None)


def _make_chapter_node(chapter_id: int, slug: str,
                        parent: Node, has_pages: bool = True) -> Node:
    """Build a chapter Node with a book parent."""
    pages = [{"id": 300, "slug": "page-1"}] if has_pages else []
    meta = {
        "id": chapter_id,
        "name": slug,
        "slug": slug,
        "pages": pages,
    }
    return Node(meta, parent=parent)


# ---------------------------------------------------------------------------
# 1. Construction
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_archive_file_ends_with_tgz(self, tmp_path):
        archiver = _make_chapter_archiver(tmp_path)
        assert archiver.archive_file.endswith(".tgz")

    def test_export_meta_stored(self, tmp_path):
        archiver = _make_chapter_archiver(tmp_path, export_meta=True)
        assert archiver.export_meta is True


# ---------------------------------------------------------------------------
# 2. N chapters × N formats → N*M write_tar calls
# ---------------------------------------------------------------------------

class TestArchiveMultipleChaptersAndFormats:
    @pytest.mark.parametrize("n_chapters,formats,expected_writes", [
        (1, ["pdf"], 1),
        (2, ["pdf"], 2),
        (2, ["pdf", "html"], 4),
        (3, ["markdown", "html", "pdf"], 9),
    ])
    def test_write_tar_call_count(self, tmp_path, n_chapters, formats, expected_writes):
        archiver = _make_chapter_archiver(tmp_path, formats=formats)
        book = _make_book_node()
        chapter_nodes = {
            i: _make_chapter_node(i, f"chapter-{i}", parent=book)
            for i in range(1, n_chapters + 1)
        }
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"chapter content",
        ), patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ) as mock_write_tar:
            archiver.archive(chapter_nodes)
        assert mock_write_tar.call_count == expected_writes


# ---------------------------------------------------------------------------
# 3. Export URL targets /api/chapters/{id}/export/{fmt}
# ---------------------------------------------------------------------------

class TestExportUrl:
    @pytest.mark.parametrize("export_format", ["pdf", "html", "markdown", "plaintext", "zip"])
    def test_url_contains_chapters_export_path(self, tmp_path, export_format):
        archiver = _make_chapter_archiver(tmp_path, formats=[export_format])
        book = _make_book_node()
        chapter_node = _make_chapter_node(55, "my-chapter", parent=book)

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"data",
        ) as mock_get_bytes, patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ):
            archiver.archive({55: chapter_node})

        called_url = mock_get_bytes.call_args.kwargs["url"]
        expected = f"{_CHAPTERS_URL}/55/export/{export_format}"
        assert called_url == expected


# ---------------------------------------------------------------------------
# 4. One format raises HTTPError → skipped, others written
# ---------------------------------------------------------------------------

class TestHTTPErrorHandling:
    def test_one_format_fails_others_written(self, tmp_path):
        archiver = _make_chapter_archiver(tmp_path, formats=["pdf", "html"])
        book = _make_book_node()
        chapter_node = _make_chapter_node(10, "test-chapter", parent=book)

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
            archiver.archive({10: chapter_node})

        assert mock_write_tar.call_count == 1

    def test_all_formats_fail_but_meta_still_written(self, tmp_path):
        """All format fetches fail, but export_meta still writes a meta file to the tar."""
        archiver = _make_chapter_archiver(tmp_path, formats=["pdf"], export_meta=True)
        book = _make_book_node()
        chapter_node = _make_chapter_node(10, "test-chapter", parent=book)

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            side_effect=HTTPError("pdf failed"),
        ), patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ) as mock_write_tar:
            archiver.archive({10: chapter_node})

        # pdf skipped, but meta still written → 1 write
        assert mock_write_tar.call_count == 1


# ---------------------------------------------------------------------------
# 5. export_meta on → +1 write per chapter
# ---------------------------------------------------------------------------

class TestExportMeta:
    def test_meta_written_per_chapter_when_enabled(self, tmp_path):
        archiver = _make_chapter_archiver(tmp_path, formats=["pdf"], export_meta=True)
        book = _make_book_node()
        chapter_nodes = {
            1: _make_chapter_node(1, "chapter-one", parent=book),
            2: _make_chapter_node(2, "chapter-two", parent=book),
        }
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"chapter data",
        ), patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ) as mock_write_tar:
            archiver.archive(chapter_nodes)
        # 2 chapters × 1 format + 2 meta files = 4 writes
        assert mock_write_tar.call_count == 4

    def test_meta_not_written_when_disabled(self, tmp_path):
        archiver = _make_chapter_archiver(tmp_path, formats=["pdf"], export_meta=False)
        book = _make_book_node()
        chapter_nodes = {1: _make_chapter_node(1, "chapter-one", parent=book)}
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"chapter data",
        ), patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ) as mock_write_tar:
            archiver.archive(chapter_nodes)
        assert mock_write_tar.call_count == 1


# ---------------------------------------------------------------------------
# 6. Empty chapter (no pages) → no fetch, no write
# ---------------------------------------------------------------------------

class TestEmptyChapter:
    def test_empty_chapter_skipped(self, tmp_path):
        archiver = _make_chapter_archiver(tmp_path, formats=["pdf"])
        book = _make_book_node()
        empty_chapter = _make_chapter_node(99, "empty-chapter", parent=book, has_pages=False)
        full_chapter = _make_chapter_node(100, "full-chapter", parent=book, has_pages=True)

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"data",
        ) as mock_get_bytes, patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ) as mock_write_tar:
            archiver.archive({99: empty_chapter, 100: full_chapter})

        assert mock_get_bytes.call_count == 1
        assert mock_write_tar.call_count == 1

    def test_all_empty_chapters_no_fetch_no_write(self, tmp_path):
        archiver = _make_chapter_archiver(tmp_path, formats=["pdf"])
        book = _make_book_node()
        empty_chapters = {
            99: _make_chapter_node(99, "empty-chapter", parent=book, has_pages=False),
            100: _make_chapter_node(100, "also-empty", parent=book, has_pages=False),
        }

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
        ) as mock_get_bytes, patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ) as mock_write_tar:
            archiver.archive(empty_chapters)

        assert mock_get_bytes.call_count == 0
        assert mock_write_tar.call_count == 0


# ---------------------------------------------------------------------------
# 7. Empty input dict → no writes
# ---------------------------------------------------------------------------

class TestEmptyInput:
    def test_empty_input_no_writes(self, tmp_path):
        archiver = _make_chapter_archiver(tmp_path, formats=["pdf"])
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
        ) as mock_get_bytes, patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.write_tar"
        ) as mock_write_tar:
            archiver.archive({})
        assert mock_get_bytes.call_count == 0
        assert mock_write_tar.call_count == 0



# ---------------------------------------------------------------------------
# 8. Descendant pages regression: chapter pages have no type key (Task 3)
# ---------------------------------------------------------------------------

class TestChapterDescendantPages:
    def test_chapter_pages_without_type_key_are_captured(self, tmp_path):
        archiver = _make_chapter_archiver(tmp_path)  # use the file's existing helper
        meta = json.loads((_FIXTURES / "chapter_detail.json").read_text())
        node = Node(meta, parent=None)
        result = archiver._descendant_page_names(node)
        expected = {p["id"]: p["slug"] for p in meta["pages"]}
        assert result == expected
        assert result, "chapter descendant pages must not be empty (no-type-key regression)"


# ---------------------------------------------------------------------------
# 9. Combined markdown rewrite for chapters (Task 5)
# ---------------------------------------------------------------------------

class TestChapterCombinedMarkdownRewrite:
    def _img(self, id_, uploaded_to):
        img = MagicMock(id_=id_, download_url=f"http://x/{id_}", uploaded_to=uploaded_to)
        img.get_relative_path = lambda page_name: f"images/{page_name}/{id_}.png"
        return img

    def test_chapter_markdown_urls_rewritten(self, tmp_path):
        archiver = _make_chapter_archiver(tmp_path, formats=["markdown"])
        archiver.asset_config = MagicMock(export_images=True, export_attachments=False,
                                          modify_links=True, export_meta=False)
        archiver.modify_links = True
        book = _make_book_node()
        # chapter pages list has no type key (the regression case)
        chapter_meta = {"id": 5, "name": "my-chapter", "slug": "my-chapter",
                        "pages": [{"id": 10, "slug": "pg", "name": "Pg"}]}
        node = Node(chapter_meta, parent=book)
        img = self._img(99, 10)
        aa = MagicMock()
        aa.get_asset_nodes.side_effect = lambda kind: {10: [img]} if kind == "images" else {}
        aa.get_asset_bytes.return_value = b"PNGDATA"
        aa.update_asset_links.side_effect = (
            lambda atype, page_name, data, nodes: data.replace(
                b"http://x/99", b"images/pg/99.png"))
        archiver.asset_archiver = aa
        written = {}
        archiver.write_data = written.__setitem__
        archiver._get_node_data = lambda url: b"![](http://x/99)"
        archiver._archive_level({5: node}, "chapters", "chapter")
        md_key = f"{archiver.archive_base_path}/test-book/my-chapter/my-chapter.md"
        assert md_key in written
        assert b"images/pg/99.png" in written[md_key]
        assert b"http://x/99" not in written[md_key]


# ---------------------------------------------------------------------------
# 10. Fix-4: standalone asset download at chapter level (modify_links=False)
# ---------------------------------------------------------------------------

def _make_img(id_, uploaded_to):
    img = MagicMock(id_=id_, download_url=f"http://x/{id_}", uploaded_to=uploaded_to)
    img.get_relative_path = lambda page_name: f"images/{page_name}/{id_}.png"
    return img


def _make_att(id_, uploaded_to):
    att = MagicMock(id_=id_, download_url=f"http://x/att/{id_}", uploaded_to=uploaded_to)
    att.get_relative_path = lambda page_name: f"attachments/{page_name}/{id_}.pdf"
    return att


def _make_chapter_archiver_with_assets(tmp_path, export_images=False, export_attachments=False,
                                       modify_links=False, formats=None):
    """Build a ChapterArchiver with an injected asset double configured per the given flags."""
    archiver = _make_chapter_archiver(tmp_path, formats=formats or ["markdown"])
    archiver.asset_config = MagicMock(
        export_images=export_images,
        export_attachments=export_attachments,
        modify_links=modify_links,
        export_meta=False,
    )
    archiver.modify_links = modify_links
    archiver.asset_archiver = MagicMock()
    return archiver


def _chapter_node_with_page():
    """Chapter under a book, one page (pages entries carry no type key)."""
    book = _make_book_node()
    meta = {"id": 5, "name": "my-chapter", "slug": "my-chapter",
            "pages": [{"id": 10, "slug": "pg", "name": "Pg"}]}
    return Node(meta, parent=book)


class TestFix4StandaloneAssetDownloadChapter:
    """Fix-4: export_images/export_attachments honored standalone at chapter level."""

    def test_images_downloaded_without_modify_links(self, tmp_path):
        """export_images=True + modify_links=False: image written to archive path."""
        archiver = _make_chapter_archiver_with_assets(tmp_path, export_images=True)
        img = _make_img(99, 10)
        archiver.asset_archiver.get_asset_nodes.side_effect = (
            lambda kind: {10: [img]} if kind == "images" else {}
        )
        archiver.asset_archiver.get_asset_bytes.return_value = b"PNGDATA"
        written = {}
        archiver.write_data = written.__setitem__
        archiver._get_node_data = lambda url: b"content"
        archiver._archive_level({5: _chapter_node_with_page()}, "chapters", "chapter")
        expected = f"{archiver.archive_base_path}/test-book/my-chapter/images/pg/99.png"
        assert expected in written
        assert written[expected] == b"PNGDATA"

    def test_attachments_downloaded_without_modify_links(self, tmp_path):
        """export_attachments=True + modify_links=False: attachment written to archive path."""
        archiver = _make_chapter_archiver_with_assets(tmp_path, export_attachments=True)
        att = _make_att(55, 10)
        archiver.asset_archiver.get_asset_nodes.side_effect = (
            lambda kind: {10: [att]} if kind == "attachments" else {}
        )
        archiver.asset_archiver.get_asset_bytes.return_value = b"ATTDATA"
        written = {}
        archiver.write_data = written.__setitem__
        archiver._get_node_data = lambda url: b"content"
        archiver._archive_level({5: _chapter_node_with_page()}, "chapters", "chapter")
        expected = f"{archiver.archive_base_path}/test-book/my-chapter/attachments/pg/55.pdf"
        assert expected in written
        assert written[expected] == b"ATTDATA"

    def test_markdown_not_rewritten_when_modify_links_false(self, tmp_path):
        """export_images=True + modify_links=False: original Bookstack URL retained in markdown."""
        archiver = _make_chapter_archiver_with_assets(tmp_path, export_images=True)
        img = _make_img(99, 10)
        archiver.asset_archiver.get_asset_nodes.side_effect = (
            lambda kind: {10: [img]} if kind == "images" else {}
        )
        archiver.asset_archiver.get_asset_bytes.return_value = b"PNGDATA"
        written = {}
        archiver.write_data = written.__setitem__
        archiver._get_node_data = lambda url: b"![](http://x/99)"
        archiver._archive_level({5: _chapter_node_with_page()}, "chapters", "chapter")
        md = written[f"{archiver.archive_base_path}/test-book/my-chapter/my-chapter.md"]
        assert b"http://x/99" in md
        archiver.asset_archiver.update_asset_links.assert_not_called()

    def test_images_only_no_attachment_fetch(self, tmp_path):
        """export_images=True, export_attachments=False: only images written."""
        archiver = _make_chapter_archiver_with_assets(tmp_path, export_images=True,
                                                      export_attachments=False)
        img = _make_img(99, 10)
        archiver.asset_archiver.get_asset_nodes.side_effect = (
            lambda kind: {10: [img]} if kind == "images" else {}
        )
        archiver.asset_archiver.get_asset_bytes.return_value = b"PNGDATA"
        written = {}
        archiver.write_data = written.__setitem__
        archiver._get_node_data = lambda url: b"content"
        archiver._archive_level({5: _chapter_node_with_page()}, "chapters", "chapter")
        assert any("images" in k for k in written)
        assert not any("attachments" in k for k in written)

    def test_attachments_only_no_image_fetch(self, tmp_path):
        """export_attachments=True, export_images=False: only attachments written."""
        archiver = _make_chapter_archiver_with_assets(tmp_path, export_images=False,
                                                      export_attachments=True)
        att = _make_att(55, 10)
        archiver.asset_archiver.get_asset_nodes.side_effect = (
            lambda kind: {10: [att]} if kind == "attachments" else {}
        )
        archiver.asset_archiver.get_asset_bytes.return_value = b"ATTDATA"
        written = {}
        archiver.write_data = written.__setitem__
        archiver._get_node_data = lambda url: b"content"
        archiver._archive_level({5: _chapter_node_with_page()}, "chapters", "chapter")
        assert any("attachments" in k for k in written)
        assert not any("images" in k for k in written)

    def test_both_flags_false_no_asset_fetch(self, tmp_path):
        """Both export flags False: no asset bytes fetched."""
        archiver = _make_chapter_archiver_with_assets(tmp_path, export_images=False,
                                                      export_attachments=False)
        archiver.asset_archiver.get_asset_nodes.return_value = {}
        archiver.write_data = lambda *a: None
        archiver._get_node_data = lambda url: b"content"
        archiver._archive_level({5: _chapter_node_with_page()}, "chapters", "chapter")
        archiver.asset_archiver.get_asset_bytes.assert_not_called()


class TestFix4InfoNoticeChapter:
    """Fix-4: INFO notice 'Assets downloaded but links not rewritten' at chapter level."""

    def test_info_emitted_when_assets_on_modify_links_off(self, tmp_path, caplog):
        """INFO notice fires when export_images=True and modify_links=False."""
        import logging  # pylint: disable=import-outside-toplevel
        archiver = _make_chapter_archiver_with_assets(tmp_path, export_images=True)
        archiver.asset_archiver.get_asset_nodes.return_value = {}
        archiver.write_data = lambda *a: None
        archiver._get_node_data = lambda url: b"content"
        with caplog.at_level(logging.INFO,
                             logger="bookstack_file_exporter.archiver.node_archiver"):
            archiver._archive_level({5: _chapter_node_with_page()}, "chapters", "chapter")
        assert any("modify_links disabled" in r.message for r in caplog.records)

    def test_info_not_emitted_when_modify_links_true(self, tmp_path, caplog):
        """INFO notice NOT fired when modify_links=True (link rewriting is active)."""
        import logging  # pylint: disable=import-outside-toplevel
        archiver = _make_chapter_archiver_with_assets(tmp_path, export_images=True,
                                                      modify_links=True)
        img = _make_img(99, 10)
        archiver.asset_archiver.get_asset_nodes.side_effect = (
            lambda kind: {10: [img]} if kind == "images" else {}
        )
        archiver.asset_archiver.get_asset_bytes.return_value = b"PNGDATA"
        archiver.asset_archiver.update_asset_links.side_effect = lambda *a, **kw: a[2]
        archiver.write_data = lambda *a: None
        archiver._get_node_data = lambda url: b"content"
        with caplog.at_level(logging.INFO,
                             logger="bookstack_file_exporter.archiver.node_archiver"):
            archiver._archive_level({5: _chapter_node_with_page()}, "chapters", "chapter")
        assert not any("modify_links disabled" in r.message for r in caplog.records)

    def test_info_not_emitted_when_both_asset_flags_false(self, tmp_path, caplog):
        """INFO notice NOT fired when both export flags are False."""
        import logging  # pylint: disable=import-outside-toplevel
        archiver = _make_chapter_archiver_with_assets(tmp_path, export_images=False,
                                                      export_attachments=False)
        archiver.asset_archiver.get_asset_nodes.return_value = {}
        archiver.write_data = lambda *a: None
        archiver._get_node_data = lambda url: b"content"
        with caplog.at_level(logging.INFO,
                             logger="bookstack_file_exporter.archiver.node_archiver"):
            archiver._archive_level({5: _chapter_node_with_page()}, "chapters", "chapter")
        assert not any("modify_links disabled" in r.message for r in caplog.records)
