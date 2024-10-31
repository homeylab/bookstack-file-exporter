from typing import Dict, Union, List
import unicodedata
from re import sub as re_sub

# shelves --> 'books'
# books --> 'content'
# chapters --> 'pages'
_CHILD_KEYS = ['books', 'contents', 'pages']

_NULL_PAGE_NAME = "New Page"

# pylint: disable=too-many-instance-attributes
class Node():
    """
    Node class provides an interface to create bookstack child/parent 
    relationships for resources like pages, books, chapters, and shelves.

    Args:
        metadata: Dict[str, Union[str, int]] (required) 
        = The metadata of the resource from bookstack api
        parent: Union['Node', None] (optional) 
        = The parent resource if any, parent/children are also of the same class 'Node'.
        path_prefix: Union[str, None] (optional) 
        = This appends a relative 'root' directory to the child resource path/file_name. 
            It is mainly used to prepend a shelve level 
            directory for books that are not assigned or under any shelf.

    Returns:
        Node instance to help create and reference bookstack child/parent 
        relationships for resources like pages, books, chapters, and shelves.

    """
    def __init__(self, meta: Dict[str, Union[str, int]],
                 parent: Union['Node', None] = None, path_prefix: str = ""):
        self.meta = meta
        self._parent = parent
        self._path_prefix = path_prefix
        # for convenience/usage for exporter
        # self.name: str = self.meta['slug']
        self.name = self.get_name(self.meta['slug'], self.meta['name'])
        # id() is a built-in function and should not be used as a variable name
        self.id_: int = self.meta['id']
        self._display_name = self.meta['name']
        # children
        self._children = self._get_children()
        # if parent
        self._file_path = self._get_file_path()

    def get_name(self, slug: str, name: str) -> str:
        """return name of resource"""
        if slug:
            return slug
        if name != _NULL_PAGE_NAME:
            return self.slugify(name)
        return ""

    def _get_file_path(self) -> str:
        if self._parent:
            # page node
            # if not self._children:
            #     return f"{self._parent.file_path}/{self.name}/{self.name}"
            return f"{self._parent.file_path}/{self.name}"
        return ""

    def _get_children(self) -> List[Dict[str, Union[str, int]]]:
        children = []
        # find first match
        for match in _CHILD_KEYS:
            if match in self.meta:
                children = self.meta[match]
                break
        return children

    @property
    def file_path(self):
        """get the base file path"""
        # check to see if parent exists
        if not self._file_path:
            # return base path + name if no parent
            return f"{self._path_prefix}{self.name}"
        # if parent exists
        # return the combined path
        return f"{self._path_prefix}{self._file_path}"

    @property
    def children(self):
        """return all children of a book/chapter/shelf"""
        return self._children

    @property
    def parent(self):
        """return parent of a book/chapter/page"""
        return self._parent

    @property
    def empty(self):
        """return True if page node lacks content"""
        if not self.name and self._display_name == _NULL_PAGE_NAME:
            return True
        return False

    @staticmethod
    def slugify(value: str, allow_unicode=False):
        """
        Taken from https://github.com/django/django/blob/master/django/utils/text.py
        Convert to ASCII if 'allow_unicode' is False. Convert spaces or repeated
        dashes to single dashes. Remove characters that aren't alphanumerics,
        underscores, or hyphens. Convert to lowercase. Also strip leading and
        trailing whitespace, dashes, and underscores.
        """
        if allow_unicode:
            value = unicodedata.normalize("NFKC", value)
        else:
            value = (
                unicodedata.normalize("NFKD", value)
                .encode("ascii", "ignore")
                .decode("ascii")
            )
        value = re_sub(r"[^\w\s-]", "", value.lower())
        return re_sub(r"[-\s]+", "-", value).strip("-_")
