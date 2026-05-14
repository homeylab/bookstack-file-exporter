import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.helpers import make_response  # noqa: F401  re-export

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str):
    with open(FIXTURES_DIR / name, "r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def shelf_detail():
    """example shelf api response with two books"""
    return _load_fixture("shelf_detail.json")


@pytest.fixture
def book_detail_mixed():
    """example book api response with mixed chapter+page contents"""
    return _load_fixture("book_detail_mixed.json")


@pytest.fixture
def chapter_detail():
    """example chapter api response with pages"""
    return _load_fixture("chapter_detail.json")


@pytest.fixture
def page_detail():
    """example page api response"""
    return _load_fixture("page_detail.json")


@pytest.fixture
def mock_http_client():
    """MagicMock substitute for HttpHelper"""
    client = MagicMock()
    return client


@pytest.fixture
def api_urls():
    """standard api_urls dict matching what NodeExporter expects"""
    return {
        "shelves": "https://wiki.test.example/api/shelves",
        "books": "https://wiki.test.example/api/books",
        "chapters": "https://wiki.test.example/api/chapters",
        "pages": "https://wiki.test.example/api/pages",
        "images": "https://wiki.test.example/api/image-gallery",
        "attachments": "https://wiki.test.example/api/attachments",
    }


@pytest.fixture
def http_config():
    """minimal HttpConfig for HttpHelper construction"""
    from bookstack_file_exporter.config_helper.models import HttpConfig
    return HttpConfig(
        timeout=10,
        verify_ssl=True,
        retry_count=0,
        backoff_factor=0,
        retry_codes=[],
    )


@pytest.fixture
def books_list_paginated():
    """example /api/books list response with pagination envelope"""
    return _load_fixture("books_list_paginated.json")


@pytest.fixture
def build_node():
    """factory for constructing Node instances inline with minimal boilerplate

    Usage:
        node = build_node(id=10, name="Book One", slug="book-one", contents=[...])
        chapter = build_node(id=200, name="Chapter X", book_id=10, pages=[...], parent=book)

    The factory returns a Node whose meta dict is `kwargs` minus reserved
    keys `parent` and `path_prefix`, which are forwarded to Node().
    """
    from bookstack_file_exporter.exporter.node import Node

    def _build(parent=None, path_prefix="", **meta):
        # required defaults so Node init succeeds even when caller omits them
        meta.setdefault("id", 1)
        meta.setdefault("name", "default-name")
        meta.setdefault("slug", meta["name"])
        return Node(meta, parent=parent, path_prefix=path_prefix)

    return _build
