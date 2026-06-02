# Design: `modify_links` (asset localization) for `books` / `chapters` export levels

- **Date:** 2026-06-02
- **Status:** Approved design, pending implementation plan
- **Branch context:** builds on PR #109 (`73/export-level-book-chapter`, unmerged)

## Problem

PR #109 added `export_level: books | chapters`, exporting one combined document
per node via BookStack's server-side export endpoints. The PR documented (and the
code assumes) that assets are "embedded by the server" at these levels, so
`assets.export_images / export_attachments / modify_links` are ignored.

That is true **only for `html` and `pdf`**. Evidence from live smoke-test output:

| Format | Image references in combined export | Portable offline? |
| ------ | ----------------------------------- | ----------------- |
| `html` | `src="data:image/png;base64,…"` (inlined, all 41 books) | Yes — self-contained |
| `pdf`  | embedded in binary | Yes |
| `markdown` | `![](https://bookstack.example/uploads/images/gallery/…/scaled-1680-/img.png)` | **No — live remote URLs** |

So combined **markdown** exports are not portable: they reference live BookStack
URLs. This is exactly the gap `modify_links` closes for pages. The feature should
therefore extend to `books` and `chapters` **for the markdown format only**.

### Verified de-risking fact

Page-level markdown and combined book-level markdown reference **byte-identical**
image URLs (same `scaled-1680-` gallery form), confirmed by diffing smoke-test
output for the same book. The existing page-level rewriter
(`AssetArchiver.update_asset_links`, which builds both the scaled and canonical
URL variants via `all_urls`) therefore applies to combined markdown **unchanged**.

## Goals

1. When `assets.modify_links` is enabled and `markdown` is in `formats`, localize
   images/attachments in combined book/chapter markdown exports: download the
   assets into the archive and rewrite their URLs to local relative paths.
2. Adopt a **folder-per-node** output layout for `books`/`chapters` so multiple
   formats + asset directories stay organized.
3. Reuse existing asset machinery — do not reimplement download or rewrite.

## Non-goals (YAGNI)

- Rewriting `html`/`pdf` at book/chapter level (already self-contained; `html` is
  base64-inlined server-side — verified). Explicitly **not** rewritten here, a
  deliberate divergence from page-level html handling.
- Internal page-to-page navigation link rewriting (never existed for any level).
- New configuration keys. Reuse `assets.modify_links`, `assets.export_images`,
  `assets.export_attachments`.
- Shelf-level export, empty-node export (unchanged; empty nodes still skipped).
- Changing `pages`-level output (remains byte-identical to today).

## Output layout change (books / chapters only; pages unchanged)

Books/chapters move from flat files to a folder per node. The combined document
lives **inside** a directory named after the node, alongside its meta and any
asset directories.

```
# BOOKS — before (current PR #109)        # after
<shelf>/<book>.md                          <shelf>/<book>/<book>.md
<shelf>/<book>.html                        <shelf>/<book>/<book>.html
<shelf>/<book>.pdf                         <shelf>/<book>/<book>.pdf
<shelf>/<book>_meta.json                   <shelf>/<book>/<book>_meta.json
                                           <shelf>/<book>/images/<page>/<img>       (md + modify_links)
                                           <shelf>/<book>/attachments/<page>/<att>  (md + modify_links)

# CHAPTERS
<shelf>/<book>/<chapter>.md                <shelf>/<book>/<chapter>/<chapter>.md
<shelf>/<book>/<chapter>_meta.json         <shelf>/<book>/<chapter>/<chapter>_meta.json
                                           <shelf>/<book>/<chapter>/images/<page>/<img>      (md + modify_links)
                                           <shelf>/<book>/<chapter>/attachments/<page>/<att> (md + modify_links)
```

- File/meta name inside the folder repeats the node slug (`<book>/<book>.md`),
  mirroring page-level naming and keeping files self-identifying if extracted.
- The folder layout applies **always** for books/chapters, regardless of
  `modify_links`. Asset subdirectories appear only when `modify_links` + `markdown`.
- `pages` level is untouched: still `<shelf>/<book>/<page>.md` with assets at
  `<shelf>/<book>/images/<page>/…`.

### Why the folder layout makes rewriting trivial

`Node.file_path` today: book = `<shelf>/<book>`, chapter = `<shelf>/<book>/<chapter>`.
Currently `_archive_node` writes `<archive_base>/<file_path>.<ext>`. The change is
to write book/chapter content/meta as `<archive_base>/<file_path>/<node.name>.<ext>`
— i.e. one extra `/<node.name>` segment, placing the file *inside* its `file_path`
directory.

Asset download then reuses `archive_page_assets` with `parent_path = node.file_path`.
That writes assets to `<archive_base>/<file_path>/images/<page_name>/<asset>`, and
the rewriter emits the relative link `images/<page_name>/<asset>`, which resolves
correctly because the combined md now lives at `<archive_base>/<file_path>/<node>.md`.

## Architecture

### Lift asset logic into `NodeArchiver` base

Asset handling currently lives only in `PageArchiver`. Move the shared parts up
into `NodeArchiver` so `Page`, `Book`, and `Chapter` use one code path:

Move to base (`NodeArchiver`):
- `asset_config`, `export_images`, `export_attachments` properties
- `_check_links_modify()` and `self.modify_links`
- `self.asset_archiver = AssetArchiver(...)`
- `archive_page_assets(...)` (rename neutrally, e.g. `_archive_node_assets`, since
  it is no longer page-specific; the `page_name` argument becomes the per-asset
  source-page name)
- `_rewrite_page_data` / the markdown rewrite dispatch helper

Keep in `PageArchiver`:
- `archive(page_nodes)` page orchestration (per-page asset map, link rewrite per page)
- page-specific helpers (`_get_page_data`, `_archive_page`, `_archive_page_meta`)

`Book`/`Chapter` gain an asset + folder-aware export path (see data flow).

### Asset listing is instance-wide (existing behavior)

`AssetArchiver.get_asset_nodes(asset_type)` calls `http_get_all` over the whole
instance's image-gallery / attachments list (paginated), returning
`{page_id: [asset_node]}`. BookStack assets are page-owned; there is no per-book
filter endpoint. Book/chapter scoping is done client-side by intersecting
`uploaded_to` (page id) with the node's descendant page-id set. Cost is O(all
assets) — the same cost `PageArchiver` already pays when assets are enabled.

## Data flow — book/chapter export with `modify_links` + `markdown`

1. `run.py` selects nodes for the level (existing dispatch).
2. In `_archive_level` (or a level-aware variant), if `self.modify_links` is true
   **and** `markdown` is in `export_formats`:
   a. List assets instance-wide once: `get_asset_nodes("images")` and
      `("attachments")` (each gated by its `export_*` flag) → `{page_id: [node]}`.
   b. Per node, walk descendants to build the page-id set and a
      `{page_id: page_name}` map (book → chapters → pages, and direct pages;
      chapter → pages). Page name comes from the page node slug.
   c. Select asset nodes whose `uploaded_to` is in that set.
   d. Download them via the shared asset helper with `parent_path = node.file_path`,
      writing to `<node>/images/<page_name>/<asset>` (+ `attachments`).
3. For each requested format:
   - Fetch the combined export (`/api/{books,chapters}/{id}/export/{fmt}`).
   - If `fmt == markdown` and `modify_links` active: rewrite asset URLs via the
     existing `update_asset_links` byte-replace, excluding any assets whose
     download failed (leave those URLs untouched).
   - Write to `<node>/<node.name>.<ext>`.
4. Write meta to `<node>/<node.name>_meta.json`.

When `modify_links` is off, or `markdown` is not requested, no asset listing or
download occurs; only the folder-layout change applies.

## Error handling (all reuse existing behavior)

- **Asset download fails:** skip that asset, log, leave its URL untouched in the
  markdown (existing `archive_page_assets` returns `failed_assets`, excluded from
  rewrite).
- **Node export fetch fails/forbidden:** skip that node+format, continue
  (existing `_export_nodes` try/except).
- **Empty node (no children):** still filtered out before export (existing
  `_archive_level` filter). No change.
- **Node has pages but no assets:** no asset directory created; markdown has no
  remote asset URLs to rewrite. No-op.
- **`modify_links` on but only `html`/`pdf` requested:** no asset work (gated on
  `markdown` specifically for book/chapter, since combined html is server-inlined).

## Testing

Update existing:
- `tests/unit/test_book_archiver.py`, `tests/unit/test_chapter_archiver.py`:
  adjust path assertions to the new folder-per-node layout.

Add cases (book and chapter):
- Folder-per-node paths for content + meta across multiple formats.
- Asset download + markdown URL rewrite for a node spanning multiple pages
  (assert local relative paths in the rewritten md and asset bytes written to
  `<node>/images/<page>/…`).
- No asset work when `markdown` absent from formats (html/pdf only).
- No asset work when `modify_links` is false.
- Attachments handled symmetrically to images.
- Node with pages but no assets → md unchanged, no asset dir.
- Failed asset download → URL left untouched, other assets still rewritten.

Mock at boundaries: the asset-list API responses (`get_asset_nodes`) and the
combined-export bytes. Reuse fixtures/patterns from `test_page_archiver` and the
asset-archiver tests.

Lint must stay 10.00/10; full suite green.

## Config & documentation

- No new config keys.
- README: correct the Export Level table — combined `markdown` is **not**
  server-embedded; `modify_links` now localizes images/attachments for
  book/chapter markdown. Document the new folder-per-node layout. Keep the
  empty-node note added earlier.
- `examples/config.yml`: brief note that `modify_links` applies to book/chapter
  markdown.

## Backward compatibility

- `export_level: books | chapters` is **unreleased** (introduced in unmerged
  PR #109), so changing its output layout breaks no released behavior.
- `pages` level output is unchanged and remains byte-identical to current.

## Open risks / notes

- Instance-wide asset list is O(all assets); acceptable and pre-existing.
- Attachments are included by symmetry with images but were **not** verifiable
  against the smoke-test data (the test books contained no attachments). Tests
  must cover attachments with mocked data.
- The combined-export markdown's `scaled-1680-` URL variant is already handled by
  `all_urls`; verified identical to page-level URLs, so no rewriter change needed.
