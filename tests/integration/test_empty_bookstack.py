# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name,unused-argument
"""regression test: empty bookstack instance exports nothing cleanly"""

import logging
from typing import Dict

import pytest

from bookstack_file_exporter.exporter.exporter import NodeExporter
from bookstack_file_exporter.exporter.node import Node


@pytest.mark.integration
def test_full_traversal_empty_bookstack(mock_http_client, api_urls, caplog):
    """empty bookstack: no shelves, no books, no pages — returns empty dicts cleanly"""
    caplog.set_level(logging.WARNING)
    mock_http_client.http_get_all.return_value = []

    exporter = NodeExporter(api_urls, mock_http_client)
    shelves: Dict[int, Node] = exporter.get_all_shelves()
    books: Dict[int, Node] = exporter.get_all_books(shelves, "unassigned")
    pages: Dict[int, Node] = exporter.get_all_pages(books)

    assert not shelves
    assert not books
    assert not pages

    # warning logged for empty shelf list (matches existing get_all_shelves behavior)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("No shelves found" in r.getMessage() for r in warnings)
