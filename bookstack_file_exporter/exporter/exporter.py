from typing import Dict, List, Union

import bookstack_file_exporter.exporter.util as util
from bookstack_file_exporter.exporter.node import Node


# _API_SUFFIX_PATHS = {
#     "shelves": "api/shelves",
#     "books": "api/books",
#     "chapters": "api/chapters",
#     "pages": "api/pages"
# }

class NodeExporter():
    """
    NodeExporter class provides an interface to help create Bookstack resources/nodes (pages, books, etc) and their relationships.

    Raises:

    ValueError if data returned from bookstack api is empty or not in desired format.
    """
    def __init__(self, api_urls: Dict[str, str], headers: Dict[str,str]):
        self.api_urls = api_urls
        self.headers = headers

    def get_shelf_nodes(self) -> Dict[int, Node]:
        """
        Function to get all shelf Node instances 
        :returns: Dict[int, Node] for all shelf nodes
        """
        base_url = self.api_urls["shelves"]
        all_parents: List[int] = util.get_all_ids(base_url, self.headers)
        if not all_parents:
            raise ValueError(f"No resources returned from Bookstack api url: {base_url}")
        return self._get_parents(base_url, all_parents)
        
    def _get_parents(self, base_url: str, parent_ids: List[int], path_prefix: str = "") -> Dict[int, Node]:
        parent_nodes = {}
        for parent_id in parent_ids:
            parent_url = f"{base_url}/{parent_id}"
            parent_data = util.get_json_response(url=parent_url, headers=self.headers)
            parent_nodes[parent_id] = Node(parent_data, path_prefix=path_prefix)
        return parent_nodes
    
    def get_chapter_nodes(self, book_nodes: Dict[int, Node]):
        # Chapters are treated a little differently
        # They are under books like pages but have their own children
        # i.e. not a terminal node
        base_url = self.api_urls["chapters"]
        all_chapters: List[int] = util.get_all_ids(base_url, self.headers)
        if not all_chapters:
            raise ValueError(f"No resources returned from Bookstack api url: {base_url}")
        return self._get_chapters(base_url, all_chapters, book_nodes)

    def _get_chapters(self, base_url: str, all_chapters: List[int], book_nodes: Dict[int, Node]):
        chapter_nodes = {}
        for chapter_id in all_chapters:
            chapter_url = f"{base_url}/{chapter_id}"
            chapter_data = util.get_json_response(url=chapter_url, headers=self.headers)
            book_id = chapter_data['book_id']
            chapter_nodes[chapter_id] = Node(chapter_data, book_nodes[book_id])
        return chapter_nodes
    
    def get_child_nodes(self, resource_type: str, parent_nodes: Dict[int, Node], filter_empty: bool = True):
        base_url = self.api_urls[resource_type]
        return self._get_children(base_url, parent_nodes, filter_empty)

    def _get_children(self, base_url: str, parent_nodes: Dict[int, Node], filter_empty: bool):
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

    def get_unassigned_books(self, existing_resources: Dict[int, Node], path_prefix: str) -> Dict[int, Node]:
        base_url = self.api_urls["books"]
        all_resources: List[int] = util.get_all_ids(url=base_url, headers=self.headers)
        unassigned = []
        # get all existing ones and compare against current known resources
        for resource_id in all_resources:
            if resource_id not in existing_resources:
                unassigned.append(resource_id)
        if not unassigned:
            raise ValueError(f"No unassigned resources found for type: {base_url}")
        # books with no shelf treated like a parent resource
        return self._get_parents(base_url, unassigned, path_prefix)