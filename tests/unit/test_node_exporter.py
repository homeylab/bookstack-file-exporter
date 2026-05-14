# pylint: disable=missing-function-docstring,redefined-outer-name,unused-argument
"""Unit tests for NodeExporter."""
import logging
from typing import Dict, List

import pytest

from bookstack_file_exporter.exporter.exporter import NodeExporter
from bookstack_file_exporter.exporter.node import Node
from tests.helpers import make_response

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LOGGER_NAME = "bookstack_file_exporter.exporter.exporter"


def _exporter(api_urls, mock_http_client) -> NodeExporter:
    return NodeExporter(api_urls, mock_http_client)


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
    assert result == {}
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
    assert result == {}
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
    assert result == {}
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
    assert result == {}
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
