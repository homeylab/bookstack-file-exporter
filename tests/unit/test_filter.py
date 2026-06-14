# pylint: disable=missing-class-docstring,missing-function-docstring
"""Unit tests for NodeFilter (exporter/filter.py) — pure logic, no I/O."""
import pytest

from bookstack_file_exporter.exporter.filter import NodeFilter
from bookstack_file_exporter.config_helper.models import Filters, ResourceFilter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_filter(**kwargs) -> NodeFilter:
    """Build a NodeFilter from keyword-arg Filters fields.

    E.g.: _make_filter(books=ResourceFilter(exclude=["draft"]))
    """
    return NodeFilter(Filters(**kwargs))


# ---------------------------------------------------------------------------
# No-op: empty / omitted config → keep all
# ---------------------------------------------------------------------------

class TestNoOpFilter:
    def test_none_filters_keeps_everything(self):
        nf = NodeFilter(None)
        assert nf.keep("anything", "books") is True

    def test_empty_filters_object_keeps_everything(self):
        nf = NodeFilter(Filters())
        assert nf.keep("anything", "books") is True

    def test_empty_include_list_keeps_everything(self):
        nf = _make_filter(books=ResourceFilter(include=[]))
        assert nf.keep("draft", "books") is True

    def test_none_include_keeps_everything(self):
        nf = _make_filter(books=ResourceFilter(include=None))
        assert nf.keep("anything", "books") is True

    def test_unknown_resource_type_keeps(self):
        nf = _make_filter(books=ResourceFilter(exclude=["draft"]))
        assert nf.keep("draft", "shelves") is True

    def test_unregistered_type_always_keeps(self):
        """A type with no filter configured is always kept."""
        nf = _make_filter(books=ResourceFilter(exclude=["x"]))
        assert nf.keep("x", "pages") is True


# ---------------------------------------------------------------------------
# fullmatch semantics
# ---------------------------------------------------------------------------

class TestFullmatchSemantics:
    def test_exact_pattern_matches_exact_name(self):
        nf = _make_filter(books=ResourceFilter(exclude=["draft"]))
        assert nf.keep("draft", "books") is False

    def test_exact_pattern_does_not_match_prefix(self):
        """["draft"] must NOT drop "draft-api" — fullmatch not search."""
        nf = _make_filter(books=ResourceFilter(exclude=["draft"]))
        assert nf.keep("draft-api", "books") is True

    def test_wildcard_pattern_matches_prefix(self):
        nf = _make_filter(books=ResourceFilter(exclude=["draft.*"]))
        assert nf.keep("draft-api", "books") is False

    def test_wildcard_contains_pattern_matches_both(self):
        """[".*draft.*"] matches both "draft" and "draft-api" and "old-draft"."""
        nf = _make_filter(books=ResourceFilter(exclude=[".*draft.*"]))
        assert nf.keep("draft", "books") is False
        assert nf.keep("draft-api", "books") is False
        assert nf.keep("old-draft", "books") is False

    def test_wildcard_contains_pattern_does_not_match_unrelated(self):
        nf = _make_filter(books=ResourceFilter(exclude=[".*draft.*"]))
        assert nf.keep("runbooks", "books") is True


# ---------------------------------------------------------------------------
# Include-only
# ---------------------------------------------------------------------------

class TestIncludeOnly:
    def test_include_allows_matching_name(self):
        nf = _make_filter(books=ResourceFilter(include=["eng-.*"]))
        assert nf.keep("eng-runbooks", "books") is True

    def test_include_drops_non_matching_name(self):
        nf = _make_filter(books=ResourceFilter(include=["eng-.*"]))
        assert nf.keep("draft", "books") is False

    def test_include_multiple_patterns_any_match_survives(self):
        nf = _make_filter(pages=ResourceFilter(include=["secret", "archive"]))
        assert nf.keep("secret", "pages") is True
        assert nf.keep("archive", "pages") is True
        assert nf.keep("public", "pages") is False


# ---------------------------------------------------------------------------
# Exclude-only
# ---------------------------------------------------------------------------

class TestExcludeOnly:
    def test_exclude_drops_matching_name(self):
        nf = _make_filter(pages=ResourceFilter(exclude=["secret", "scratch"]))
        assert nf.keep("secret", "pages") is False
        assert nf.keep("scratch", "pages") is False

    def test_exclude_keeps_non_matching_name(self):
        nf = _make_filter(pages=ResourceFilter(exclude=["secret", "scratch"]))
        assert nf.keep("public", "pages") is True


# ---------------------------------------------------------------------------
# Include + Exclude (exclude wins on conflict)
# ---------------------------------------------------------------------------

class TestIncludeAndExclude:
    def test_include_and_no_exclude_match_keeps(self):
        nf = _make_filter(books=ResourceFilter(include=["eng-.*"], exclude=["draft"]))
        assert nf.keep("eng-runbooks", "books") is True

    def test_exclude_wins_over_include_on_same_name(self):
        """Name matches both include and exclude → dropped (exclude wins)."""
        nf = _make_filter(books=ResourceFilter(include=["draft.*"], exclude=["draft"]))
        assert nf.keep("draft", "books") is False

    def test_include_miss_drops_even_without_exclude_match(self):
        nf = _make_filter(books=ResourceFilter(include=["eng-.*"], exclude=["draft"]))
        assert nf.keep("archive", "books") is False

    def test_include_match_excluded_name_dropped(self):
        """Wildcard include matches but exclude also matches → drop."""
        nf = _make_filter(
            chapters=ResourceFilter(include=[".*"], exclude=["scratch"])
        )
        assert nf.keep("scratch", "chapters") is False
        assert nf.keep("intro", "chapters") is True


# ---------------------------------------------------------------------------
# Per-type isolation
# ---------------------------------------------------------------------------

class TestPerTypeIsolation:
    def test_books_pattern_does_not_affect_pages(self):
        nf = _make_filter(books=ResourceFilter(exclude=["draft"]))
        assert nf.keep("draft", "pages") is True

    def test_pages_pattern_does_not_affect_books(self):
        nf = _make_filter(pages=ResourceFilter(exclude=["secret"]))
        assert nf.keep("secret", "books") is True

    def test_shelves_pattern_does_not_affect_chapters(self):
        nf = _make_filter(shelves=ResourceFilter(exclude=["archive"]))
        assert nf.keep("archive", "chapters") is True

    def test_chapters_pattern_does_not_affect_shelves(self):
        nf = _make_filter(chapters=ResourceFilter(exclude=["scratch"]))
        assert nf.keep("scratch", "shelves") is True

    def test_multiple_types_independent(self):
        nf = NodeFilter(Filters(
            books=ResourceFilter(include=["eng-.*"]),
            pages=ResourceFilter(exclude=["secret"]),
        ))
        # books filter
        assert nf.keep("eng-api", "books") is True
        assert nf.keep("archive", "books") is False
        # pages filter
        assert nf.keep("secret", "pages") is False
        assert nf.keep("public", "pages") is True
        # chapters: no filter → keep all
        assert nf.keep("anything", "chapters") is True
