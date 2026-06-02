# modify_links for books/chapters — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Localize images/attachments in combined book/chapter **markdown and html** exports (the `modify_links` feature), and adopt a folder-per-node output layout for the `books`/`chapters` export levels.

**Architecture:** Lift the asset download + link-rewrite machinery from `PageArchiver` up into the shared `NodeArchiver` base. Books/chapters write each node into its own directory (`<node.file_path>/<node.name>.<ext>`); when `modify_links` is on and a rewritable format (`markdown` or `html`) is requested, descendant-page assets are downloaded into that directory and the combined export's remote URLs are rewritten to local relative paths by grouping assets per source page and reusing the existing per-page rewriters (`update_asset_links` for md, `update_asset_links_html` for html; base64-inlined html `src` is left untouched). `pdf` is self-contained and written verbatim.

**Tech Stack:** Python 3, `pytest`, `pylint` (must stay 10.00/10), `requests`. Tooling via `task test` / `task lint`.

**Spec:** `docs/superpowers/specs/2026-06-02-modify-links-books-chapters-design.md`

**Reference reading before starting:**
- `bookstack_file_exporter/archiver/node_archiver.py` (the classes being refactored)
- `bookstack_file_exporter/archiver/asset_archiver.py` (`get_asset_nodes`, `get_asset_bytes`, `update_asset_links`, `get_relative_path`)
- `bookstack_file_exporter/exporter/node.py` (`Node.file_path`, `Node.children`, `Node.get_name`)
- `bookstack_file_exporter/archiver/archiver.py:44-65` (archiver construction)
- `tests/unit/test_book_archiver.py`, `tests/unit/test_chapter_archiver.py` (test patterns)

**Conventions:**
- Commits: `feat:`/`fix:` only (user rule; `feat` → minor bump, `fix` → patch). No Claude attribution in commits.
- TDD: write the failing test first, watch it fail, implement minimally, watch it pass, commit.
- Run a single test: `python -m pytest tests/unit/test_book_archiver.py::TestX::test_y -v`
- Run all: `task test`. Lint: `task lint`.

---

## File Structure

- **Modify** `bookstack_file_exporter/archiver/node_archiver.py` — move asset logic into `NodeArchiver` base; add folder layout; add descendant-page walk, asset collection, combined-md rewrite; simplify `PageArchiver` to use base helpers.
- **Modify** `bookstack_file_exporter/archiver/archiver.py:48-63` — pass `asset_config` to `BookArchiver`/`ChapterArchiver`.
- **Modify** `tests/unit/test_book_archiver.py` — update path assertions to folder layout; add asset/rewrite cases.
- **Modify** `tests/unit/test_chapter_archiver.py` — same.
- **Modify** `tests/unit/test_page_archiver.py` — only if signatures it calls change (keep page output identical).
- **Modify** `README.md` — Export Level section: correct markdown asset claim, document folder layout + modify_links support.
- **Modify** `examples/config.yml` — brief note.

---

## Task 1: Base `__init__` accepts optional asset config (no behavior change yet)

**Files:**
- Modify: `bookstack_file_exporter/archiver/node_archiver.py`
- Test: `tests/unit/test_book_archiver.py`

Make the base own asset state so Book/Chapter can use it, while keeping the existing primitive constructor signature working (asset features default off).

- [ ] **Step 1: Write failing test** — a BookArchiver built without asset config reports assets off.

In `tests/unit/test_book_archiver.py` add:

```python
class TestAssetConfigDefaults:
    def test_no_asset_config_means_modify_links_false(self, tmp_path):
        archiver = _make_book_archiver(tmp_path)
        assert archiver.modify_links is False
        assert archiver.export_images is False
        assert archiver.export_attachments is False
```

- [ ] **Step 2: Run, verify it fails**

Run: `python -m pytest tests/unit/test_book_archiver.py::TestAssetConfigDefaults -v`
Expected: FAIL (`AttributeError: 'BookArchiver' object has no attribute 'modify_links'`).

- [ ] **Step 3: Implement in `NodeArchiver`**

Change base `__init__` signature and body (add `asset_config` param + asset attrs). Add `AssetArchiver` import is already present.

```python
    def __init__(self, archive_dir: str, api_urls: dict[str, str],  # pylint: disable=too-many-arguments,too-many-positional-arguments
                 export_formats: list[str], http_client: HttpHelper,
                 export_meta: bool, asset_config=None) -> None:
        self.api_urls = api_urls
        self.export_formats = export_formats
        self.http_client = http_client
        self.export_meta = export_meta
        self.archive_file = f"{archive_dir}{_FILE_EXTENSION_MAP['tgz']}"
        self.tar_file = f"{archive_dir}{_FILE_EXTENSION_MAP['tar']}"
        self.archive_base_path = archive_dir.split("/")[-1]
        # asset handling (shared by page/book/chapter); None => disabled
        self.asset_config = asset_config
        self.asset_archiver = AssetArchiver(api_urls, http_client) if asset_config else None
        self.modify_links: bool = self._check_links_modify()
```

Add these to `NodeArchiver` (moved from `PageArchiver`), guarding for `asset_config is None`:

```python
    @property
    def export_images(self) -> bool:
        """return whether or not to export images"""
        return bool(self.asset_config and self.asset_config.export_images)

    @property
    def export_attachments(self) -> bool:
        """return whether or not to export attachments"""
        return bool(self.asset_config and self.asset_config.export_attachments)

    def _check_links_modify(self) -> bool:
        """Return True iff modify_links AND asset export enabled AND a rewritable format present."""
        if not (self.asset_config and self.asset_config.modify_links):
            return False
        if not (self.export_images or self.export_attachments):
            return False
        has_rewritable = any(fmt in _REWRITABLE_FORMATS for fmt in self.export_formats)
        if not has_rewritable:
            log.warning(
                "MODIFY_LINKS ENABLED BUT NO REWRITABLE FORMAT (markdown, html) CONFIGURED "
                "- NO LINK REWRITING WILL OCCUR"
            )
            return False
        return True
```

Now delete the duplicate `_check_links_modify`, `export_images`, `export_attachments` from `PageArchiver`, and change `PageArchiver.__init__` to pass `asset_config` to super and drop its own `self.modify_links`/`self.asset_archiver`:

```python
    def __init__(self, archive_dir: str, config: ConfigNode, http_client: HttpHelper) -> None:
        super().__init__(
            archive_dir=archive_dir,
            api_urls=config.urls,
            export_formats=config.user_inputs.formats,
            http_client=http_client,
            export_meta=config.user_inputs.assets.export_meta,
            asset_config=config.user_inputs.assets,
        )
```

(Leave the rest of `PageArchiver` — `archive`, `_modify_links`, etc. — as is for now; they reference `self.asset_archiver`/`self.modify_links` which now live on the base.)

**Ordering constraint (do not reorder):** base `__init__` must set `self.asset_config`
BEFORE calling `self._check_links_modify()` (which reads `self.export_images` →
`self.asset_config`). The body above already orders it correctly. A slip yields
`AttributeError: asset_config` at construction.

**Pylint budget:** moving asset state into the base may trip
`too-many-instance-attributes` / `too-many-public-methods` on `NodeArchiver`. If
lint drops below 10.00, add the same `# pylint: disable=too-many-instance-attributes`
already used on `PageArchiver` to the `NodeArchiver` class line. Do not lower the
project lint threshold.

- [ ] **Step 4: Run, verify pass + full suite green**

Run: `python -m pytest tests/unit/test_book_archiver.py::TestAssetConfigDefaults -v` → PASS
Run: `python -m pytest tests/unit/test_page_archiver.py -v` → all pass (page construction + asset paths unchanged — this is the regression guard for the `PageArchiver.__init__` rewrite).
Run: `task test` → all pass (page behavior unchanged). Run: `task lint` → 10.00/10.

- [ ] **Step 5: Commit**

```bash
git add bookstack_file_exporter/archiver/node_archiver.py tests/unit/test_book_archiver.py
git commit -m "feat: move asset config into NodeArchiver base"
```

---

## Task 2: Folder-per-node output layout for books/chapters

**Files:**
- Modify: `bookstack_file_exporter/archiver/node_archiver.py` (`_archive_node`, `_archive_node_meta`, `_export_nodes`)
- Test: `tests/unit/test_book_archiver.py`, `tests/unit/test_chapter_archiver.py`

Combined content/meta move from `<file_path>.<ext>` to `<file_path>/<node.name>.<ext>`.

- [ ] **Step 1: Write failing test** — book content + meta land inside a per-node folder.

In `tests/unit/test_book_archiver.py` (assumes existing helper `_make_book_node`; a book node's `file_path` is its slug when parentless):

```python
class TestFolderLayout:
    def test_book_content_written_inside_node_folder(self, tmp_path):
        archiver = _make_book_archiver(tmp_path, formats=["markdown"])
        node = _make_book_node(1, "my-book")
        written = {}
        archiver.write_data = lambda path, data: written.__setitem__(path, data)
        archiver._get_node_data = lambda url: b"# combined"
        archiver._archive_level({1: node}, "books", "book")
        assert f"{archiver.archive_base_path}/my-book/my-book.md" in written

    def test_book_meta_written_inside_node_folder(self, tmp_path):
        archiver = _make_book_archiver(tmp_path, formats=["markdown"], export_meta=True)
        node = _make_book_node(1, "my-book")
        written = {}
        archiver.write_data = lambda path, data: written.__setitem__(path, data)
        archiver._get_node_data = lambda url: b"# combined"
        archiver._archive_level({1: node}, "books", "book")
        assert f"{archiver.archive_base_path}/my-book/my-book_meta.json" in written
```

- [ ] **Step 2: Run, verify fail**

Run: `python -m pytest tests/unit/test_book_archiver.py::TestFolderLayout -v`
Expected: FAIL (paths are currently `my-book.md`, not `my-book/my-book.md`).

- [ ] **Step 3: Implement** — nest in base `_archive_node` / `_archive_node_meta`. Change `_archive_node_meta` to take the node so it can build the folder path, and update its caller in `_export_nodes`.

```python
    def _archive_node(self, node: Node, export_format: str, data: bytes):
        file_name = (
            f"{self.archive_base_path}/"
            f"{node.file_path}/{node.name}{_FILE_EXTENSION_MAP[export_format]}"
        )
        self.write_data(file_name, data)

    def _archive_node_meta(self, node: Node, meta_data: dict):
        meta_file_name = (
            f"{self.archive_base_path}/"
            f"{node.file_path}/{node.name}{_FILE_EXTENSION_MAP['meta']}"
        )
        bytes_meta = archiver_util.get_json_bytes(meta_data)
        self.write_data(file_path=meta_file_name, data=bytes_meta)
```

In `_export_nodes`, change the meta call from `self._archive_node_meta(node.file_path, node.meta)` to `self._archive_node_meta(node, node.meta)`.

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/unit/test_book_archiver.py::TestFolderLayout -v` → PASS

- [ ] **Step 5: Update existing path assertions for chapters too**

In `tests/unit/test_chapter_archiver.py`, find existing tests asserting combined chapter paths like `<...>/<chapter>.md` / `<chapter>_meta.json` and update them to `<...>/<chapter>/<chapter>.md` / `<chapter>/<chapter>_meta.json`. Run `python -m pytest tests/unit/test_chapter_archiver.py -v` and fix each path assertion until green.

- [ ] **Step 6: Run full suite + lint**

Run: `task test` → all pass. `task lint` → 10.00/10.

- [ ] **Step 7: Commit**

```bash
git add bookstack_file_exporter/archiver/node_archiver.py tests/unit/test_book_archiver.py tests/unit/test_chapter_archiver.py
git commit -m "feat: folder-per-node layout for books/chapters export"
```

---

## Task 3: Descendant-page name map for a book/chapter node

**Files:**
- Modify: `bookstack_file_exporter/archiver/node_archiver.py` (add `_descendant_page_names` to base)
- Test: `tests/unit/test_book_archiver.py`

Map `{page_id: page_name}` for every page under a node, so assets (keyed by `uploaded_to` page id) get the correct per-page subdir name. `page_name` uses the same slug logic as `Node.get_name` (slug if present, else slugify(name)).

- [ ] **Step 1: Write failing test** — load the REAL fixtures so the page-shape
matches production (top children have `type`, chapter-nested pages do NOT).

First inspect `tests/fixtures/book_detail_mixed.json` and
`tests/fixtures/chapter_detail.json` to read the actual page `id`/`slug` values,
then assert against them. Example shape (replace the ids/slugs with the fixture's
real values after inspecting):

```python
import json
from pathlib import Path

_FIXTURES = Path(__file__).parent.parent / "fixtures"

def _load_fixture(name):
    return json.loads((_FIXTURES / name).read_text())

class TestDescendantPages:
    def test_book_collects_direct_and_chapter_nested_pages(self, tmp_path):
        archiver = _make_book_archiver(tmp_path)
        node = Node(_load_fixture("book_detail_mixed.json"), parent=None)
        result = archiver._descendant_page_names(node)
        # every page id in contents (direct + chapter-nested) must be present,
        # mapped to its slug. Derive expected from the fixture itself:
        expected = {}
        for child in node.children:
            if child.get("type") == "chapter" or "pages" in child:
                for p in child.get("pages", []):
                    expected[p["id"]] = p["slug"]
            else:
                expected[child["id"]] = child["slug"]
        assert result == expected
        assert result  # non-empty: proves chapter-nested pages were captured

    def test_page_name_falls_back_to_slugified_name(self, tmp_path):
        archiver = _make_book_archiver(tmp_path)
        meta = {"id": 1, "name": "bk", "slug": "bk",
                "contents": [{"id": 10, "type": "page", "slug": "", "name": "My Page!"}]}
        node = Node(meta, parent=None)
        assert archiver._descendant_page_names(node) == {10: "my-page"}
```

- [ ] **Step 2: Run, verify fail**

Run: `python -m pytest tests/unit/test_book_archiver.py::TestDescendantPages -v`
Expected: FAIL (`AttributeError: _descendant_page_names`).

- [ ] **Step 3: Implement in `NodeArchiver`**

```python
    @staticmethod
    def _page_name(child: dict) -> str:
        """Slug if present, else a slugified name (mirrors Node.get_name)."""
        slug = child.get("slug")
        if slug:
            return slug
        return Node.slugify(child.get("name", ""))

    def _descendant_page_names(self, node: Node) -> dict[int, str]:
        """Map {page_id: page_name} for every page under a book/chapter node.

        Do NOT rely on a ``type`` key for pages. Verified against fixtures:
        - book ``contents`` children carry ``type`` ('page'|'chapter'); chapter
          children carry a nested ``pages`` list.
        - chapter-detail ``pages`` entries (and the book's chapter-nested
          ``pages``) have **no** ``type`` key.
        So: a child is a chapter iff it has a nested ``pages`` list (or
        ``type == 'chapter'``); otherwise it is a page.
        """
        pages: dict[int, str] = {}
        for child in node.children:
            if child.get("type") == "chapter" or "pages" in child:
                for page in child.get("pages", []):
                    pages[page["id"]] = self._page_name(page)
            else:
                pages[child["id"]] = self._page_name(child)
        return pages
```

(`Node` is already imported in this module. This rule is verified against
`tests/fixtures/book_detail_mixed.json` (book contents, `type` present on top
children, absent on chapter-nested pages) and `tests/fixtures/chapter_detail.json`
(chapter `pages` have no `type`). The Task 3/Task 5 tests MUST load these fixtures
— not hand-built dicts — or they will mask the chapter no-op.)

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/unit/test_book_archiver.py::TestDescendantPages -v` → PASS

- [ ] **Step 5: Add the chapter-level regression test** in `tests/unit/test_chapter_archiver.py` — this is the test that guards the headline blocker (chapter `pages` have no `type` key). Load `tests/fixtures/chapter_detail.json`, build a chapter `Node` from it, and assert the descendant map is **non-empty** and equals `{page["id"]: page["slug"]}` for every entry in the fixture's `pages`:

```python
import json
from pathlib import Path
_FIXTURES = Path(__file__).parent.parent / "fixtures"

class TestChapterDescendantPages:
    def test_chapter_pages_without_type_key_are_captured(self, tmp_path):
        archiver = _make_chapter_archiver(tmp_path)  # use the file's existing helper
        meta = json.loads((_FIXTURES / "chapter_detail.json").read_text())
        node = Node(meta, parent=None)
        result = archiver._descendant_page_names(node)
        expected = {p["id"]: p["slug"] for p in meta["pages"]}
        assert result == expected
        assert result, "chapter descendant pages must not be empty (no-type-key regression)"
```

Run: `python -m pytest tests/unit/test_chapter_archiver.py::TestChapterDescendantPages -v`. If `result` is empty, the `_descendant_page_names` chapter handling is wrong — fix it (do not weaken the test).

- [ ] **Step 6: Run full suite + lint, commit**

```bash
git add bookstack_file_exporter/archiver/node_archiver.py tests/unit/test_book_archiver.py tests/unit/test_chapter_archiver.py
git commit -m "feat: descendant-page name map for book/chapter nodes"
```

---

## Task 4: Lift asset download into base; collect per-node assets

**Files:**
- Modify: `bookstack_file_exporter/archiver/node_archiver.py`
- Test: `tests/unit/test_book_archiver.py`

Move `archive_page_assets` and the `_get_image_meta`/`_get_attachment_meta` helpers from `PageArchiver` to `NodeArchiver` (rename `archive_page_assets` → `_archive_node_assets`; keep `archive_page_assets` as a thin alias if `test_page_archiver` references it). Add a per-node collector that downloads assets into the node folder, grouped by source page.

- [ ] **Step 1: Write failing test** — book with one image on one page downloads to `<book>/images/<page>/<img>`.

```python
class TestAssetDownload:
    def test_downloads_image_into_node_folder(self, tmp_path):
        archiver = _make_book_archiver(tmp_path, formats=["markdown"])
        # enable modify_links by injecting an asset_config double
        archiver.asset_config = MagicMock(export_images=True, export_attachments=False,
                                          modify_links=True, export_meta=False)
        archiver.modify_links = True
        node = Node({"id": 1, "name": "bk", "slug": "bk",
                     "contents": [{"id": 10, "type": "page", "slug": "pg", "name": "Pg"}]},
                    parent=None)
        img = MagicMock(id_=99, download_url="http://x/img", uploaded_to=10)
        img.get_relative_path = lambda page_name: f"images/{page_name}/img.png"
        archiver.asset_archiver = MagicMock()
        archiver.asset_archiver.get_asset_bytes.return_value = b"PNGDATA"
        written = {}
        archiver.write_data = lambda path, data: written.__setitem__(path, data)
        failed = archiver._archive_node_assets("images", node.file_path, "pg", [img])
        assert failed == set()
        assert f"{archiver.archive_base_path}/bk/images/pg/img.png" in written
```

- [ ] **Step 2: Run, verify fail** (`AttributeError: _archive_node_assets`).

Run: `python -m pytest tests/unit/test_book_archiver.py::TestAssetDownload -v`

- [ ] **Step 3: Implement** — move these methods to `NodeArchiver` verbatim (renaming the first):

```python
    def _archive_node_assets(self, asset_type: str, parent_path: str, page_name: str,
                             asset_nodes: list[ImageNode | AttachmentNode]) -> set[int]:
        """Download assets for one source page into <parent_path>/<prefix>/<page_name>/."""
        if not asset_nodes:
            return set()
        failed_assets: set[int] = set()
        node_base_path = f"{self.archive_base_path}/{parent_path}"
        for asset_node in asset_nodes:
            try:
                asset_data = self.asset_archiver.get_asset_bytes(asset_type, asset_node.download_url)
            except (HTTPError, RetryError):
                failed_assets.add(asset_node.id_)
                log.error("Failed to get image or attachment data "
                          "for asset located at: %s - skipping", asset_node.download_url)
                continue
            asset_path = f"{node_base_path}/{asset_node.get_relative_path(page_name)}"
            self.write_data(asset_path, asset_data)
        return failed_assets

    def _get_image_meta(self) -> dict[int, list]:
        if not self.export_images:
            return {}
        return self.asset_archiver.get_asset_nodes('images')

    def _get_attachment_meta(self) -> dict[int, list]:
        if not self.export_attachments:
            return {}
        return self.asset_archiver.get_asset_nodes('attachments')
```

In `PageArchiver`, replace the body of `archive_page_assets` with a call to the base method (keep the name so existing page code/tests still work):

```python
    def archive_page_assets(self, asset_type: str, parent_path: str, page_name: str,
                            asset_nodes) -> set[int]:
        return self._archive_node_assets(asset_type, parent_path, page_name, asset_nodes)
```

Remove the now-duplicate `_get_image_meta`/`_get_attachment_meta` from `PageArchiver`.

- [ ] **Step 4: Run, verify pass + full suite green + lint.**

Run: `python -m pytest tests/unit/test_book_archiver.py::TestAssetDownload -v` → PASS
Run: `task test` → all pass. `task lint` → 10.00/10.

- [ ] **Step 5: Commit**

```bash
git add bookstack_file_exporter/archiver/node_archiver.py tests/unit/test_book_archiver.py
git commit -m "feat: lift asset download into NodeArchiver base"
```

---

## Task 5: Wire asset download + markdown rewrite into the book/chapter export flow

**Files:**
- Modify: `bookstack_file_exporter/archiver/node_archiver.py` (`_archive_level`, `_export_nodes`)
- Test: `tests/unit/test_book_archiver.py`, `tests/unit/test_chapter_archiver.py`

When `modify_links` is active and `markdown` is requested: list assets once for the level, then per node download descendant-page assets and rewrite the combined markdown URLs (grouped per source page so the existing `update_asset_links(asset_type, page_name, data, assets)` reuses unchanged).

- [ ] **Step 1: Write failing integration-style test** — combined md AND html
remote URLs rewritten to local paths; pdf written verbatim; base64 `src` left alone.

```python
class TestCombinedRewrite:
    def _img(self, id_, uploaded_to):
        img = MagicMock(id_=id_, download_url=f"http://x/{id_}", uploaded_to=uploaded_to)
        img.get_relative_path = lambda page_name: f"images/{page_name}/{id_}.png"
        return img

    def test_markdown_and_html_remote_urls_rewritten_pdf_verbatim(self, tmp_path):
        archiver = _make_book_archiver(tmp_path, formats=["markdown", "html", "pdf"])
        archiver.asset_config = MagicMock(export_images=True, export_attachments=False,
                                          modify_links=True, export_meta=False)
        archiver.modify_links = True
        node = Node({"id": 1, "name": "bk", "slug": "bk",
                     "contents": [{"id": 10, "type": "page", "slug": "pg", "name": "Pg"}]},
                    parent=None)
        img = self._img(99, 10)
        aa = MagicMock()
        aa.get_asset_nodes.side_effect = lambda kind: {10: [img]} if kind == "images" else {}
        aa.get_asset_bytes.return_value = b"PNGDATA"
        # both rewriters do a literal remote->local replace (base64 src has no match)
        aa.update_asset_links.side_effect = (
            lambda atype, page_name, data, nodes: data.replace(b"http://x/99", b"images/pg/99.png"))
        aa.update_asset_links_html.side_effect = (
            lambda atype, page_name, data, nodes: data.replace(b"http://x/99", b"images/pg/99.png"))
        archiver.asset_archiver = aa
        bodies = {
            "markdown": b"![](http://x/99)",
            "html": b"<img src='data:image/png;base64,AAAA'><img src='http://x/99'>",
            "pdf": b"%PDF-1.4 http://x/99",  # pdf must NOT be rewritten
        }
        written = {}
        archiver.write_data = lambda path, data: written.__setitem__(path, data)
        archiver._get_node_data = lambda url: bodies[url.rsplit("/", 1)[-1]]
        archiver._archive_level({1: node}, "books", "book")
        base = archiver.archive_base_path
        md = written[f"{base}/bk/bk.md"]
        html = written[f"{base}/bk/bk.html"]
        pdf = written[f"{base}/bk/bk.pdf"]
        assert b"images/pg/99.png" in md and b"http://x/99" not in md
        # html: remote src rewritten, base64 src untouched
        assert b"images/pg/99.png" in html and b"http://x/99" not in html
        assert b"data:image/png;base64,AAAA" in html
        # pdf: written verbatim, NOT rewritten
        assert pdf == b"%PDF-1.4 http://x/99"
```

- [ ] **Step 2: Run, verify fail** (md/html still contain the remote URL).

Run: `python -m pytest tests/unit/test_book_archiver.py::TestCombinedRewrite -v`

- [ ] **Step 3: Implement** — extend `_archive_level` and `_export_nodes`.

```python
    def _archive_level(self, nodes: dict[int, Node], resource_type: str, label: str):
        """Shared entry point for book/chapter archivers."""
        if not nodes:
            log.warning("No %s nodes available. Nothing to archive", label)
            return
        non_empty = {}
        for node_id, node in nodes.items():
            if not node.children:
                log.info("Skipping empty %s '%s' (no children)", label, node.name)
                continue
            non_empty[node_id] = node
        if not non_empty:
            log.warning("No non-empty %s nodes available. Nothing to archive", label)
            return
        # Asset localization applies to rewritable combined exports (markdown +
        # html). pdf is self-contained. Warn on the dead-state combo where
        # modify_links is on but no rewritable format is requested.
        image_map: dict[int, list] = {}
        attachment_map: dict[int, list] = {}
        if self.modify_links:
            if any(fmt in _REWRITABLE_FORMATS for fmt in self.export_formats):
                image_map = self._get_image_meta()
                attachment_map = self._get_attachment_meta()
            else:
                log.warning(
                    "modify_links is enabled but no rewritable format "
                    "(markdown, html) is in formats; asset localization for %s "
                    "will not occur",
                    label,
                )
        self._export_nodes(non_empty, resource_type, image_map, attachment_map)

    def _export_nodes(self, nodes: dict[int, Node], resource_type: str,
                      image_map: dict[int, list] | None = None,
                      attachment_map: dict[int, list] | None = None):
        """Fetch and archive each node in every requested format."""
        image_map = image_map or {}
        attachment_map = attachment_map or {}
        for _, node in nodes.items():
            assets_by_page = self._download_node_assets(node, image_map, attachment_map)
            for fmt in self.export_formats:
                url = f"{self.api_urls[resource_type]}/{node.id_}/export/{fmt}"
                try:
                    data = self._get_node_data(url)
                except (HTTPError, RetryError):
                    log.error("Failed to get %s data for node id=%d format=%s - skipping",
                              resource_type, node.id_, fmt)
                    continue
                if self.modify_links and fmt in _REWRITABLE_FORMATS:
                    data = self._rewrite_combined(data, fmt, assets_by_page)
                self._archive_node(node, fmt, data)
            if self.export_meta:
                self._archive_node_meta(node, node.meta)

    def _download_node_assets(self, node: Node, image_map: dict[int, list],
                              attachment_map: dict[int, list]) -> dict:
        """Download this node's descendant-page assets; return survivors grouped per page+type."""
        if not (image_map or attachment_map):
            return {}
        page_names = self._descendant_page_names(node)
        grouped = {"images": {}, "attachments": {}}
        for asset_type, amap in (("images", image_map), ("attachments", attachment_map)):
            for page_id, page_name in page_names.items():
                assets = amap.get(page_id)
                if not assets:
                    continue
                failed = self._archive_node_assets(asset_type, node.file_path, page_name, assets)
                survivors = [a for a in assets if a.id_ not in failed]
                if survivors:
                    grouped[asset_type][page_name] = survivors
        return grouped

    def _rewrite_combined(self, data: bytes, export_format: str,
                          assets_by_page: dict) -> bytes:
        """Rewrite asset URLs in a combined markdown/html export.

        Reuses the per-page rewriters; markdown -> update_asset_links,
        html -> update_asset_links_html (base64-inlined src left untouched).
        """
        if not assets_by_page or self.asset_archiver is None:
            return data
        if export_format == "markdown":
            rewrite = self.asset_archiver.update_asset_links
        elif export_format == "html":
            rewrite = self.asset_archiver.update_asset_links_html
        else:
            return data
        for asset_type, by_page in assets_by_page.items():
            for page_name, assets in by_page.items():
                data = rewrite(asset_type, page_name, data, assets)
        return data
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/unit/test_book_archiver.py::TestCombinedRewrite -v` → PASS

- [ ] **Step 5: Add chapter equivalent** in `tests/unit/test_chapter_archiver.py` (chapter node with pages directly under it — from `chapter_detail.json` shape, no `type` key on pages; assert both md and html remote URLs rewritten, pdf verbatim). Run it green.

- [ ] **Step 6: Run full suite + lint, commit**

```bash
git add bookstack_file_exporter/archiver/node_archiver.py tests/unit/test_book_archiver.py tests/unit/test_chapter_archiver.py
git commit -m "feat: localize images/attachments in book/chapter markdown"
```

---

## Task 6: Pass `asset_config` to Book/Chapter archivers in `archiver.py`

**Files:**
- Modify: `bookstack_file_exporter/archiver/archiver.py:48-63`
- Test: `tests/unit/test_archiver.py` (if it asserts archiver construction)

Without this wiring the feature is dead in production — Book/Chapter are built with no `asset_config`.

- [ ] **Step 1: Write failing test** — a books-level Archiver builds a BookArchiver with modify_links active when config enables it.

**Use `tests/fixtures/mock_config.py::make_mock_config`** to build the config — NOT the bare `MagicMock` `mock_config` fixture local to `test_archiver.py` (that one leaves `assets.modify_links` as a truthy MagicMock, making the assertion meaningless — finding from review). Build a real config with `export_level="books"`, `formats=["markdown"]`, `assets.modify_links=True`, `assets.export_images=True`, then assert `Archiver(...)._archiver.modify_links is True`. Inspect `make_mock_config`'s signature first to pass these correctly; do not invent a new config shape.

- [ ] **Step 2: Run, verify fail** (modify_links False because asset_config not passed).

- [ ] **Step 3: Implement**

```python
        if export_level == "books":
            return BookArchiver(
                archive_dir=self.archive_dir,
                api_urls=self.config.urls,
                export_formats=self.config.user_inputs.formats,
                http_client=http_client,
                export_meta=export_meta,
                asset_config=self.config.user_inputs.assets,
            )
        if export_level == "chapters":
            return ChapterArchiver(
                archive_dir=self.archive_dir,
                api_urls=self.config.urls,
                export_formats=self.config.user_inputs.formats,
                http_client=http_client,
                export_meta=export_meta,
                asset_config=self.config.user_inputs.assets,
            )
```

- [ ] **Step 4: Run, verify pass + full suite + lint.**

- [ ] **Step 5: Commit**

```bash
git add bookstack_file_exporter/archiver/archiver.py tests/unit/test_archiver.py
git commit -m "feat: enable modify_links for books/chapters export levels"
```

---

## Task 7: Documentation

**Files:**
- Modify: `README.md` (Export Level section, ~line 319-329)
- Modify: `examples/config.yml`

- [ ] **Step 1: Update README Export Level table** — correct the `books`/`chapters` rows so they no longer claim markdown assets are server-embedded, and state modify_links support + folder layout. Replace the `books` and `chapters` rows:

```markdown
| `books` | One combined file per book per format, written to a per-book folder (`<shelf>/<book>/<book>.<ext>`). `pdf` is self-contained. For `markdown` and `html`, set `assets.modify_links: true` (with `export_images`/`export_attachments`) to download images/attachments locally and rewrite links to relative paths (`html` keeps server-inlined base64 images and rewrites the remaining remote image/attachment URLs). |
| `chapters` | One combined file per chapter per format, in a per-chapter folder (`<shelf>/<book>/<chapter>/<chapter>.<ext>`). Same `modify_links` support (markdown + html) as `books`. **Note:** pages not under any chapter are not captured at this level. |
```

- [ ] **Step 2: Verify the existing "Empty nodes" note still reads correctly** after the table (added in an earlier commit).

- [ ] **Step 3: Add a brief note to `examples/config.yml`** near the `modify_links` / `export_level` keys, e.g. a comment: `# modify_links also localizes assets for books/chapters when exporting markdown or html`.

- [ ] **Step 4: Fix the stale in-code comment** in `bookstack_file_exporter/config_helper/models.py:70-71`, which states asset options apply only at page level / book-chapter embed server-side. Update it to note that `modify_links` now localizes assets for book/chapter **markdown** exports (html/pdf remain server-embedded). Read the exact current comment before editing.

- [ ] **Step 5: Commit**

```bash
git add README.md examples/config.yml bookstack_file_exporter/config_helper/models.py
git commit -m "docs: modify_links + folder layout for books/chapters"
```

---

## Final verification

- [ ] `task test` → all green (expect new book/chapter cases + unchanged page/run tests).
- [ ] `task lint` → 10.00/10.
- [ ] Manual sanity (optional, needs live instance): `export_level: books`, `formats: [markdown]`, `assets: {export_images: true, modify_links: true}` → a book with images yields `<shelf>/<book>/images/<page>/<img>` and the `.md` references `images/<page>/<img>`.
- [ ] Spec coverage re-check: every spec section maps to a task (layout→T2, base lift→T1/T4, descendant walk→T3, rewrite→T5, wiring→T6, docs→T7, error handling→reused paths exercised in T4/T5 tests).
