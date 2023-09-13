from typing import Dict, Union, List

# books for shelves
# contents for books
CHILD_KEYS = ['books', 'contents']

class Node():
    def __init__(self, meta: Dict[str, Union[str, int]], parent: Union['Node', None] = None):
        self.meta = meta
        self.__parent = parent
        self._children: Union[List[Dict[str, Union[str, int]]], None] = None
        self._file_path = ""
        self._name = ""
        self._initialize()
    
    def _initialize(self):
        # for convenience
        self._name = self.meta['slug']
        # get base file path from parent
        if self.__parent:
            self._file_path = self.__parent.file_path + '/' + self._name
        # check for children
        self._get_children()
    
    def _get_children(self):
        # find first match
        for match in CHILD_KEYS:
            if match in self.meta:
                self._children = self.meta[match]
                break
    
    @property
    def file_path(self):
        if not self._file_path:
            return self._name
        return self._file_path

    @property
    def children(self):
        return self._children