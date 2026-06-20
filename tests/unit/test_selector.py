# pylint: disable=missing-function-docstring,missing-module-docstring
from bookstack_file_exporter.exporter import selector
from bookstack_file_exporter.exporter.node import Node
from bookstack_file_exporter.exporter.filter import NodeFilter
from bookstack_file_exporter.config_helper.models import Filters, ResourceFilter


def _make_filter(**kwargs) -> NodeFilter:
    rf_kwargs = {k: ResourceFilter(**v) for k, v in kwargs.items()}
    return NodeFilter(Filters(**rf_kwargs))


def _shelf(shelf_id: int, name: str, book_ids: list[int]) -> Node:
    meta = {
        "id": shelf_id,
        "slug": f"shelf-{shelf_id}",
        "name": name,
        "books": [{"id": bid, "name": f"book-{bid}"} for bid in book_ids],
    }
    return Node(meta)


def test_partition_shelves_no_filter_passthrough():
    shelves = {1: _shelf(1, "Keep", [10, 11])}
    surviving, excluded = selector.partition_shelves(shelves, None)
    assert surviving == shelves
    assert excluded == set()


def test_partition_shelves_drops_unmatched_and_records_book_ids():
    shelves = {
        1: _shelf(1, "keep-me", [10, 11]),
        2: _shelf(2, "drop-me", [20, 21]),
    }
    node_filter = _make_filter(shelves={"include": ["keep-me"]})
    surviving, excluded = selector.partition_shelves(shelves, node_filter)
    assert set(surviving.keys()) == {1}
    assert excluded == {20, 21}
