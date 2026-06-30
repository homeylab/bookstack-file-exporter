# Filters

[← Back to README](../README.md#documentation)

- [Schema](#schema)
- [Pattern matching](#pattern-matching)
- [What the pattern matches](#what-the-pattern-matches)
- [Precedence](#precedence)
- [Cascade](#cascade)
- [Interaction with export\_level](#interaction-with-export_level)
- [Excluding books with no shelf](#excluding-books-with-no-shelf)
- [Validation](#validation)
  - [Known limitations](#known-limitations)


The `filters` configuration option lets you include or exclude BookStack resources (shelves, books, chapters, pages) by name during export. Filtering runs during the tree build, before the exporter issues any detail API call for a node — excluded books, chapters, and pages — and all descendants of any excluded node — are never fetched.

## Schema

All keys are optional. Omit a type entirely (or leave its lists empty/`[]`) to apply no filter for that type.

```yaml
filters:
  shelves:
    exclude: ["Archive"]            # drops the Archive shelf + everything under it
  books:
    include: ["eng-.*"]             # optional allow-list (fullmatch)
    exclude: ["draft"]
  chapters:
    exclude: []
  pages:
    exclude: ["secret", "scratch"]
  # structural toggle: drop every book that is not on a shelf
  exclude_unassigned_books: false
```

## Pattern matching

Patterns are Python [`re.fullmatch`](https://docs.python.org/3/library/re.html#re.fullmatch) — the **entire** display name must match. Substring matching is opt-in via `.*`:

| Pattern | Matches |
| ------- | ------- |
| `draft` | `draft` only |
| `draft.*` | `draft`, `draft-api` |
| `.*draft.*` | `draft`, `draft-api`, `old-draft` |

This means `exclude: ["draft"]` drops only the resource named exactly `draft`, not `draft-api` or `old-draft`. Add those names to the list (or use a pattern like `draft.*`) to drop them too.

Patterns are also **case-sensitive** by default — `windows` does not match a shelf named `Windows`. Prefix with the inline flag `(?i)` for case-insensitive matching:

| Pattern | Matches |
| ------- | ------- |
| `Windows` | `Windows` only |
| `(?i)windows` | `windows`, `Windows`, `WINDOWS` |
| `(?i).*windows.*` | any name containing `windows`, any case |

## What the pattern matches

Filters currently only match the resource's **display name** (the title shown in the BookStack UI), *not* the lowercased slug used for on-disk directory names. A shelf shown as `Windows` exports to a `windows/` directory, but the filter pattern must target `Windows` (or `(?i)windows`), not the `windows` directory name.

## Precedence

Per resource node:
1. If `include` is non-empty, the name must `fullmatch` at least one include pattern to survive.
2. If the name `fullmatch`es any `exclude` pattern, it is dropped — **exclude wins**.

Both conditions are evaluated against the bare display name of the node (not a path).

## Cascade

Excluding a shelf, book, or chapter prunes its entire subtree — children are never fetched or exported. For example, `shelves.exclude: ["Archive"]` suppresses the Archive shelf and all books, chapters, and pages beneath it with no additional configuration.

## Interaction with export_level

Filters are applied as the resource tree is built, which happens before [`export_level`](configuration.md#export-level) selects what to archive. Shelves and books are always built (books are the basis for every level), so their filters always apply. Chapter and page filters only take effect when the level builds those nodes:

| `export_level` | Filters applied |
| -------------- | --------------- |
| `books` | `shelves`, `books` |
| `chapters` | `shelves`, `books`, `chapters` |
| `pages` (default) | `shelves`, `books`, `chapters`, `pages` |

A filter for a type below the selected level is **silently ignored** — e.g. a `pages` filter has no effect when `export_level: books`. Cascade still works at every level: excluding a parent prunes its whole subtree.

## Excluding books with no shelf

A `shelves` filter only decides which shelves survive (and cascades to books *on* dropped shelves). A book on no shelf is an independent root and is **not** governed by the `shelves` filter. To drop such books, either name them with a `books` rule or set the structural toggle:

```yaml
filters:
  shelves:
    include: ["(?i)windows"]      # keep only the Windows shelf
  exclude_unassigned_books: true  # drop every book not on a shelf
```

`exclude_unassigned_books` is structural and takes precedence over `books` patterns: when `true`, every shelfless book is dropped even if it would match a `books.include` pattern. `books` filters then only affect books that live on a surviving shelf. The toggle is independent of `export_level` (it applies at all levels, since books are always built).

## Validation

All patterns are compiled with `re.compile` at config load time. An invalid regex or an empty string `""` pattern is rejected with a clear error message before any API call is made.

- [Schema](#schema)
- [Pattern matching](#pattern-matching)
- [What the pattern matches](#what-the-pattern-matches)
- [Precedence](#precedence)
- [Cascade](#cascade)
- [Interaction with export\_level](#interaction-with-export_level)
- [Excluding books with no shelf](#excluding-books-with-no-shelf)
- [Validation](#validation)
  - [Known limitations](#known-limitations)
### Known limitations

- **Same-name resources cannot be individually disambiguated.** If two books share the same display name, a filter pattern will match both. Use cascade (exclude the parent shelf/book) to scope the filter more precisely, or rename one of the resources.
- **Renaming a resource can silently break a filter.** Filters match display names, not IDs — if a resource is renamed, existing patterns will no longer match it.
- **Shelfless books aren't governed by `shelves` filters** — see [Excluding books with no shelf](#excluding-books-with-no-shelf).
