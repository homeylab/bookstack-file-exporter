import logging
from typing import Optional

# pylint: disable=import-error
from requests import Response

from bookstack_file_exporter.exporter.node import Node
from bookstack_file_exporter.exporter.filter import NodeFilter
from bookstack_file_exporter.common.util import HttpHelper

log = logging.getLogger(__name__)

class NodeExporter():
    """
    NodeExporter class provides an interface to help create
    Bookstack resources/nodes (pages, books, etc) and their relationships.

    Uses Bookstack API to get gather enough information to do so.

    Returns:
        NodeExporter instance to handle building shelve/book/chapter/page relations.
    """
    def __init__(self, api_urls: dict[str, str], http_client: HttpHelper,
                 node_filter: Optional[NodeFilter] = None):
        self.api_urls = api_urls
        self.http_client = http_client
        self._node_filter = node_filter
        # Tracks book IDs belonging to dropped shelves; consumed in get_unassigned_books.
        # Populated in get_all_shelves, pruned in get_all_books before unassigned check.
        self._excluded_book_ids: set[int] = set()

    def get_all_shelves(self) -> dict[int, Node]:
        """
        Function to get all shelf Node instances.
        When a node_filter is configured, shelves not matching the filter are dropped
        and their child book IDs are recorded in _excluded_book_ids for cascade suppression.
        :returns: Dict[int, Node] for all surviving shelf nodes
        """
        base_url = self.api_urls["shelves"]
        all_parents: list[int] = self._get_all_ids(base_url)
        if not all_parents:
            log.warning("No shelves found in given Bookstack instance")
            return {}
        # Fetch every shelf detail regardless of filter (shelf detail contains the book
        # IDs needed for cascade suppression — those IDs are not in the list summary).
        all_shelf_nodes = self._get_parents(base_url, all_parents)
        if self._node_filter is None:
            return all_shelf_nodes
        surviving = {}
        for shelf_id, shelf_node in all_shelf_nodes.items():
            if self._node_filter.keep(shelf_node.display_name, "shelves"):
                surviving[shelf_id] = shelf_node
            else:
                log.debug("Shelf '%s' excluded by filter; suppressing its books",
                          shelf_node.display_name)
                # Record the child book IDs so they don't resurface as unassigned.
                for book_entry in shelf_node.children:
                    self._excluded_book_ids.add(book_entry['id'])
        return surviving

    def _get_json_response(self, url: str) -> list[dict[str, str |int]]:
        """get http response data in json format"""
        response: Response = self.http_client.http_get_request(url=url)
        return response.json()

    def _get_all_ids(self, url: str) -> list[int]:
        return [item['id'] for item in self.http_client.http_get_all(url)]

    def _get_parents(self, base_url: str, parent_ids: list[int],
                      path_prefix: str = "") -> dict[int, Node]:
        parent_nodes = {}
        for parent_id in parent_ids:
            parent_url = f"{base_url}/{parent_id}"
            parent_data = self._get_json_response(parent_url)
            parent_nodes[parent_id] = Node(parent_data, path_prefix=path_prefix)
        return parent_nodes

    def get_chapter_nodes(self, book_nodes: dict[int, Node]) -> dict[int, Node]:
        """build chapter nodes by walking each book's contents.

        When a node_filter is configured, chapters not matching the chapters patterns are
        skipped before their detail GET — their pages are also never fetched (cascade).
        """
        base_url = self.api_urls["chapters"]
        chapter_nodes = {}
        for book_node in book_nodes.values():
            for child in book_node.children:
                if child.get('type') != 'chapter':
                    continue
                if self._node_filter:
                    chapter_name = child['name']
                    if not self._node_filter.keep(chapter_name, "chapters"):
                        log.debug("Chapter '%s' excluded by filter", chapter_name)
                        continue
                chapter_id = child['id']
                chapter_data = self._get_json_response(f"{base_url}/{chapter_id}")
                chapter_nodes[chapter_id] = Node(chapter_data, book_node)
        return chapter_nodes

    def get_child_nodes(self, resource_type: str, parent_nodes: dict[int, Node],
                        filter_empty: bool = True, node_type: str = "") -> dict[int, Node]:
        """get child nodes from a book/chapter/shelf"""
        base_url = self.api_urls[resource_type]
        return self._get_children(base_url, resource_type, parent_nodes, filter_empty, node_type)

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def _get_children(self, base_url: str, resource_type: str, parent_nodes: dict[int, Node],
                      filter_empty: bool, node_type: str = "") -> dict[int, Node]:
        child_nodes = {}
        for _, parent in parent_nodes.items():
            if parent.children:
                for child in parent.children:
                    if node_type:
                        # only used for Book Nodes to get children Page/Chapter Nodes
                        # access key directly, don't create a Node if not needed
                        # chapters and pages always have `type` from what I can tell
                        if not child['type'] == node_type:
                            log.debug("Book Node child of type: %s is not desired type: %s",
                                       child['type'], node_type)
                            continue
                    # Pre-GET name filter: test child name before issuing the detail GET.
                    if self._node_filter:
                        child_name = child['name']
                        if not self._node_filter.keep(child_name, resource_type):
                            log.debug("'%s' (type=%s) excluded by filter",
                                      child_name, resource_type)
                            continue
                    child_id = child['id']
                    child_url = f"{base_url}/{child_id}"
                    child_data = self._get_json_response(child_url)
                    child_node = Node(child_data, parent)
                    if filter_empty:
                        # if it is not empty, add it
                        # skip it if empty
                        if not child_node.empty:
                            child_nodes[child_id] = child_node
                    else:
                        child_nodes[child_id] = child_node
        return child_nodes

    def get_unassigned_books(self, existing_books: dict[int, Node],
                              path_prefix: str) -> dict[int, Node]:
        """get books not under a shelf.

        Applies these gates before fetching each book detail:
          1. The book must not already be collected under a shelf (existing_books).
          2. The book ID must not be in _excluded_book_ids (books from dropped shelves).
          3. When a node_filter is set, the book name must pass the 'books' filter.
        """
        book_url = self.api_urls["books"]
        all_books: list[dict] = self.http_client.http_get_all(book_url)
        unassigned = []
        for book_item in all_books:
            book_id = book_item['id']
            if book_id in existing_books:
                continue
            if book_id in self._excluded_book_ids:
                log.debug("Book id=%d suppressed (its shelf was excluded)", book_id)
                continue
            # books-list summaries normally carry `name`; default defensively so
            # the unassigned path stays robust if a summary omits it.
            book_name = book_item.get('name', '')
            if self._node_filter and not self._node_filter.keep(book_name, "books"):
                log.debug("Unassigned book '%s' excluded by filter", book_name)
                continue
            unassigned.append(book_id)
        if not unassigned:
            return {}
        # books with no shelf treated like a parent resource
        return self._get_parents(book_url, unassigned, path_prefix)

    # convenience function
    def get_all_books(self, shelve_nodes: dict[int, Node], unassigned_dir: str) -> dict[int, Node]:
        """get all books"""
        book_nodes = {}
        # get books in shelves
        if shelve_nodes:
            book_nodes = self.get_child_nodes("books", shelve_nodes)
        # A book that appears on both a pruned shelf AND a surviving shelf was collected
        # via the survivor above — remove it from the suppression set so it is not
        # wrongly blocked in get_unassigned_books (it won't be unassigned anyway, but
        # the state must be consistent for the edge case where it truly is unassigned).
        self._excluded_book_ids -= set(book_nodes.keys())
        # books with no shelve assignment
        # default will be put in "unassigned" directory relative to backup dir
        if self._node_filter and self._node_filter.exclude_unassigned_books:
            books_no_shelf = {}
        else:
            books_no_shelf = self.get_unassigned_books(book_nodes, unassigned_dir)

        # add new book nodes to map
        # these should not already be present in map
        # since we started with shelves first and then moved our way down.
        if books_no_shelf:
            book_nodes.update(books_no_shelf)

        return book_nodes

    # convenience function
    def get_all_pages(self, book_nodes: dict[int, Node]) -> dict[int, Node]:
        """get all pages and their content"""
        ## pages
        page_nodes = {}
        if book_nodes:
            # add `page` flag, we only want pages
            # filter out chapters for now
            # chapters can have their own children/pages
            page_nodes: dict[int, Node] = self.get_child_nodes("pages",
                                                book_nodes, node_type="page")
        ## chapters (if exists)
        # chapter nodes are treated a little differently
        # chapters are children under books
        chapter_nodes: dict[int, Node] = self.get_chapter_nodes(book_nodes)
        # add chapter node pages
        # replace existing page node if found with proper chapter parent
        if chapter_nodes:
            page_chapter_nodes: dict[int, Node] = self.get_child_nodes("pages", chapter_nodes)
            ## since we filter empty, check if there is any content
            ## add all chapter pages to existing page nodes
            if page_chapter_nodes:
                page_nodes.update(page_chapter_nodes)
        return page_nodes
