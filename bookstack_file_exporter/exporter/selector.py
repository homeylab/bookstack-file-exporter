"""Pure filter/cascade decision functions for NodeExporter.

No I/O. These functions decide *which* candidate nodes survive filtering and
cascade suppression; NodeExporter performs the actual fetches and calls these
before each detail GET so excluded nodes are never fetched.
"""
import logging

from bookstack_file_exporter.exporter.node import Node
from bookstack_file_exporter.exporter.filter import NodeFilter

log = logging.getLogger(__name__)


def partition_shelves(
    shelf_nodes: dict[int, Node], node_filter: NodeFilter | None
) -> tuple[dict[int, Node], set[int]]:
    """Split fetched shelves into survivors and the book IDs to suppress.

    Returns (surviving_shelves, excluded_book_ids). When no filter is
    configured, all shelves survive and no books are suppressed.
    """
    if node_filter is None:
        return shelf_nodes, set()
    surviving: dict[int, Node] = {}
    excluded_book_ids: set[int] = set()
    for shelf_id, shelf_node in shelf_nodes.items():
        if node_filter.keep(shelf_node.display_name, "shelves"):
            surviving[shelf_id] = shelf_node
        else:
            log.debug("Shelf '%s' excluded by filter; suppressing its books",
                      shelf_node.display_name)
            for book_entry in shelf_node.children:
                excluded_book_ids.add(book_entry['id'])
    return surviving, excluded_book_ids


def selectable_children(
    children: list[dict], resource_type: str,
    node_filter: NodeFilter | None, node_type: str = "",
) -> list[dict]:
    """Apply the pre-GET type + name gate to a parent's child summaries.

    Returns the child dicts that survive; the caller fetches each detail and
    applies filter_empty afterward. node_type (when set) restricts to children
    of that 'type' (used to pick pages vs chapters out of a book's contents).
    """
    selected: list[dict] = []
    for child in children:
        if node_type and child.get('type') != node_type:
            log.debug("child of type: %s is not desired type: %s",
                      child.get('type'), node_type)
            continue
        if node_filter and not node_filter.keep(child['name'], resource_type):
            log.debug("'%s' (type=%s) excluded by filter",
                      child['name'], resource_type)
            continue
        selected.append(child)
    return selected


def selectable_unassigned_books(
    all_books: list[dict], existing_ids: set[int],
    excluded_ids: set[int], node_filter: NodeFilter | None,
) -> list[int]:
    """Pick shelfless book IDs to fetch, applying the three pre-GET gates.

    1. Skip books already collected under a shelf (existing_ids).
    2. Skip books whose shelf was dropped (excluded_ids).
    3. When a filter is set, skip books failing the 'books' name filter.
    """
    selected: list[int] = []
    for book in all_books:
        book_id = book['id']
        if book_id in existing_ids:
            continue
        if book_id in excluded_ids:
            log.debug("Book id=%d suppressed (its shelf was excluded)", book_id)
            continue
        if node_filter and not node_filter.keep(book['name'], "books"):
            log.debug("Unassigned book '%s' excluded by filter", book['name'])
            continue
        selected.append(book_id)
    return selected
