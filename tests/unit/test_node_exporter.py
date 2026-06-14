# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name,unused-argument,protected-access
"""Unit tests for NodeExporter."""
import logging

import pytest

from bookstack_file_exporter.exporter.exporter import NodeExporter
from bookstack_file_exporter.exporter.filter import NodeFilter
from bookstack_file_exporter.config_helper.models import Filters, ResourceFilter
from bookstack_file_exporter.exporter.node import Node
from tests.helpers import make_response

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LOGGER_NAME = "bookstack_file_exporter.exporter.exporter"


def _exporter(api_urls, mock_http_client) -> NodeExporter:
    return NodeExporter(api_urls, mock_http_client)


def _make_filter(**kwargs) -> NodeFilter:
    """Build a NodeFilter from keyword args mapping resource_type → ResourceFilter kwargs.

    Example: _make_filter(books={"exclude": ["draft"]})
    """
    rf_kwargs = {k: ResourceFilter(**v) for k, v in kwargs.items()}
    return NodeFilter(Filters(**rf_kwargs))


# ---------------------------------------------------------------------------
# _get_all_ids
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("items,expected_ids", [
    ([], []),
    (
        [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}, {"id": 3, "name": "c"}],
        [1, 2, 3],
    ),
])
def test_get_all_ids(api_urls, mock_http_client, items, expected_ids):
    mock_http_client.http_get_all.return_value = items
    exporter = _exporter(api_urls, mock_http_client)
    result = exporter._get_all_ids(api_urls["shelves"])
    assert result == expected_ids


# ---------------------------------------------------------------------------
# get_all_shelves
# ---------------------------------------------------------------------------

def test_get_all_shelves_empty_logs_warning_and_returns_empty(
    api_urls, mock_http_client, caplog
):
    mock_http_client.http_get_all.return_value = []
    exporter = _exporter(api_urls, mock_http_client)
    caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)
    result = exporter.get_all_shelves()
    assert not result
    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("No shelves" in m for m in warning_messages)


def test_get_all_shelves_nonempty_returns_dict_keyed_by_id(
    api_urls, mock_http_client, shelf_detail
):
    mock_http_client.http_get_all.return_value = [{"id": 1}]
    mock_http_client.http_get_request.return_value = make_response(shelf_detail)
    exporter = _exporter(api_urls, mock_http_client)
    result = exporter.get_all_shelves()
    assert 1 in result
    assert isinstance(result[1], Node)
    assert mock_http_client.http_get_request.call_count == 1


def test_get_all_shelves_multiple_ids_each_fetched(api_urls, mock_http_client, shelf_detail):
    shelf2 = dict(shelf_detail, id=2, slug="shelf-2", name="Shelf 2")
    mock_http_client.http_get_all.return_value = [{"id": 1}, {"id": 2}]
    mock_http_client.http_get_request.side_effect = [
        make_response(shelf_detail),
        make_response(shelf2),
    ]
    exporter = _exporter(api_urls, mock_http_client)
    result = exporter.get_all_shelves()
    assert set(result.keys()) == {1, 2}


# ---------------------------------------------------------------------------
# get_chapter_nodes
# ---------------------------------------------------------------------------

def test_get_chapter_nodes_empty_book_nodes_returns_empty(api_urls, mock_http_client):
    exporter = _exporter(api_urls, mock_http_client)
    result = exporter.get_chapter_nodes({})
    assert not result
    mock_http_client.http_get_request.assert_not_called()


def test_get_chapter_nodes_book_with_only_pages_returns_empty(
    api_urls, mock_http_client, build_node
):
    book_node = build_node(
        id=10, name="Book Only Pages", slug="book-only-pages",
        contents=[
            {"id": 100, "type": "page", "name": "Page A", "slug": "page-a"},
            {"id": 101, "type": "page", "name": "Page B", "slug": "page-b"},
        ],
    )
    exporter = _exporter(api_urls, mock_http_client)
    result = exporter.get_chapter_nodes({10: book_node})
    assert not result
    mock_http_client.http_get_request.assert_not_called()


def test_get_chapter_nodes_mixed_book_fetches_chapters(
    api_urls, mock_http_client, book_detail_mixed, chapter_detail
):
    book_node = Node(book_detail_mixed)
    chapter2 = dict(chapter_detail, id=201, slug="test-chapter-2", name="Test Chapter 2")

    def _side_effect(url):
        if "/chapters/200" in url:
            return make_response(chapter_detail)
        if "/chapters/201" in url:
            return make_response(chapter2)
        raise AssertionError(f"unexpected url: {url}")

    mock_http_client.http_get_request.side_effect = _side_effect
    exporter = _exporter(api_urls, mock_http_client)
    result = exporter.get_chapter_nodes({10: book_node})
    assert set(result.keys()) == {200, 201}


def test_get_chapter_nodes_chapter_parent_is_book_node(
    api_urls, mock_http_client, book_detail_mixed, chapter_detail
):
    book_node = Node(book_detail_mixed)
    chapter2 = dict(chapter_detail, id=201, slug="test-chapter-2", name="Test Chapter 2")

    def _side_effect(url):
        if "/chapters/200" in url:
            return make_response(chapter_detail)
        if "/chapters/201" in url:
            return make_response(chapter2)
        raise AssertionError(f"unexpected url: {url}")

    mock_http_client.http_get_request.side_effect = _side_effect
    exporter = _exporter(api_urls, mock_http_client)
    result = exporter.get_chapter_nodes({10: book_node})
    for chapter in result.values():
        assert chapter.parent is book_node


def test_get_chapter_nodes_multiple_books(
    api_urls, mock_http_client, chapter_detail, build_node
):
    ch_a = dict(chapter_detail, id=200, slug="ch-a", name="Chapter A")
    ch_b = dict(chapter_detail, id=300, slug="ch-b", name="Chapter B")
    book_a = build_node(
        id=10, slug="book-a", name="Book A",
        contents=[{"id": 200, "type": "chapter"}],
    )
    book_b = build_node(
        id=11, slug="book-b", name="Book B",
        contents=[{"id": 300, "type": "chapter"}],
    )

    def _side_effect(url):
        if "/chapters/200" in url:
            return make_response(ch_a)
        if "/chapters/300" in url:
            return make_response(ch_b)
        raise AssertionError(f"unexpected url: {url}")

    mock_http_client.http_get_request.side_effect = _side_effect
    exporter = _exporter(api_urls, mock_http_client)
    result = exporter.get_chapter_nodes({10: book_a, 11: book_b})
    assert set(result.keys()) == {200, 300}


# ---------------------------------------------------------------------------
# get_unassigned_books
# ---------------------------------------------------------------------------

def test_get_unassigned_books_all_assigned_returns_empty(
    api_urls, mock_http_client, build_node
):
    existing = {10: build_node(id=10, slug="book-10", name="Book 10")}
    mock_http_client.http_get_all.return_value = [{"id": 10}]
    exporter = _exporter(api_urls, mock_http_client)
    result = exporter.get_unassigned_books(existing, "unassigned/")
    assert not result
    mock_http_client.http_get_request.assert_not_called()


def test_get_unassigned_books_one_unassigned_fetched_with_prefix(
    api_urls, mock_http_client, book_detail_mixed, build_node
):
    existing = {10: build_node(id=10, slug="book-10", name="Book 10")}
    unassigned_data = dict(book_detail_mixed, id=99, slug="orphan-book", name="Orphan Book")
    mock_http_client.http_get_all.return_value = [{"id": 10}, {"id": 99}]
    mock_http_client.http_get_request.return_value = make_response(unassigned_data)
    exporter = _exporter(api_urls, mock_http_client)
    result = exporter.get_unassigned_books(existing, "unassigned/")
    assert 99 in result
    assert result[99].file_path.startswith("unassigned/")


# ---------------------------------------------------------------------------
# get_all_books
# ---------------------------------------------------------------------------

def test_get_all_books_shelves_no_unassigned(
    api_urls, mock_http_client, shelf_detail, book_detail_mixed
):
    shelf_node = Node(shelf_detail)
    book_data_10 = dict(book_detail_mixed, id=10, slug="test-book-1", name="Test Book 1")
    book_data_11 = dict(book_detail_mixed, id=11, slug="test-book-2", name="Test Book 2")

    def _side_effect(url):
        if "/books/10" in url:
            return make_response(book_data_10)
        if "/books/11" in url:
            return make_response(book_data_11)
        raise AssertionError(f"unexpected url: {url}")

    # shelf has books 10 and 11; all-books list also only has 10 and 11
    mock_http_client.http_get_all.return_value = [{"id": 10}, {"id": 11}]
    mock_http_client.http_get_request.side_effect = _side_effect
    exporter = _exporter(api_urls, mock_http_client)
    result = exporter.get_all_books({1: shelf_node}, "unassigned/")
    assert set(result.keys()) == {10, 11}


def test_get_all_books_adds_unassigned_books(
    api_urls, mock_http_client, shelf_detail, book_detail_mixed
):
    shelf_node = Node(shelf_detail)
    book_data_10 = dict(book_detail_mixed, id=10, slug="test-book-1", name="Test Book 1")
    book_data_11 = dict(book_detail_mixed, id=11, slug="test-book-2", name="Test Book 2")
    unassigned_data = dict(book_detail_mixed, id=99, slug="orphan", name="Orphan")

    def _side_effect(url):
        if "/books/10" in url:
            return make_response(book_data_10)
        if "/books/11" in url:
            return make_response(book_data_11)
        if "/books/99" in url:
            return make_response(unassigned_data)
        raise AssertionError(f"unexpected url: {url}")

    # all-books includes 99 which isn't in the shelf
    mock_http_client.http_get_all.return_value = [{"id": 10}, {"id": 11}, {"id": 99}]
    mock_http_client.http_get_request.side_effect = _side_effect
    exporter = _exporter(api_urls, mock_http_client)
    result = exporter.get_all_books({1: shelf_node}, "unassigned/")
    assert 99 in result
    assert result[99].file_path.startswith("unassigned/")


def test_get_all_books_merges_unassigned(api_urls, mock_http_client, monkeypatch):
    exporter_obj = NodeExporter(api_urls, mock_http_client)
    monkeypatch.setattr(exporter_obj, "get_child_nodes", lambda *a, **k: {1: "shelf-book"})
    monkeypatch.setattr(exporter_obj, "get_unassigned_books", lambda *a, **k: {2: "loose-book"})
    result = exporter_obj.get_all_books({10: "shelf"}, "unassigned/")
    assert result == {1: "shelf-book", 2: "loose-book"}


# ---------------------------------------------------------------------------
# get_all_books — exclude_unassigned_books toggle
# ---------------------------------------------------------------------------

def test_exclude_unassigned_books_true_drops_orphan(
    api_urls, mock_http_client, shelf_detail, book_detail_mixed
):
    """exclude_unassigned_books=True: orphan book absent; its detail GET never issued."""
    node_filter = NodeFilter(Filters(exclude_unassigned_books=True))
    exporter = NodeExporter(api_urls, mock_http_client, node_filter=node_filter)

    shelf_node = Node(shelf_detail)
    book_data_10 = dict(book_detail_mixed, id=10, slug="test-book-1", name="Test Book 1")
    book_data_11 = dict(book_detail_mixed, id=11, slug="test-book-2", name="Test Book 2")

    def _side_effect(url):
        if "/books/10" in url:
            return make_response(book_data_10)
        if "/books/11" in url:
            return make_response(book_data_11)
        if "/books/99" in url:
            raise AssertionError("orphan book 99 detail should never be fetched")
        raise AssertionError(f"unexpected url: {url}")

    # books list includes orphan 99; shelf has books 10 and 11
    mock_http_client.http_get_all.return_value = [
        {"id": 10, "name": "Test Book 1"},
        {"id": 11, "name": "Test Book 2"},
        {"id": 99, "name": "Orphan Book"},
    ]
    mock_http_client.http_get_request.side_effect = _side_effect

    result = exporter.get_all_books({1: shelf_node}, "unassigned/")
    assert 10 in result
    assert 11 in result
    assert 99 not in result


def test_exclude_unassigned_books_false_includes_orphan(
    api_urls, mock_http_client, shelf_detail, book_detail_mixed
):
    """exclude_unassigned_books=False (default): orphan book is still exported."""
    node_filter = NodeFilter(Filters(exclude_unassigned_books=False))
    exporter = NodeExporter(api_urls, mock_http_client, node_filter=node_filter)

    shelf_node = Node(shelf_detail)
    book_data_10 = dict(book_detail_mixed, id=10, slug="test-book-1", name="Test Book 1")
    book_data_11 = dict(book_detail_mixed, id=11, slug="test-book-2", name="Test Book 2")
    orphan_data = dict(book_detail_mixed, id=99, slug="orphan-book", name="Orphan Book")

    def _side_effect(url):
        if "/books/10" in url:
            return make_response(book_data_10)
        if "/books/11" in url:
            return make_response(book_data_11)
        if "/books/99" in url:
            return make_response(orphan_data)
        raise AssertionError(f"unexpected url: {url}")

    mock_http_client.http_get_all.return_value = [
        {"id": 10, "name": "Test Book 1"},
        {"id": 11, "name": "Test Book 2"},
        {"id": 99, "name": "Orphan Book"},
    ]
    mock_http_client.http_get_request.side_effect = _side_effect

    result = exporter.get_all_books({1: shelf_node}, "unassigned/")
    assert 10 in result
    assert 11 in result
    assert 99 in result


def test_exclude_unassigned_books_true_independent_of_books_include(
    api_urls, mock_http_client, shelf_detail, book_detail_mixed
):
    """exclude_unassigned_books=True wins even when books.include would match the orphan."""
    node_filter = NodeFilter(Filters(
        exclude_unassigned_books=True,
        books=ResourceFilter(include=["Orphan Book"]),
    ))
    exporter = NodeExporter(api_urls, mock_http_client, node_filter=node_filter)

    shelf_node = Node(shelf_detail)
    book_data_10 = dict(book_detail_mixed, id=10, slug="test-book-1", name="Test Book 1")
    book_data_11 = dict(book_detail_mixed, id=11, slug="test-book-2", name="Test Book 2")

    def _side_effect(url):
        # Books 10 and 11 are on the shelf so they are fetched via get_child_nodes;
        # the books.include filter would normally drop them (they don't match "Orphan Book"),
        # but this test's concern is only that the orphan detail is never fetched.
        if "/books/10" in url or "/books/11" in url:
            # These will be dropped by the books.include filter; if somehow reached, fail.
            raise AssertionError(f"shelf book detail fetched unexpectedly: {url}")
        if "/books/99" in url:
            raise AssertionError("orphan 99 detail must not be fetched when toggle is True")
        raise AssertionError(f"unexpected url: {url}")

    mock_http_client.http_get_all.return_value = [
        {"id": 10, "name": "Test Book 1"},
        {"id": 11, "name": "Test Book 2"},
        {"id": 99, "name": "Orphan Book"},
    ]
    mock_http_client.http_get_request.side_effect = _side_effect

    result = exporter.get_all_books({1: shelf_node}, "unassigned/")
    assert 99 not in result


# ---------------------------------------------------------------------------
# get_child_nodes / _get_children
# ---------------------------------------------------------------------------

def test_get_child_nodes_page_filter_skips_chapters(
    api_urls, mock_http_client, book_detail_mixed, page_detail
):
    book_node = Node(book_detail_mixed)

    def _side_effect(url):
        if "/pages/100" in url:
            return make_response(page_detail)
        if "/pages/101" in url:
            page_b = dict(page_detail, id=101, slug="direct-page-b", name="Direct Page B")
            return make_response(page_b)
        raise AssertionError(f"unexpected url: {url}")

    mock_http_client.http_get_request.side_effect = _side_effect
    exporter = _exporter(api_urls, mock_http_client)
    result = exporter.get_child_nodes("pages", {10: book_node}, node_type="page")
    # only the 2 direct pages (100, 101) should be fetched; chapters 200, 201 skipped
    assert set(result.keys()) == {100, 101}


def test_get_child_nodes_filter_empty_true_excludes_empty_pages(
    api_urls, mock_http_client, build_node, page_detail
):
    book_node = build_node(
        id=10, slug="my-book", name="My Book",
        contents=[
            {"id": 100, "type": "page"},
            {"id": 999, "type": "page"},
        ],
    )
    empty_page = {"id": 999, "name": "New Page", "slug": ""}

    def _side_effect(url):
        if "/pages/100" in url:
            return make_response(page_detail)
        if "/pages/999" in url:
            return make_response(empty_page)
        raise AssertionError(f"unexpected url: {url}")

    mock_http_client.http_get_request.side_effect = _side_effect
    exporter = _exporter(api_urls, mock_http_client)
    result = exporter.get_child_nodes("pages", {10: book_node}, filter_empty=True, node_type="page")
    assert 100 in result
    assert 999 not in result


def test_get_child_nodes_filter_empty_false_includes_empty_pages(
    api_urls, mock_http_client, build_node, page_detail
):
    book_node = build_node(
        id=10, slug="my-book", name="My Book",
        contents=[
            {"id": 100, "type": "page"},
            {"id": 999, "type": "page"},
        ],
    )
    empty_page = {"id": 999, "name": "New Page", "slug": ""}

    def _side_effect(url):
        if "/pages/100" in url:
            return make_response(page_detail)
        if "/pages/999" in url:
            return make_response(empty_page)
        raise AssertionError(f"unexpected url: {url}")

    mock_http_client.http_get_request.side_effect = _side_effect
    exporter = _exporter(api_urls, mock_http_client)
    result = exporter.get_child_nodes(
        "pages", {10: book_node}, filter_empty=False, node_type="page"
    )
    assert 100 in result
    assert 999 in result


# ---------------------------------------------------------------------------
# NodeFilter integration — pre-GET filtering
# ---------------------------------------------------------------------------

# ── books ──────────────────────────────────────────────────────────────────

def test_filter_excluded_book_detail_never_fetched(
    api_urls, mock_http_client, shelf_detail, book_detail_mixed
):
    """Excluded book → its own detail GET is never issued (pre-GET guarantee)."""
    # shelf has books 10 ("Test Book 1") and 11 ("Test Book 2")
    # exclude book 10 by exact name
    node_filter = _make_filter(books={"exclude": ["Test Book 1"]})
    exporter = NodeExporter(api_urls, mock_http_client, node_filter=node_filter)
    shelf_node = Node(shelf_detail)
    book_data_11 = dict(book_detail_mixed, id=11, slug="test-book-2", name="Test Book 2")

    def _side_effect(url):
        if "/books/10" in url:
            raise AssertionError("should never fetch excluded book 10")
        if "/books/11" in url:
            return make_response(book_data_11)
        raise AssertionError(f"unexpected url: {url}")

    mock_http_client.http_get_request.side_effect = _side_effect
    result = exporter.get_child_nodes("books", {1: shelf_node})
    assert 10 not in result
    assert 11 in result


def test_filter_excluded_book_cascade_no_chapter_page_fetch(
    api_urls, mock_http_client, shelf_detail, book_detail_mixed
):
    """Dropped book → its chapter/page endpoints never called."""
    node_filter = _make_filter(books={"exclude": ["Test Book 1"]})
    exporter = NodeExporter(api_urls, mock_http_client, node_filter=node_filter)
    shelf_node = Node(shelf_detail)
    # Only book 11 survives; book 10 is dropped entirely
    book_data_11 = dict(book_detail_mixed, id=11, slug="test-book-2", name="Test Book 2",
                        contents=[])

    def _side_effect(url):
        if "/books/10" in url or "/chapters/2" in url or "/pages/1" in url:
            raise AssertionError(f"should never fetch descendants of excluded book: {url}")
        if "/books/11" in url:
            return make_response(book_data_11)
        raise AssertionError(f"unexpected url: {url}")

    mock_http_client.http_get_request.side_effect = _side_effect
    book_nodes = exporter.get_child_nodes("books", {1: shelf_node})
    assert 10 not in book_nodes


# ── pages — both paths ─────────────────────────────────────────────────────

def test_filter_direct_page_under_book_excluded(
    api_urls, mock_http_client, book_detail_mixed, page_detail
):
    """pages.exclude match dropped for page directly under a book (:143 path)."""
    node_filter = _make_filter(pages={"exclude": ["Direct Page A"]})
    exporter = NodeExporter(api_urls, mock_http_client, node_filter=node_filter)
    book_node = Node(book_detail_mixed)

    # Page 101 (Direct Page B) should be fetched; page 100 (Direct Page A) should not
    page_b = dict(page_detail, id=101, slug="direct-page-b", name="Direct Page B")

    def _side_effect(url):
        if "/pages/100" in url:
            raise AssertionError("should not fetch excluded Direct Page A")
        if "/pages/101" in url:
            return make_response(page_b)
        raise AssertionError(f"unexpected url: {url}")

    mock_http_client.http_get_request.side_effect = _side_effect
    result = exporter.get_child_nodes("pages", {10: book_node}, node_type="page")
    assert 100 not in result
    assert 101 in result


def test_filter_chapter_page_excluded(
    api_urls, mock_http_client, chapter_detail, build_node, page_detail
):
    """pages.exclude match dropped for page under a chapter (:152 path)."""
    node_filter = _make_filter(pages={"exclude": ["Chapter 1 Page 1"]})
    exporter = NodeExporter(api_urls, mock_http_client, node_filter=node_filter)
    chapter_node = Node(chapter_detail)
    # chapter_detail has pages 300 (Chapter 1 Page 1) and 301 (Chapter 1 Page 2)
    page_301 = dict(page_detail, id=301, slug="chapter-1-page-2", name="Chapter 1 Page 2")

    def _side_effect(url):
        if "/pages/300" in url:
            raise AssertionError("should not fetch excluded Chapter 1 Page 1")
        if "/pages/301" in url:
            return make_response(page_301)
        raise AssertionError(f"unexpected url: {url}")

    mock_http_client.http_get_request.side_effect = _side_effect
    result = exporter.get_child_nodes("pages", {200: chapter_node})
    assert 300 not in result
    assert 301 in result


# ── unassigned books ────────────────────────────────────────────────────────

def test_filter_unassigned_book_excluded(
    api_urls, mock_http_client, book_detail_mixed
):
    """Unassigned book matched by books.exclude → dropped; detail GET never issued."""
    node_filter = _make_filter(books={"exclude": ["Orphan Book"]})
    exporter = NodeExporter(api_urls, mock_http_client, node_filter=node_filter)
    # existing_books is empty → book 99 would normally be unassigned
    existing = {}
    mock_http_client.http_get_all.return_value = [
        {"id": 99, "name": "Orphan Book", "slug": "orphan-book"},
    ]

    def _side_effect(url):
        if "/books/99" in url:
            raise AssertionError("should not fetch excluded unassigned book 99")
        raise AssertionError(f"unexpected url: {url}")

    mock_http_client.http_get_request.side_effect = _side_effect
    result = exporter.get_unassigned_books(existing, "unassigned/")
    assert not result


# ── type isolation ───────────────────────────────────────────────────────────

def test_shelves_pattern_does_not_affect_unassigned_books(
    api_urls, mock_http_client, book_detail_mixed
):
    """A shelves pattern must not filter unassigned books."""
    # Exclude anything matching "Orphan Book" at the shelves type — should NOT drop the book
    node_filter = _make_filter(shelves={"exclude": ["Orphan Book"]})
    exporter = NodeExporter(api_urls, mock_http_client, node_filter=node_filter)
    unassigned_data = dict(book_detail_mixed, id=99, slug="orphan-book", name="Orphan Book")
    mock_http_client.http_get_all.return_value = [
        {"id": 99, "name": "Orphan Book", "slug": "orphan-book"},
    ]
    mock_http_client.http_get_request.return_value = make_response(unassigned_data)
    result = exporter.get_unassigned_books({}, "unassigned/")
    assert 99 in result


def test_books_pattern_does_not_affect_shelves(
    api_urls, mock_http_client, shelf_detail
):
    """A books pattern must not filter shelves (shelves always fetched)."""
    # Exclude "Test Shelf 1" at the books type — shelf should still be fetched
    node_filter = _make_filter(books={"exclude": ["Test Shelf 1"]})
    exporter = NodeExporter(api_urls, mock_http_client, node_filter=node_filter)
    mock_http_client.http_get_all.return_value = [{"id": 1}]
    mock_http_client.http_get_request.return_value = make_response(shelf_detail)
    result = exporter.get_all_shelves()
    assert 1 in result


# ── shelves → dropped shelf books not unassigned ────────────────────────────

def test_dropped_shelf_books_do_not_resurface_as_unassigned(
    api_urls, mock_http_client, shelf_detail, book_detail_mixed
):
    """When a shelf is dropped, its books must not resurface via get_unassigned_books."""
    # shelf_detail has books 10 and 11 under "Test Shelf 1"
    node_filter = _make_filter(shelves={"exclude": ["Test Shelf 1"]})
    exporter = NodeExporter(api_urls, mock_http_client, node_filter=node_filter)

    # get_all_shelves: one shelf (id=1) whose name "Test Shelf 1" is excluded
    mock_http_client.http_get_all.side_effect = [
        [{"id": 1}],            # shelves list
        [{"id": 10, "name": "Test Book 1"}, {"id": 11, "name": "Test Book 2"}],  # books list
    ]
    mock_http_client.http_get_request.return_value = make_response(shelf_detail)

    shelf_nodes = exporter.get_all_shelves()
    # The shelf was dropped — shelf_nodes should be empty
    assert not shelf_nodes

    # Now call get_all_books — books 10 and 11 should NOT resurface as unassigned
    def _side_effect(url):
        if "/books/10" in url or "/books/11" in url:
            raise AssertionError(f"books from dropped shelf should not be fetched: {url}")
        raise AssertionError(f"unexpected url: {url}")

    mock_http_client.http_get_request.side_effect = _side_effect
    book_nodes = exporter.get_all_books(shelf_nodes, "unassigned/")
    assert 10 not in book_nodes
    assert 11 not in book_nodes


def test_multi_shelf_book_under_pruned_and_surviving_shelf_still_exported(
    api_urls, mock_http_client, book_detail_mixed
):
    """Book on a pruned shelf AND a surviving shelf must still export."""
    # Shelf 1 (Archive) is dropped; shelf 2 (Keep) survives.
    # Both shelves list book 10. After pruning, book 10 is collected via shelf 2.
    node_filter = _make_filter(shelves={"exclude": ["Archive"]})
    exporter = NodeExporter(api_urls, mock_http_client, node_filter=node_filter)

    archive_shelf = {
        "id": 1, "name": "Archive", "slug": "archive", "books": [
            {"id": 10, "name": "Shared Book", "slug": "shared-book"},
        ]
    }
    keep_shelf = {
        "id": 2, "name": "Keep", "slug": "keep", "books": [
            {"id": 10, "name": "Shared Book", "slug": "shared-book"},
        ]
    }
    book_data = dict(book_detail_mixed, id=10, slug="shared-book", name="Shared Book")

    # http_get_all is called for shelves list, then books list (in get_unassigned_books)
    mock_http_client.http_get_all.side_effect = [
        [{"id": 1}, {"id": 2}],   # shelves list
        [{"id": 10, "name": "Shared Book"}],  # books list for unassigned check
    ]

    def _shelf_side_effect(url):
        if "/shelves/1" in url:
            return make_response(archive_shelf)
        if "/shelves/2" in url:
            return make_response(keep_shelf)
        if "/books/10" in url:
            return make_response(book_data)
        raise AssertionError(f"unexpected url: {url}")

    mock_http_client.http_get_request.side_effect = _shelf_side_effect

    shelf_nodes = exporter.get_all_shelves()
    # only shelf 2 (Keep) survives
    assert 1 not in shelf_nodes
    assert 2 in shelf_nodes

    book_nodes = exporter.get_all_books(shelf_nodes, "unassigned/")
    # book 10 was on a surviving shelf → must be present
    assert 10 in book_nodes


def test_book_on_pruned_shelf_also_books_excluded_stays_dropped(
    api_urls, mock_http_client, book_detail_mixed
):
    """Book on pruned shelf + also matched by books.exclude → dropped, not re-fetched."""
    node_filter = _make_filter(
        shelves={"exclude": ["Archive"]},
        books={"exclude": ["Shared Book"]},
    )
    exporter = NodeExporter(api_urls, mock_http_client, node_filter=node_filter)

    archive_shelf = {
        "id": 1, "name": "Archive", "slug": "archive", "books": [
            {"id": 10, "name": "Shared Book", "slug": "shared-book"},
        ]
    }

    mock_http_client.http_get_all.side_effect = [
        [{"id": 1}],   # shelves list
        [{"id": 10, "name": "Shared Book"}],  # books list (for unassigned)
    ]

    mock_http_client.http_get_request.side_effect = [make_response(archive_shelf)]

    shelf_nodes = exporter.get_all_shelves()
    assert not shelf_nodes

    def _raise_if_book_fetched(url):
        if "/books/10" in url:
            raise AssertionError("book on pruned shelf+books.exclude should never be fetched")
        raise AssertionError(f"unexpected url: {url}")

    mock_http_client.http_get_request.side_effect = _raise_if_book_fetched
    book_nodes = exporter.get_all_books(shelf_nodes, "unassigned/")
    assert 10 not in book_nodes


# ── chapters ────────────────────────────────────────────────────────────────

def test_filter_chapter_excluded_detail_never_fetched(
    api_urls, mock_http_client, book_detail_mixed, chapter_detail
):
    """Excluded chapter → its own detail GET is never issued."""
    # book_detail_mixed has chapters 200 ("Test Chapter 1") and 201 ("Test Chapter 2")
    node_filter = _make_filter(chapters={"exclude": ["Test Chapter 1"]})
    exporter = NodeExporter(api_urls, mock_http_client, node_filter=node_filter)
    book_node = Node(book_detail_mixed)
    chapter2 = dict(chapter_detail, id=201, slug="test-chapter-2", name="Test Chapter 2",
                    pages=[])

    def _side_effect(url):
        if "/chapters/200" in url:
            raise AssertionError("should never fetch excluded chapter 200")
        if "/chapters/201" in url:
            return make_response(chapter2)
        raise AssertionError(f"unexpected url: {url}")

    mock_http_client.http_get_request.side_effect = _side_effect
    result = exporter.get_chapter_nodes({10: book_node})
    assert 200 not in result
    assert 201 in result


def test_filter_chapter_excluded_pages_not_fetched_export_pages(
    api_urls, mock_http_client, book_detail_mixed, chapter_detail, page_detail
):
    """Chapter excluded → its pages pruned at export_level: pages."""
    # Exclude chapter 200; its page 300 should never be fetched
    node_filter = _make_filter(chapters={"exclude": ["Test Chapter 1"]})
    exporter = NodeExporter(api_urls, mock_http_client, node_filter=node_filter)
    book_node = Node(book_detail_mixed)

    chapter2 = dict(chapter_detail, id=201, slug="test-chapter-2", name="Test Chapter 2",
                    pages=[{"id": 400, "name": "Ch2 Page 1", "slug": "ch2-page-1",
                            "book_id": 10, "chapter_id": 201}])
    page_400 = dict(page_detail, id=400, name="Ch2 Page 1", slug="ch2-page-1")

    def _side_effect(url):
        if "/chapters/200" in url:
            raise AssertionError("should never fetch excluded chapter 200")
        if "/pages/300" in url:
            raise AssertionError("page 300 belongs to excluded chapter, must not be fetched")
        if "/chapters/201" in url:
            return make_response(chapter2)
        if "/pages/400" in url:
            return make_response(page_400)
        raise AssertionError(f"unexpected url: {url}")

    mock_http_client.http_get_request.side_effect = _side_effect
    chapter_nodes = exporter.get_chapter_nodes({10: book_node})
    assert 200 not in chapter_nodes
    # Chapter 2's pages should be fetchable
    page_nodes = exporter.get_child_nodes("pages", chapter_nodes)
    assert 300 not in page_nodes
    assert 400 in page_nodes


def test_filter_chapter_excluded_at_export_level_chapters(
    api_urls, mock_http_client, book_detail_mixed, chapter_detail
):
    """Chapter excluded → dropped from result at export_level: chapters."""
    node_filter = _make_filter(chapters={"exclude": ["Test Chapter 1"]})
    exporter = NodeExporter(api_urls, mock_http_client, node_filter=node_filter)
    book_node = Node(book_detail_mixed)
    chapter2 = dict(chapter_detail, id=201, slug="test-chapter-2", name="Test Chapter 2",
                    pages=[])

    def _side_effect(url):
        if "/chapters/200" in url:
            raise AssertionError("should never fetch excluded chapter 200")
        if "/chapters/201" in url:
            return make_response(chapter2)
        raise AssertionError(f"unexpected url: {url}")

    mock_http_client.http_get_request.side_effect = _side_effect
    # At export_level=chapters, run.py calls get_chapter_nodes directly
    chapter_nodes = exporter.get_chapter_nodes({10: book_node})
    assert 200 not in chapter_nodes
    assert 201 in chapter_nodes


# ── no-filter no-op ─────────────────────────────────────────────────────────

def test_no_filter_behavior_unchanged(
    api_urls, mock_http_client, shelf_detail, book_detail_mixed
):
    """When node_filter is None, all books are fetched as before."""
    exporter = NodeExporter(api_urls, mock_http_client, node_filter=None)
    shelf_node = Node(shelf_detail)
    book_data_10 = dict(book_detail_mixed, id=10, slug="test-book-1", name="Test Book 1")
    book_data_11 = dict(book_detail_mixed, id=11, slug="test-book-2", name="Test Book 2")

    def _side_effect(url):
        if "/books/10" in url:
            return make_response(book_data_10)
        if "/books/11" in url:
            return make_response(book_data_11)
        raise AssertionError(f"unexpected url: {url}")

    mock_http_client.http_get_request.side_effect = _side_effect
    result = exporter.get_child_nodes("books", {1: shelf_node})
    assert set(result.keys()) == {10, 11}
