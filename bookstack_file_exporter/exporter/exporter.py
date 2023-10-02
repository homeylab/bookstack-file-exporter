from typing import Dict, List
import logging

from bookstack_file_exporter.exporter import util
from bookstack_file_exporter.exporter.node import Node

log = logging.getLogger(__name__)

class NodeExporter():
    """
    NodeExporter class provides an interface to help create 
    Bookstack resources/nodes (pages, books, etc) and their relationships.

    Raises:

    ValueError if data returned from bookstack api is empty or not in desired format.
    """
    def __init__(self, api_urls: Dict[str, str], headers: Dict[str,str]):
        self.api_urls = api_urls
        self.headers = headers

    def get_all_shelves(self) -> Dict[int, Node]:
        """
        Function to get all shelf Node instances 
        :returns: Dict[int, Node] for all shelf nodes
        """
        base_url = self.api_urls["shelves"]
        all_parents: List[int] = util.get_all_ids(base_url, self.headers)
        if not all_parents:
            log.warning("No shelves found in given Bookstack instance")
            return {}
        return self._get_parents(base_url, all_parents)

    def _get_parents(self, base_url: str, parent_ids: List[int],
                      path_prefix: str = "") -> Dict[int, Node]:
        parent_nodes = {}
        for parent_id in parent_ids:
            parent_url = f"{base_url}/{parent_id}"
            parent_data = util.get_json_response(url=parent_url, headers=self.headers)
            parent_nodes[parent_id] = Node(parent_data, path_prefix=path_prefix)
        return parent_nodes

    def get_chapter_nodes(self, book_nodes: Dict[int, Node]) -> Dict[int, Node]:
        """ get chapter nodes """
        # Chapters are treated a little differently
        # They are under books like pages but have their own children
        # i.e. not a terminal node
        base_url = self.api_urls["chapters"]
        all_chapters: List[int] = util.get_all_ids(base_url, self.headers)
        if not all_chapters:
            log.debug("No chapters found in given Bookstack instance")
            return {}
        return self._get_chapters(base_url, all_chapters, book_nodes)

    def _get_chapters(self, base_url: str, all_chapters: List[int],
                       book_nodes: Dict[int, Node]) -> Dict[int, Node]:
        chapter_nodes = {}
        for chapter_id in all_chapters:
            chapter_url = f"{base_url}/{chapter_id}"
            chapter_data = util.get_json_response(url=chapter_url, headers=self.headers)
            book_id = chapter_data['book_id']
            chapter_nodes[chapter_id] = Node(chapter_data, book_nodes[book_id])
        return chapter_nodes

    def get_child_nodes(self, resource_type: str, parent_nodes: Dict[int, Node],
                        filter_empty: bool = True) -> Dict[int, Node]:
        """get child nodes from a book/chapter/shelf"""
        base_url = self.api_urls[resource_type]
        return self._get_children(base_url, parent_nodes, filter_empty)

    def _get_children(self, base_url: str, parent_nodes: Dict[int, Node],
                       filter_empty: bool) -> Dict[int, Node]:
        child_nodes = {}
        for _, parent in parent_nodes.items():
            if parent.children:
                for child in parent.children:
                    child_id = child['id']
                    child_url = f"{base_url}/{child_id}"
                    child_data = util.get_json_response(url=child_url, headers=self.headers)
                    child_node = Node(child_data, parent)
                    if filter_empty:
                        if not child_node.empty:
                            child_nodes[child_id] = child_node
                    else:
                        child_nodes[child_id] = child_node
        return child_nodes

    def get_unassigned_books(self, existing_resources: Dict[int, Node],
                              path_prefix: str) -> Dict[int, Node]:
        """get books not under a shelf"""
        base_url = self.api_urls["books"]
        all_resources: List[int] = util.get_all_ids(url=base_url, headers=self.headers)
        unassigned = []
        # get all existing ones and compare against current known resources
        for resource_id in all_resources:
            if resource_id not in existing_resources:
                unassigned.append(resource_id)
        if not unassigned:
            return {}
        # books with no shelf treated like a parent resource
        return self._get_parents(base_url, unassigned, path_prefix)

    # convenience function
    def get_all_books(self, shelve_nodes: Dict[int, Node], unassigned_dir: str) -> Dict[int, Node]:
        """get all books"""
        book_nodes = {}
        # get books in shelves
        if shelve_nodes:
            book_nodes = self.get_child_nodes("books", shelve_nodes)
        # books with no shelve assignment
        # default will be put in "unassigned" directory relative to backup dir
        books_no_shelf = self.get_unassigned_books(book_nodes, unassigned_dir)

        # add new book nodes to map
        # these should not already be present in map
        # since we started with shelves first and then moved our way down.
        if books_no_shelf:
            for key, value in books_no_shelf.items():
                book_nodes[key] = value

        return book_nodes

    # convenience function
    def get_all_pages(self, book_nodes: Dict[int, Node]) -> Dict[int, Node]:
        """get all pages and their content"""
        ## pages
        page_nodes = {}
        if book_nodes:
            page_nodes: Dict[int, Node] = self.get_child_nodes("pages", book_nodes)
        ## chapters (if exists)
        # chapter nodes are treated a little differently
        # chapters are children under books
        chapter_nodes: Dict[int, Node] = self.get_chapter_nodes(book_nodes)
        # add chapter node pages
        # replace existing page node if found with proper chapter parent
        if chapter_nodes:
            page_chapter_nodes: Dict[int, Node] = self.get_child_nodes("pages", chapter_nodes)
            ## since we filter empty, check if there is any content
            ## add all chapter pages to existing page nodes
            if page_chapter_nodes:
                for key, value in page_chapter_nodes.items():
                    page_nodes[key] = value
        return page_nodes
        