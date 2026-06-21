# pylint: disable=missing-class-docstring,missing-function-docstring
"""Unit tests for ResourceFilter and Filters config validation in models.py."""
import pytest
from pydantic import ValidationError

from bookstack_file_exporter.config_helper.models import (
    Filters,
    ResourceFilter,
    UserInput,
)


# ---------------------------------------------------------------------------
# ResourceFilter: valid inputs
# ---------------------------------------------------------------------------

class TestResourceFilterValid:
    def test_both_none_is_valid(self):
        rf = ResourceFilter()
        assert rf.include is None
        assert rf.exclude is None

    def test_valid_regex_patterns_accepted(self):
        rf = ResourceFilter(include=["eng-.*", "archive"], exclude=["draft", ".*secret.*"])
        assert rf.include == ["eng-.*", "archive"]
        assert rf.exclude == ["draft", ".*secret.*"]

    def test_empty_list_accepted(self):
        rf = ResourceFilter(include=[], exclude=[])
        assert not rf.include
        assert not rf.exclude

    def test_single_pattern_accepted(self):
        rf = ResourceFilter(include=["draft"])
        assert rf.include == ["draft"]


# ---------------------------------------------------------------------------
# ResourceFilter: invalid regex rejected
# ---------------------------------------------------------------------------

class TestResourceFilterInvalidRegex:
    def test_invalid_regex_in_include_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            ResourceFilter(include=["[invalid"])
        assert "[invalid" in str(exc_info.value)

    def test_invalid_regex_in_exclude_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            ResourceFilter(exclude=["(unclosed"])
        assert "(unclosed" in str(exc_info.value)

    def test_invalid_regex_error_names_pattern(self):
        """Error message must name the offending pattern."""
        bad_pattern = "(?P<bad"
        with pytest.raises(ValidationError) as exc_info:
            ResourceFilter(include=[bad_pattern])
        assert bad_pattern in str(exc_info.value)


# ---------------------------------------------------------------------------
# ResourceFilter: empty string rejected
# ---------------------------------------------------------------------------

class TestResourceFilterEmptyString:
    def test_empty_string_in_include_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            ResourceFilter(include=[""])
        assert '""' in str(exc_info.value) or "empty" in str(exc_info.value).lower()

    def test_empty_string_in_exclude_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            ResourceFilter(exclude=[""])
        assert '""' in str(exc_info.value) or "empty" in str(exc_info.value).lower()

    def test_empty_string_among_valid_patterns_raises(self):
        """Even one empty string in a list with valid patterns is rejected."""
        with pytest.raises(ValidationError):
            ResourceFilter(include=["valid-pattern", ""])


# ---------------------------------------------------------------------------
# Filters model
# ---------------------------------------------------------------------------

class TestFiltersModel:
    def test_all_none_is_valid(self):
        f = Filters()
        assert f.shelves is None
        assert f.books is None
        assert f.chapters is None
        assert f.pages is None

    def test_partial_population_leaves_others_none(self):
        f = Filters(books=ResourceFilter(exclude=["draft"]))
        assert f.books is not None
        assert f.shelves is None
        assert f.chapters is None
        assert f.pages is None

    def test_all_resource_types_populated(self):
        f = Filters(
            shelves=ResourceFilter(exclude=["Archive"]),
            books=ResourceFilter(include=["eng-.*"], exclude=["draft"]),
            chapters=ResourceFilter(exclude=[]),
            pages=ResourceFilter(exclude=["secret", "scratch"]),
        )
        assert f.shelves.exclude == ["Archive"]
        assert f.books.include == ["eng-.*"]
        assert f.chapters.exclude == []
        assert f.pages.exclude == ["secret", "scratch"]

    def test_invalid_regex_bubbles_through_filters(self):
        with pytest.raises(ValidationError):
            Filters(books=ResourceFilter(include=["[bad"]))

    def test_exclude_unassigned_books_defaults_to_false(self):
        f = Filters()
        assert f.exclude_unassigned_books is False

    def test_exclude_unassigned_books_true_is_accepted(self):
        f = Filters(exclude_unassigned_books=True)
        assert f.exclude_unassigned_books is True


# ---------------------------------------------------------------------------
# UserInput integration: filters field
# ---------------------------------------------------------------------------

def _base_user_input_kwargs(**overrides):
    base = {
        "host": "https://bookstack.example.com",
        "formats": ["markdown"],
    }
    base.update(overrides)
    return base


class TestUserInputFilters:
    def test_filters_defaults_to_none(self):
        ui = UserInput(**_base_user_input_kwargs())
        assert ui.filters is None

    def test_filters_accepts_none_explicitly(self):
        ui = UserInput(**_base_user_input_kwargs(filters=None))
        assert ui.filters is None

    def test_filters_accepts_valid_filters_object(self):
        f = Filters(books=ResourceFilter(exclude=["draft"]))
        ui = UserInput(**_base_user_input_kwargs(filters=f))
        assert ui.filters.books.exclude == ["draft"]

    def test_filters_accepts_dict_coercion(self):
        """Pydantic v2 coerces nested dicts to models."""
        ui = UserInput(**_base_user_input_kwargs(
            filters={"books": {"exclude": ["draft"]}}
        ))
        assert ui.filters.books.exclude == ["draft"]

    def test_filters_invalid_regex_raises_at_user_input_level(self):
        with pytest.raises(ValidationError):
            UserInput(**_base_user_input_kwargs(
                filters={"pages": {"include": ["[bad"]}}
            ))


# ---------------------------------------------------------------------------
# UserInput: run_schedule field and mutual-exclusion validator
# ---------------------------------------------------------------------------

class TestUserInputRunSchedule:
    def test_run_schedule_accepts_valid_cron(self):
        ui = UserInput(**_base_user_input_kwargs(run_schedule="0 2 * * *"))
        assert ui.run_schedule == "0 2 * * *"

    def test_run_schedule_rejects_invalid_cron(self):
        with pytest.raises(ValidationError):
            UserInput(**_base_user_input_kwargs(run_schedule="not a cron"))

    def test_run_interval_and_schedule_mutually_exclusive(self):
        with pytest.raises(ValidationError):
            UserInput(**_base_user_input_kwargs(run_interval=3600, run_schedule="0 2 * * *"))

    def test_run_interval_zero_with_schedule_ok(self):
        ui = UserInput(**_base_user_input_kwargs(run_interval=0, run_schedule="0 2 * * *"))
        assert ui.run_schedule == "0 2 * * *"
        assert ui.run_interval == 0

    def test_run_schedule_rejects_impossible_date(self):
        with pytest.raises(ValidationError):
            UserInput(**_base_user_input_kwargs(run_schedule="0 2 31 2 *"))
