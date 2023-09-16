from typing import Dict, Union, List

# shelves --> 'books'
# books --> 'content'
# chapters --> 'pages'
_CHILD_KEYS = ['books', 'contents', 'pages']

_NULL_PAGE_NAME = "New Page"

class Node():
    def __init__(self, meta: Dict[str, Union[str, int]], parent: Union['Node', None] = None, path_prefix: Union[str, None] = ""):
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
        # get base file path from parent
        if self.__parent:
            self._file_path = self.__parent.file_path + '/' + self.name
        # normalize path prefix if it does not exist
        if not self._path_prefix:
            self._path_prefix = ""
        # check for children
        self._get_children()
        # check empty
        self._check_empty()
    
    def _get_children(self):
        # find first match
        for match in _CHILD_KEYS:
            if match in self.meta:
                self._children = self.meta[match]
                break
    
    def _check_empty(self):
        if not self.name and self._display_name == _NULL_PAGE_NAME:
            self._is_empty = True
    
    @property
    def file_path(self):
        if not self._file_path:
            return self._path_prefix + self.name
        return self._path_prefix + self._file_path

    @property
    def children(self):
        return self._children
    
    @property
    def empty(self):
        return self._is_empty