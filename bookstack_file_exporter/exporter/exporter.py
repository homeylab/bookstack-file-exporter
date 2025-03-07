from typing import Dict, List, Union
import logging

# pylint: disable=import-error
from requests import Response

from bookstack_file_exporter.exporter.node import Node
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
    def __init__(self, api_urls: Dict[str, str], http_client: HttpHelper):
        self.api_urls = api_urls
        self.http_client = http_client

    def get_all_shelves(self) -> Dict[int, Node]:
        """
        Function to get all shelf Node instances 
        :returns: Dict[int, Node] for all shelf nodes
        """
        base_url = self.api_urls["shelves"]
        all_parents: List[int] = self._get_all_ids(base_url)
        if not all_parents:
            log.warning("No shelves found in given Bookstack instance")
            return {}
        return self._get_parents(base_url, all_parents)

    def _get_json_response(self, url: str) -> List[Dict[str, Union[str,int]]]:
        """get http response data in json format"""
        response: Response = self.http_client.http_get_request(url=url)
        return response.json()

    def _get_all_ids(self, url: str) -> List[int]:
        ids_api_meta = self._get_json_response(url)
        if ids_api_meta:
            return [item['id'] for item in ids_api_meta['data']]
        return []

    def _get_parents(self, base_url: str, parent_ids: List[int],
                      path_prefix: str = "") -> Dict[int, Node]:
        parent_nodes = {}
        for parent_id in parent_ids:
            parent_url = f"{base_url}/{parent_id}"
            parent_data = self._get_json_response(parent_url)
            parent_nodes[parent_id] = Node(parent_data, path_prefix=path_prefix)
        return parent_nodes

    def get_chapter_nodes(self, book_nodes: Dict[int, Node]) -> Dict[int, Node]:
        """ get chapter nodes """
        # Chapters are treated a little differently
        # They are under books like pages but have their own children
        # i.e. not a terminal node
        base_url = self.api_urls["chapters"]
        all_chapters: List[int] = self._get_all_ids(base_url)
        if not all_chapters:
            log.debug("No chapters found in given Bookstack instance")
            return {}
        return self._get_chapters(base_url, all_chapters, book_nodes)

    def _get_chapters(self, base_url: str, all_chapters: List[int],
                       book_nodes: Dict[int, Node]) -> Dict[int, Node]:
        chapter_nodes = {}
        for chapter_id in all_chapters:
            chapter_url = f"{base_url}/{chapter_id}"
            chapter_data = self._get_json_response(chapter_url)
            book_id = chapter_data['book_id']
            chapter_nodes[chapter_id] = Node(chapter_data, book_nodes[book_id])
        return chapter_nodes

    def get_child_nodes(self, resource_type: str, parent_nodes: Dict[int, Node],
                        filter_empty: bool = True, node_type: str = "") -> Dict[int, Node]:
        """get child nodes from a book/chapter/shelf"""
        base_url = self.api_urls[resource_type]
        return self._get_children(base_url, parent_nodes, filter_empty, node_type)

    def _get_children(self, base_url: str, parent_nodes: Dict[int, Node],
                       filter_empty: bool, node_type: str = "") -> Dict[int, Node]:
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

    def get_unassigned_books(self, existing_books: Dict[int, Node],
                              path_prefix: str) -> Dict[int, Node]:
        """get books not under a shelf"""
        book_url = self.api_urls["books"]
        all_books: List[int] = self._get_all_ids(book_url)
        unassigned = []
        # get all existing ones and compare against current known books
        for book in all_books:
            if book not in existing_books:
                unassigned.append(book)
        if not unassigned:
            return {}
        # books with no shelf treated like a parent resource
        return self._get_parents(book_url, unassigned, path_prefix)

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
            # add `page` flag, we only want pages
            # filter out chapters for now
            # chapters can have their own children/pages
            page_nodes: Dict[int, Node] = self.get_child_nodes("pages",
                                                book_nodes, node_type="page")
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
