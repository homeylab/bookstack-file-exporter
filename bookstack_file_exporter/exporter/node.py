from typing import Dict, Union, List

# shelves --> 'books'
# books --> 'content'
# chapters --> 'pages'
_CHILD_KEYS = ['books', 'contents', 'pages']

_NULL_PAGE_NAME = "New Page"

class Node():
    """
    Node class provides an interface to create and reference bookstack child/parent relationships for resources like pages, books, chapters, and shelves.

    Args:
        metadata: Dict[str, Union[str, int]] (required) = The metadata of the resource from bookstack api
        parent: Union['Node', None] (optional) = The parent resource if any, parent/children are also of the same class 'Node'.
        path_prefix: Union[str, None] (optional) = This appends a relative 'root' directory to the child resource path/file_name. 
            It is mainly used to prepend a shelve level directory for books that are not assigned or under any shelf.

    Returns:
        Node instance to help create and reference bookstack child/parent relationships for resources like pages, books, chapters, and shelves.

    """
    def __init__(self, meta: Dict[str, Union[str, int]], parent: Union['Node', None] = None, path_prefix: Union[str, None] = None):
        self.meta = meta
        self.__parent = parent
        self._path_prefix = path_prefix
        self.name: str = ""
        self.id: int = 0
        self._children: Union[List[Dict[str, Union[str, int]]], None] = None
        self._file_path = ""
        self._display_name = ""
        self._is_empty = False
        self._initialize()
    
    def _initialize(self):
        # for convenience/usage for exporter
        self.name = self.meta['slug']
        self.id = self.meta['id']
        self._display_name = self.meta['name']
        # get base file path from parent if it exists
        if self.__parent:
            self._file_path = f"{self.__parent.file_path}/{self.name}"
            # self._file_path = self.__parent.file_path + '/' + self.name
        # normalize path prefix if it does not exist
        if not self._path_prefix:
            self._path_prefix = ""
        # check for children
        self._get_children()
        # check empty - pages that were created but never touched by any user
        self._check_empty()
    
    def _get_children(self):
        # find first match
        for match in _CHILD_KEYS:
            if match in self.meta:
                self._children = self.meta[match]
                break
    
    def _check_empty(self):
        # this is will tell us if page is empty
        if not self.name and self._display_name == _NULL_PAGE_NAME:
            self._is_empty = True
    
    @property
    def file_path(self):
        # check to see if parent exists
        if not self._file_path:
            # return base path + name if no parent
            return f"{self._path_prefix}{self.name}"
        # if parent exists
        # return the combined path
        return f"{self._path_prefix}{self._file_path}"

    @property
    def children(self):
        return self._children
    
    @property
    def empty(self):
        return self._is_empty