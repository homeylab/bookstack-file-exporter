# pylint: disable=missing-class-docstring,missing-function-docstring
"""Pytest fixtures shared across all tests."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bookstack_file_exporter.archiver.asset_archiver import (
    AssetArchiver,
    AttachmentNode,
    ImageNode,
)
from bookstack_file_exporter.config_helper.models import HttpConfig
from bookstack_file_exporter.exporter.node import Node

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
def image_api_content():
    """image gallery API response for screenshot.png"""
    return _load_fixture("api_image_content.json")


@pytest.fixture
def attachment_api_content():
    """attachment API response for project-spec.pdf"""
    return _load_fixture("api_attachment_content.json")


@pytest.fixture
def html_anchor_wrapped_page():
    """HTML page bytes with anchor-wrapped image"""
    with open(FIXTURES_DIR / "html_page_anchor_wrapped_image.html", "rb") as fh:
        return fh.read()


@pytest.fixture
def html_attachment_page():
    """HTML page bytes with attachment link"""
    with open(FIXTURES_DIR / "html_page_attachment.html", "rb") as fh:
        return fh.read()


@pytest.fixture
def image_node():
    """ImageNode for screenshot.png, page id=7"""
    meta = {
        "id": 42,
        "uploaded_to": 7,
        "url": "https://wiki.example.com/uploads/images/gallery/2024-01/screenshot.png",
    }
    return ImageNode(meta)


@pytest.fixture
def attachment_node():
    """AttachmentNode for project-spec.pdf"""
    meta = {
        "id": 99,
        "uploaded_to": 7,
        "name": "project-spec.pdf",
        "external": False,
    }
    return AttachmentNode(meta, "https://wiki.example.com/attachments")


@pytest.fixture
def asset_archiver():
    """AssetArchiver with MagicMock http_client"""
    urls = {
        "images": "https://wiki.example.com/api/image-gallery",
        "attachments": "https://wiki.example.com/api/attachments",
    }
    http_client = MagicMock()
    return AssetArchiver(urls, http_client)


@pytest.fixture
def build_node():
    """factory for constructing Node instances inline with minimal boilerplate

    Usage:
        node = build_node(id=10, name="Book One", slug="book-one", contents=[...])
        chapter = build_node(id=200, name="Chapter X", book_id=10, pages=[...], parent=book)

    The factory returns a Node whose meta dict is `kwargs` minus reserved
    keys `parent` and `path_prefix`, which are forwarded to Node().
    """
    def _build(parent=None, path_prefix="", **meta):
        # required defaults so Node init succeeds even when caller omits them
        meta.setdefault("id", 1)
        meta.setdefault("name", "default-name")
        meta.setdefault("slug", meta["name"])
        return Node(meta, parent=parent, path_prefix=path_prefix)

    return _build
