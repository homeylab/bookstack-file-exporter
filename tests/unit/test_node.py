"""Unit tests for the Node class."""
import pytest
from bookstack_file_exporter.exporter.node import Node


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_node(name="My Book", slug="my-book", id_=1, extra=None, **kwargs):
    meta = {"id": id_, "name": name, "slug": slug}
    if extra:
        meta.update(extra)
    return Node(meta, **kwargs)


# ---------------------------------------------------------------------------
# __init__ and basic properties
# ---------------------------------------------------------------------------

def test_init_id_stored():
    meta = {"id": 42, "name": "Test", "slug": "test"}
    node = Node(meta)
    assert node.id_ == 42


def test_init_name_uses_slug_when_present():
    meta = {"id": 1, "name": "Some Title", "slug": "some-title"}
    node = Node(meta)
    assert node.name == "some-title"


def test_init_display_name_is_raw_name():
    meta = {"id": 1, "name": "Some Title", "slug": "some-title"}
    node = Node(meta)
    assert node._display_name == "Some Title"


# ---------------------------------------------------------------------------
# get_name
# ---------------------------------------------------------------------------

def test_get_name_returns_slug_when_slug_present():
    meta = {"id": 1, "name": "Whatever", "slug": "my-slug"}
    node = Node(meta)
    assert node.name == "my-slug"


def test_get_name_slugifies_name_when_slug_empty():
    meta = {"id": 1, "name": "Hello World", "slug": ""}
    node = Node(meta)
    assert node.name == "hello-world"


def test_get_name_returns_empty_string_for_new_page_without_slug():
    meta = {"id": 1, "name": "New Page", "slug": ""}
    node = Node(meta)
    assert node.name == ""


def test_get_name_returns_slug_even_for_new_page_name():
    """A 'New Page' that actually has a slug should use the slug."""
    meta = {"id": 1, "name": "New Page", "slug": "new-page"}
    node = Node(meta)
    assert node.name == "new-page"


# ---------------------------------------------------------------------------
# slugify (static method)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("hello", "hello"),
    ("HelloWorld", "helloworld"),
    ("abc123", "abc123"),
])
def test_slugify_simple_alphanumeric(value, expected):
    assert Node.slugify(value) == expected


@pytest.mark.parametrize("value,expected", [
    ("hello world", "hello-world"),
    ("foo  bar", "foo-bar"),
    ("a b c", "a-b-c"),
])
def test_slugify_spaces_become_hyphens(value, expected):
    assert Node.slugify(value) == expected


@pytest.mark.parametrize("value,expected", [
    ("Hello, World!", "hello-world"),
    ("foo@bar.baz", "foobarbaz"),
    ("price: $9.99", "price-999"),
])
def test_slugify_special_chars_stripped(value, expected):
    assert Node.slugify(value) == expected


def test_slugify_leading_trailing_whitespace_stripped():
    assert Node.slugify("  hello  ") == "hello"


def test_slugify_leading_trailing_dashes_stripped():
    assert Node.slugify("---hello---") == "hello"


def test_slugify_unicode_stripped_when_allow_unicode_false():
    # NFKD decomposes é→e+combining, ö→o+combining; ASCII encode drops the
    # combining marks, leaving the base letters intact.
    result = Node.slugify("Héllo Wörld", allow_unicode=False)
    assert result == "hello-world"


def test_slugify_unicode_preserved_when_allow_unicode_true():
    result = Node.slugify("Héllo Wörld", allow_unicode=True)
    # unicode chars kept; lowercased
    assert "héllo" in result or "h" in result  # at minimum no crash
    assert result == "héllo-wörld"


# ---------------------------------------------------------------------------
# _get_children / children property
# ---------------------------------------------------------------------------

def test_children_returns_contents_for_book_style():
    pages = [{"id": 10, "name": "Page One", "slug": "page-one"}]
    meta = {"id": 1, "name": "Book", "slug": "book", "contents": pages}
    node = Node(meta)
    assert node.children == pages


def test_children_returns_books_for_shelf_style():
    books = [{"id": 20, "name": "Book One", "slug": "book-one"}]
    meta = {"id": 1, "name": "Shelf", "slug": "shelf", "books": books}
    node = Node(meta)
    assert node.children == books


def test_children_returns_pages_for_chapter_style():
    pages = [{"id": 30, "name": "Ch Page", "slug": "ch-page"}]
    meta = {"id": 1, "name": "Chapter", "slug": "chapter", "pages": pages}
    node = Node(meta)
    assert node.children == pages


def test_children_returns_empty_list_when_no_child_keys():
    meta = {"id": 1, "name": "Leaf", "slug": "leaf"}
    node = Node(meta)
    assert node.children == []


def test_children_prefers_books_over_contents_when_both_present():
    """_CHILD_KEYS order is ['books', 'contents', 'pages']; books wins."""
    books = [{"id": 2, "name": "B", "slug": "b"}]
    contents = [{"id": 3, "name": "C", "slug": "c"}]
    meta = {"id": 1, "name": "Multi", "slug": "multi", "books": books, "contents": contents}
    node = Node(meta)
    assert node.children == books


def test_children_prefers_books_over_pages_when_both_present():
    books = [{"id": 2, "name": "B", "slug": "b"}]
    pages = [{"id": 4, "name": "P", "slug": "p"}]
    meta = {"id": 1, "name": "Multi", "slug": "multi", "books": books, "pages": pages}
    node = Node(meta)
    assert node.children == books


def test_children_prefers_contents_over_pages_when_both_present():
    contents = [{"id": 3, "name": "C", "slug": "c"}]
    pages = [{"id": 4, "name": "P", "slug": "p"}]
    meta = {"id": 1, "name": "Multi", "slug": "multi", "contents": contents, "pages": pages}
    node = Node(meta)
    assert node.children == contents


# ---------------------------------------------------------------------------
# file_path property
# ---------------------------------------------------------------------------

def test_file_path_no_parent_no_prefix():
    meta = {"id": 1, "name": "Shelf", "slug": "my-shelf"}
    node = Node(meta)
    assert node.file_path == "my-shelf"


def test_file_path_no_parent_with_prefix():
    meta = {"id": 1, "name": "Shelf", "slug": "my-shelf"}
    node = Node(meta, path_prefix="root/")
    assert node.file_path == "root/my-shelf"


def test_file_path_with_parent_no_prefix():
    parent_meta = {"id": 1, "name": "Parent", "slug": "parent"}
    parent = Node(parent_meta)
    child_meta = {"id": 2, "name": "Child", "slug": "child"}
    child = Node(child_meta, parent=parent)
    assert child.file_path == "parent/child"


def test_file_path_with_parent_and_prefix():
    parent_meta = {"id": 1, "name": "Parent", "slug": "parent"}
    parent = Node(parent_meta)
    child_meta = {"id": 2, "name": "Child", "slug": "child"}
    child = Node(child_meta, parent=parent, path_prefix="root/")
    assert child.file_path == "root/parent/child"


def test_file_path_deep_nesting():
    grandparent_meta = {"id": 1, "name": "GP", "slug": "gp"}
    grandparent = Node(grandparent_meta)
    parent_meta = {"id": 2, "name": "Par", "slug": "par"}
    parent = Node(parent_meta, parent=grandparent)
    child_meta = {"id": 3, "name": "Kid", "slug": "kid"}
    child = Node(child_meta, parent=parent)
    assert child.file_path == "gp/par/kid"


# ---------------------------------------------------------------------------
# empty property
# ---------------------------------------------------------------------------

def test_empty_true_when_new_page_without_slug():
    meta = {"id": 1, "name": "New Page", "slug": ""}
    node = Node(meta)
    assert node.empty is True


def test_empty_false_for_normal_node():
    meta = {"id": 1, "name": "Real Book", "slug": "real-book"}
    node = Node(meta)
    assert node.empty is False


def test_empty_false_when_no_slug_but_not_new_page():
    meta = {"id": 1, "name": "Some Title", "slug": ""}
    node = Node(meta)
    assert node.empty is False


def test_empty_false_when_slug_present_even_for_new_page_display_name():
    meta = {"id": 1, "name": "New Page", "slug": "new-page"}
    node = Node(meta)
    assert node.empty is False


# ---------------------------------------------------------------------------
# parent and children properties
# ---------------------------------------------------------------------------

def test_parent_property_returns_set_parent():
    parent_meta = {"id": 1, "name": "P", "slug": "p"}
    parent = Node(parent_meta)
    child_meta = {"id": 2, "name": "C", "slug": "c"}
    child = Node(child_meta, parent=parent)
    assert child.parent is parent


def test_parent_property_none_by_default():
    meta = {"id": 1, "name": "Root", "slug": "root"}
    node = Node(meta)
    assert node.parent is None


def test_children_property_returns_list():
    books = [{"id": 5, "name": "B", "slug": "b"}]
    meta = {"id": 1, "name": "Shelf", "slug": "shelf", "books": books}
    node = Node(meta)
    assert node.children is node._children
    assert node.children == books
