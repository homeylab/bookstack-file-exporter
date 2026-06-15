"""Node name filter backed by compiled regex patterns.

Pure logic — no I/O. NodeFilter is constructed once per export run and
consulted for each candidate node before the detail GET is issued.
"""
import re

from bookstack_file_exporter.config_helper.models import Filters, ResourceFilter


# pylint: disable=too-few-public-methods
class NodeFilter:
    """Apply per-type include/exclude regex patterns to resource names.

    Precedence (per node):
      1. If include list is non-empty, name must fullmatch >=1 pattern to survive.
      2. If name fullmatches any exclude pattern, drop it (exclude wins).

    Unknown resource types (no filter configured) always pass through.
    """

    # Filterable resource types; each matches a field of the same name on Filters.
    _RESOURCE_TYPES = ("shelves", "books", "chapters", "pages")

    def __init__(self, filters: Filters | None) -> None:
        # Compile patterns once per resource type.
        # _include and _exclude map resource_type → list[re.Pattern] | None.
        # None means "no filter configured" (always keep / no gate).
        # Empty list means "empty gate" — for include that means keep-all;
        # for exclude that means no patterns to match.
        self._include: dict[str, list[re.Pattern] | None] = {}
        self._exclude: dict[str, list[re.Pattern] | None] = {}
        self._exclude_unassigned_books = bool(filters and filters.exclude_unassigned_books)

        if filters is None:
            return

        for resource_type in self._RESOURCE_TYPES:
            rf: ResourceFilter | None = getattr(filters, resource_type)
            if rf is None:
                self._include[resource_type] = None
                self._exclude[resource_type] = None
            else:
                self._include[resource_type] = (
                    [re.compile(p) for p in rf.include] if rf.include else []
                )
                self._exclude[resource_type] = (
                    [re.compile(p) for p in rf.exclude] if rf.exclude else []
                )

    def keep(self, name: str, resource_type: str) -> bool:
        """Return True if the named resource should be exported.

        Parameters
        ----------
        name:
            The display name of the resource (``meta['name']``).
        resource_type:
            One of ``"shelves"``, ``"books"``, ``"chapters"``, ``"pages"``.
            An unrecognised / unfiltered type always returns ``True``.
        """
        include_patterns = self._include.get(resource_type)
        exclude_patterns = self._exclude.get(resource_type)

        # No filter configured for this type → always keep.
        if include_patterns is None and exclude_patterns is None:
            return True

        # Include gate: non-empty list → name must match at least one pattern.
        if include_patterns:
            if not any(p.fullmatch(name) for p in include_patterns):
                return False

        # Exclude gate: any match → drop (exclude wins).
        if exclude_patterns and any(p.fullmatch(name) for p in exclude_patterns):
            return False

        return True

    @property
    def exclude_unassigned_books(self) -> bool:
        """When True, drop all shelfless books regardless of name filters."""
        return self._exclude_unassigned_books
