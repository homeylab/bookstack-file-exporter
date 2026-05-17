# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name,unused-argument
"""Integration regression test for GitHub issue #74.

Exercises NodeExporter.get_all_pages end-to-end with a mocked HttpHelper using
the book_detail_mixed fixture (2 direct pages + 2 chapters, each chapter fetched
via synth_chapter_detail which yields 2 unique pages per chapter = 6 page nodes
total).
"""
from typing import Dict, List, Union
from unittest.mock import MagicMock

import pytest

from bookstack_file_exporter.exporter.exporter import NodeExporter
from bookstack_file_exporter.exporter.node import Node
from tests.helpers import make_response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page(page_id: int, book_id: int = 10,
               chapter_id: Union[int, None] = None) -> Dict:
    """Synthesize a minimal page detail dict for the given page_id."""
    return {
        "id": page_id,
        "name": f"page-{page_id}",
        "slug": f"page-{page_id}-slug",
        "book_id": book_id,
        "chapter_id": chapter_id,
    }


def synth_chapter_detail(chapter_id: int) -> Dict:
    """Produce a fresh chapter detail with unique page ids per chapter.

    Uses ``chapter_id * 10`` as the base page id to guarantee uniqueness
    across all chapters present in book_detail_mixed.json (ids 200, 201).
    """
    base_page_id = chapter_id * 10  # ensures uniqueness
    return {
        "id": chapter_id,
        "name": f"chapter-{chapter_id}",
        "slug": f"chapter-{chapter_id}",
        "book_id": 10,
        "pages": [
            {
                "id": base_page_id + 1,
                "name": f"chapter-{chapter_id}-page-1",
                "slug": f"chapter-{chapter_id}-page-1",
            },
            {
                "id": base_page_id + 2,
                "name": f"chapter-{chapter_id}-page-2",
                "slug": f"chapter-{chapter_id}-page-2",
            },
        ],
    }


# ---------------------------------------------------------------------------
# Fixture IDs drawn directly from fixtures/book_detail_mixed.json
# ---------------------------------------------------------------------------
_BOOK_ID = 10
_DIRECT_PAGE_IDS: List[int] = [100, 101]
_CHAPTER_IDS: List[int] = [200, 201]

# Chapter page ids produced by synth_chapter_detail for each chapter id.
# chapter 200 -> pages 2001, 2002
# chapter 201 -> pages 2011, 2012
_CHAPTER_PAGE_IDS: List[int] = [
    chapter_id * 10 + offset
    for chapter_id in _CHAPTER_IDS
    for offset in (1, 2)
]


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------

@pytest.mark.integration
# integration test reads multi-level fixtures; splitting hurts clarity
def test_get_all_pages_mixed_book(  # pylint: disable=too-many-locals
    mock_http_client, api_urls, book_detail_mixed
):
    """get_all_pages must return direct pages AND all chapter pages for a
    book that mixes direct pages and chapters at the same level.

    With two chapters each yielding 2 unique pages the expected total is:
      2 direct pages + 2 chapters * 2 pages = 6 page nodes.
    """

    base_pages_url = api_urls["pages"]        # "https://wiki.test.example/api/pages"
    base_chapters_url = api_urls["chapters"]  # "https://wiki.test.example/api/chapters"

    def http_get_request_side_effect(url: str) -> MagicMock:
        # Direct-page detail: /api/pages/<id>
        for page_id in _DIRECT_PAGE_IDS:
            if url == f"{base_pages_url}/{page_id}":
                return make_response(
                    _make_page(page_id, book_id=_BOOK_ID, chapter_id=None)
                )

        # Chapter-page detail: /api/pages/<id>
        for page_id in _CHAPTER_PAGE_IDS:
            if url == f"{base_pages_url}/{page_id}":
                # Determine which chapter owns this page
                chapter_id = page_id // 10
                return make_response(
                    _make_page(page_id, book_id=_BOOK_ID, chapter_id=chapter_id)
                )

        # Chapter detail: /api/chapters/<id>
        for chapter_id in _CHAPTER_IDS:
            if url == f"{base_chapters_url}/{chapter_id}":
                return make_response(synth_chapter_detail(chapter_id))

        raise ValueError(f"Unexpected URL in mock dispatcher: {url}")

    mock_http_client.http_get_request.side_effect = http_get_request_side_effect

    # Build the exporter and the single book node from fixture
    exporter = NodeExporter(api_urls=api_urls, http_client=mock_http_client)
    book_node = Node(book_detail_mixed)
    book_nodes: Dict[int, Node] = {_BOOK_ID: book_node}

    # -----------------------------------------------------------------------
    # Exercise
    # -----------------------------------------------------------------------
    result = exporter.get_all_pages(book_nodes)

    # -----------------------------------------------------------------------
    # Assertion 1: result is a Dict[int, Node]
    # -----------------------------------------------------------------------
    assert isinstance(result, dict), "get_all_pages must return a dict"
    for key, value in result.items():
        assert isinstance(key, int), f"Key {key!r} must be an int page id"
        assert isinstance(value, Node), f"Value for key {key} must be a Node"

    # -----------------------------------------------------------------------
    # Assertion 2: count — 2 direct + 4 chapter = 6 distinct page nodes
    # -----------------------------------------------------------------------
    expected_page_ids = set(_DIRECT_PAGE_IDS + _CHAPTER_PAGE_IDS)
    assert len(result) == len(expected_page_ids), (
        f"Expected {len(expected_page_ids)} page nodes, got {len(result)}: "
        f"{set(result.keys())}"
    )
    assert len(result) == 6, f"Expected exactly 6 page nodes, got {len(result)}"

    # -----------------------------------------------------------------------
    # Assertion 3: coverage — every expected page id is present
    # -----------------------------------------------------------------------
    for page_id in expected_page_ids:
        assert page_id in result, f"Page id {page_id} missing from result"

    # -----------------------------------------------------------------------
    # Assertion 4: parentage — direct pages point to book_node
    # -----------------------------------------------------------------------
    for page_id in _DIRECT_PAGE_IDS:
        node = result[page_id]
        assert node.parent is book_node, (
            f"Direct page {page_id} should have the book node as parent"
        )

    # -----------------------------------------------------------------------
    # Assertion 5: parentage — chapter pages point through a chapter node
    #              that itself points to book_node
    # -----------------------------------------------------------------------
    for page_id in _CHAPTER_PAGE_IDS:
        node = result[page_id]
        chapter_node = node.parent
        assert chapter_node is not None, (
            f"Chapter page {page_id} must have a chapter parent"
        )
        assert chapter_node.parent is book_node, (
            f"Chapter page {page_id}'s parent chapter must have book_node as its parent"
        )

    # -----------------------------------------------------------------------
    # Assertion 6: no chapter ids appear as page node keys
    # -----------------------------------------------------------------------
    for chapter_id in _CHAPTER_IDS:
        assert chapter_id not in result, (
            f"Chapter id {chapter_id} must NOT appear as a page node key"
        )
