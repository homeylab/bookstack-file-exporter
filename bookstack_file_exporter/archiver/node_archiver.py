import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
# pylint: disable=import-error
from requests.exceptions import HTTPError, RetryError
from bookstack_file_exporter.exporter.node import Node
from bookstack_file_exporter.archiver import util as archiver_util
from bookstack_file_exporter.archiver.asset_archiver import AssetArchiver, ImageNode, AttachmentNode
from bookstack_file_exporter.config_helper.config_helper import ConfigNode
from bookstack_file_exporter.common.util import HttpHelper

log = logging.getLogger(__name__)

_META_FILE_SUFFIX = "_meta.json"
_TAR_SUFFIX = ".tar"
_TAR_GZ_SUFFIX = ".tgz"

_FILE_EXTENSION_MAP = {
    "markdown": ".md",
    "html": ".html",
    "pdf": ".pdf",
    "plaintext": ".txt",
    "zip": ".zip",
    "meta": _META_FILE_SUFFIX,
    "tar": _TAR_SUFFIX,
    "tgz": _TAR_GZ_SUFFIX
}

_REWRITABLE_FORMATS = {"markdown", "html"}

# Soft-warn threshold for export_workers (not a hard cap). 16 is a conservative
# heuristic: ~2x headroom over the urllib3 connection-pool default (10). It is SOFT
# precisely because we cannot know the server's capacity — the speedup is bound by how
# fast the BookStack instance answers concurrent requests, which varies by deployment,
# so we advise rather than cap. User-facing rate-limit /
# 429 guidance is the single source of truth on the field in config_helper/models.py.
# NOTE: docs/configuration.md "Parallel Export" mirrors this 16 in prose; keep in sync.
_EXPORT_WORKERS_SOFT_MAX = 16


@dataclass
class ContentFailures:
    """Per-node export outcome for the run ledger.

    Returned by _export_node so failures ride the existing return path back to
    the coordinating thread instead of workers mutating shared archiver state.
    """
    nodes: list[str] = field(default_factory=list)   # node exports (path + format ext)
    assets: list[str] = field(default_factory=list)  # asset downloads (get_relative_path)
    # True once at least one format export for this node landed in the tar.
    # Deliberately NOT set by asset/meta writes: documents are the deliverable,
    # and assets without any document content are not a restorable backup.
    wrote_content: bool = False


# pylint: disable=too-many-instance-attributes
class NodeArchiver:
    """
    NodeArchiver is the base class for all level-specific archivers.

    Holds level-agnostic primitives: tar/gzip helpers, a generic export loop,
    and shared file-path/extension logic. Subclasses add level-specific
    state (e.g. asset handling for pages) and implement ``archive``.

    Args:
        :archive_dir: <str> = directory where data will be put into.
        :api_urls: <dict> = map of resource type to base API URL.
        :export_formats: <list[str]> = formats to export.
        :http_client: <HttpHelper> = http helper for API requests.
        :export_meta: <bool> = whether to write metadata JSON alongside exports.
        :asset_config: optional asset configuration; None => asset features disabled.
    """
    def __init__(self, archive_dir: str, api_urls: dict[str, str],  # pylint: disable=too-many-arguments,too-many-positional-arguments
                 export_formats: list[str], http_client: HttpHelper,
                 export_meta: bool, asset_config=None, asset_archiver=None,
                 export_workers: int = 1) -> None:
        self.api_urls = api_urls
        self.export_formats = export_formats
        self.http_client = http_client
        self.export_meta = export_meta
        # full path with .tgz extension
        self.archive_file = f"{archive_dir}{_FILE_EXTENSION_MAP['tgz']}"
        # streaming archive target; renamed to archive_file on finalize
        self.incomplete_file = f"{self.archive_file}.incomplete"
        self._tar_stream = archiver_util.TarStream(self.incomplete_file)
        # base folder name inside the tgz archive
        self.archive_base_path = os.path.basename(archive_dir)
        # asset handling (shared by page/book/chapter); None => disabled
        self.asset_config = asset_config
        self.asset_archiver = (
            asset_archiver if asset_archiver is not None
            else self._default_asset_archiver(api_urls, http_client)
        )
        self.modify_links: bool = self._check_links_modify()
        # Cooperative-shutdown flag, injected by Archiver.set_stop() in both
        # one-shot and scheduled mode. Polled at export checkpoints below; the
        # signal handler only SETS this flag (it cannot safely raise across
        # arbitrary code), so the export must poll it to cancel.
        self._stop = None
        # Content-loss ledger: paths this run failed to produce (node exports,
        # archive-relative) or download (assets, prefix/page/name -- only ever
        # counted, never resolved against the tar). Merged only by the coordinating
        # thread — the serial loop or the as_completed loop — from _export_node's
        # returned ContentFailures, so no lock is needed even with
        # export_workers > 1. A non-empty ledger downgrades the run to PARTIAL;
        # a non-empty ledger with content_written still False means no document
        # was archived at all (a hard failure upstream).
        self.failed_node_exports: list[str] = []
        self.failed_asset_downloads: list[str] = []
        self.content_written: bool = False
        # Opt-in node-level fetch parallelism (default 1 = serial, today's behavior).
        self.export_workers = export_workers
        if self.export_workers > _EXPORT_WORKERS_SOFT_MAX:
            log.warning(
                "export_workers=%d is high. The speedup is bound by how fast your "
                "BookStack instance answers concurrent requests, so beyond a point this "
                "adds load without speeding up the export and may hit HTTP 429 "
                "(BookStack API_REQUESTS_PER_MIN, default 180/min). If your server is "
                "provisioned for it, higher can be fine — tune to your deployment.",
                self.export_workers,
            )

    def set_stop(self, stop) -> None:
        """Inject the shutdown flag (threading.Event) for cooperative cancel."""
        self._stop = stop

    def _stop_requested(self) -> bool:
        """True when a shutdown signal has flagged this run for cancellation."""
        return self._stop is not None and self._stop.is_set()

    def _merge_failures(self, failures: ContentFailures) -> None:
        """Fold one node's outcome into the run ledger (coordinating thread only)."""
        self.failed_node_exports.extend(failures.nodes)
        self.failed_asset_downloads.extend(failures.assets)
        self.content_written = self.content_written or failures.wrote_content

    def _default_asset_archiver(self, api_urls: dict[str, str], http_client: HttpHelper):
        """Build an AssetArchiver when no double is injected, or return None if assets disabled."""
        return AssetArchiver(api_urls, http_client) if self.asset_config else None

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

    def _archive_node_assets(self, asset_type: str, parent_path: str, page_name: str,
                             asset_nodes: list[ImageNode | AttachmentNode]) -> set[int]:
        """Download assets for one source page into <parent_path>/<prefix>/<page_name>/."""
        if not asset_nodes:
            return set()
        failed_assets: set[int] = set()
        node_base_path = f"{self.archive_base_path}/{parent_path}"
        for asset_node in asset_nodes:
            if self._stop_requested():
                break
            try:
                asset_data = self.asset_archiver.get_asset_bytes(
                    asset_type, asset_node.download_url)
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
        try:
            return self.asset_archiver.get_asset_nodes('images')
        except (HTTPError, RetryError):
            # Degrade like every other network call here: a transient listing failure
            # drops image assets for this run (-> PARTIAL) instead of aborting the whole
            # backup. Empty map means nodes still export, just without image rewriting.
            log.error("Failed to list image metadata - skipping image assets this run")
            self.failed_asset_downloads.append("images (listing failed)")
            return {}

    def _get_attachment_meta(self) -> dict[int, list]:
        if not self.export_attachments:
            return {}
        try:
            return self.asset_archiver.get_asset_nodes('attachments')
        except (HTTPError, RetryError):
            log.error("Failed to list attachment metadata - skipping attachments this run")
            self.failed_asset_downloads.append("attachments (listing failed)")
            return {}

    def _get_node_data(self, url: str) -> bytes:
        return archiver_util.get_byte_response(url=url, http_client=self.http_client)

    def _asset_page_map(self, node: Node) -> dict[int, str]:
        """Map {page_id: page_name} of pages whose assets attach to this node."""
        return self._descendant_page_names(node)

    def _asset_parent_path(self, node: Node) -> str:
        """Directory (relative to archive_base_path) under which page assets are written."""
        return node.file_path

    def _node_output_path(self, node: Node) -> str:
        """Path fragment (relative to archive_base_path, no extension) for export/meta files."""
        return f"{node.file_path}/{node.name}"

    def _archive_node(self, node: Node, export_format: str, data: bytes):
        file_name = (
            f"{self.archive_base_path}/"
            f"{self._node_output_path(node)}{_FILE_EXTENSION_MAP[export_format]}"
        )
        self.write_data(file_name, data)

    def _archive_node_meta(self, node: Node, meta_data: dict):
        meta_file_name = (
            f"{self.archive_base_path}/"
            f"{self._node_output_path(node)}{_FILE_EXTENSION_MAP['meta']}"
        )
        bytes_meta = archiver_util.get_json_bytes(meta_data)
        self.write_data(meta_file_name, bytes_meta)

    def _archive_level(self, nodes: dict[int, Node],
                       resource_type: str, label: str):
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
        image_map = self._get_image_meta()
        attachment_map = self._get_attachment_meta()
        self._export_nodes(non_empty, resource_type, image_map, attachment_map)

    def _export_nodes(self, nodes: dict[int, Node], resource_type: str,
                      image_map: dict[int, list],
                      attachment_map: dict[int, list]):
        """Fetch and archive each node in every requested format.

        The only caller (_archive_level) always passes real maps (empty when
        modify_links is off), so no None-defaulting is needed. export_workers==1
        runs serially (byte-identical to pre-parallel behavior); >1 fans node
        fetches across a thread pool.
        """
        if (self.export_images or self.export_attachments) and not self.modify_links:
            log.info("Assets downloaded but links not rewritten (modify_links disabled)")
        if self.export_workers == 1:
            self._export_nodes_serial(nodes, resource_type, image_map, attachment_map)
        else:
            self._export_nodes_parallel(nodes, resource_type, image_map, attachment_map)

    def _export_nodes_serial(self, nodes: dict[int, Node], resource_type: str,
                             image_map: dict[int, list],
                             attachment_map: dict[int, list]):
        """Today's exact serial path: one node at a time, stop at node boundary."""
        for _, node in nodes.items():
            if self._stop_requested():
                return
            self._merge_failures(
                self._export_node(node, resource_type, image_map, attachment_map))

    def _export_nodes_parallel(self, nodes: dict[int, Node], resource_type: str,
                               image_map: dict[int, list],
                               attachment_map: dict[int, list]):
        """Fan node fetches across a thread pool; writes serialize inside TarStream.

        Memory stays ~= export_workers x fattest-node: only max_workers tasks run
        at once, and _export_node returns only the tiny ContentFailures ledger,
        so completed futures hold no bulky payload.

        Cancellation is cooperative, NOT a hard kill. On stop:
          - queued (not-yet-started) futures are dropped by shutdown(cancel_futures=True);
          - in-flight nodes are NOT interrupted -- they keep running until their own
            _stop_requested() checkpoints inside _export_node bail out, then the
            with-block exit waits for them to finish.
        The explicit shutdown(cancel_futures=True) is required: the with-exit shutdown
        runs WITHOUT cancel_futures, so without this call queued work would all run.
        A worker raising a non-HTTP error (HTTPError/RetryError are already swallowed
        per-format inside _export_node) is logged and skipped so one bad node never
        aborts the run - EXCEPT ArchiveWriteError: that means the shared tar stream
        is poisoned and no later node can be written, so the run aborts promptly
        instead of fetching the rest for nothing.
        """
        # Threads (not processes) because the work is I/O-bound: each node spends
        # almost all its time waiting on a network round-trip to BookStack, and
        # Python releases the GIL during blocking I/O, so the waits genuinely
        # overlap. (Unlike Go goroutines, Python threads do NOT parallelize
        # CPU-bound work — the GIL serializes that — but that is not our case.)
        # `with ThreadPoolExecutor(...)` is a context manager: its __exit__ calls
        # executor.shutdown(wait=True), so we always join every worker before
        # returning, even on an exception.
        with ThreadPoolExecutor(max_workers=self.export_workers) as executor:
            # {future: node} so the exception path below can name the lost node
            futures = {}
            for _, node in nodes.items():
                if self._stop_requested():
                    break
                # submit() schedules the call on a pool thread and returns
                # immediately with a Future handle (a promise of the result).
                futures[executor.submit(
                    self._export_node, node, resource_type, image_map,
                    attachment_map)] = node
            # as_completed yields each future the moment it finishes, in
            # completion order (NOT submission order) — so we react to whichever
            # node returns first.
            for future in as_completed(futures):
                # future.result() re-raises, in THIS thread, any exception the
                # worker thread raised. We catch broadly so one bad node is logged
                # and skipped rather than aborting every other node's export.
                try:
                    self._merge_failures(future.result())
                except archiver_util.ArchiveWriteError:
                    # The stream is poisoned: no later node can write, so
                    # continuing only burns API fetches. Drop queued futures and
                    # propagate; in-flight workers finish their fetch and die
                    # cheaply on the poisoned write. (Fail-fast is scoped to
                    # ArchiveWriteError deliberately - requests exceptions
                    # subclass OSError, so a broader class would abort the run
                    # on one flaky page.)
                    executor.shutdown(cancel_futures=True)
                    raise
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    log.error("Node export worker failed, skipping node: %s", exc)
                    # formats already exported before the crash are unknown here,
                    # so the entry carries no extension
                    self.failed_node_exports.append(
                        f"{self._node_output_path(futures[future])} (worker error)")
                # Honor stop only AFTER the just-completed result is recorded, so the
                # node yielded this iteration (already in the tar) is merged, not dropped.
                # This narrows the ledger gap; it does not fully close it - futures already
                # done-but-not-yet-yielded, and in-flight workers that finish during the
                # shutdown join, are still not merged. Acceptable: run.py discards the
                # partial on stop anyway, so the ledger is not consulted on the stop path.
                if self._stop_requested():
                    executor.shutdown(cancel_futures=True)
                    break

    def _export_node(self, node: Node, resource_type: str,
                     image_map: dict[int, list],
                     attachment_map: dict[int, list]) -> ContentFailures:
        """Fetch and archive ONE node in every requested format.

        Self-contained per node (no shared mutable state): safe to run in a
        worker thread when export_workers > 1. Writes go through write_data ->
        TarStream, which serializes appends under its internal lock. Returns only the
        tiny ContentFailures ledger, so completed pool futures retain no bulky
        payload (peak RAM ~= workers x fattest-node).
        """
        assets_by_page, failed_assets = self._download_node_assets(
            node, image_map, attachment_map)
        failures = ContentFailures(assets=failed_assets)
        for fmt in self.export_formats:
            # Per-format checkpoint: a single book/chapter export call can be slow
            # (server-side render); stop between formats instead of after all of them.
            if self._stop_requested():
                return failures
            url = f"{self.api_urls[resource_type]}/{node.id_}/export/{fmt}"
            try:
                data = self._get_node_data(url)
            except (HTTPError, RetryError):
                log.error("Failed to get %s data for node id=%d format=%s - skipping",
                          resource_type, node.id_, fmt)
                failures.nodes.append(
                    f"{self._node_output_path(node)}{_FILE_EXTENSION_MAP[fmt]}")
                continue
            if fmt == "markdown" and self.modify_links:
                data = self._rewrite_combined_markdown(data, assets_by_page)
            elif fmt == "html" and self.modify_links:
                data = self._rewrite_combined_html(data, assets_by_page)
            self._archive_node(node, fmt, data)
            failures.wrote_content = True
        if self.export_meta:
            self._archive_node_meta(node, node.meta)
        return failures

    def _download_node_assets(self, node: Node, image_map: dict[int, list],
                              attachment_map: dict[int, list]) -> tuple[dict, list[str]]:
        """Download this node's descendant-page assets.

        Returns (survivors grouped per page+type, archive-relative paths of the
        assets that failed to download)."""
        if not (image_map or attachment_map):
            return {}, []
        page_names = self._asset_page_map(node)
        grouped = {"images": {}, "attachments": {}}
        failed_paths: list[str] = []
        for asset_type, amap in (("images", image_map), ("attachments", attachment_map)):
            if self._stop_requested():
                break
            for page_id, page_name in page_names.items():
                assets = amap.get(page_id)
                if not assets:
                    continue
                failed = self._archive_node_assets(
                    asset_type, self._asset_parent_path(node), page_name, assets)
                failed_paths.extend(
                    a.get_relative_path(page_name) for a in assets if a.id_ in failed)
                survivors = [a for a in assets if a.id_ not in failed]
                if survivors:
                    grouped[asset_type][page_name] = survivors
        return grouped, failed_paths

    def _rewrite_combined(self, data: bytes, assets_by_page: dict, rewriter) -> bytes:
        """Run the shared guard and double loop, delegating each page to rewriter."""
        if not assets_by_page or self.asset_archiver is None:
            return data
        for asset_type, by_page in assets_by_page.items():
            for page_name, assets in by_page.items():
                data = rewriter(asset_type, page_name, data, assets)
        return data

    def _rewrite_combined_markdown(self, data: bytes, assets_by_page: dict) -> bytes:
        """Rewrite asset URLs in combined markdown, reusing the per-page rewriter."""
        return self._rewrite_combined(data, assets_by_page,
                                      self.asset_archiver.update_asset_links)

    def _rewrite_combined_html(self, data: bytes, assets_by_page: dict) -> bytes:
        """Rewrite asset URLs in combined html, reusing the per-page html rewriter."""
        return self._rewrite_combined(data, assets_by_page,
                                      self.asset_archiver.update_asset_links_html)

    def write_data(self, file_path: str, data: bytes):
        """Write data into the streaming archive.

        Args:
            :file_path: <str> path of file relative to archive inner directory
            :data: <bytes> data to write to that file_path within the archive
        """
        self._tar_stream.write(file_path, data)

    def finalize_archive(self):
        """Close the stream and atomically publish .tgz.incomplete as the final .tgz.

        Close-before-rename is load-bearing: a consumer or the next run never
        observes a half-written .tgz (a SIGKILL/crash mid-run leaves only the
        .incomplete, which the run-start sweep removes). finalize() raises if the
        stream is poisoned or the closing flush fails, so a corrupt archive is
        never renamed into place. The unconditional os.rename never sees a
        missing .incomplete: run.py only calls create_archive() after its
        has_exported_content / content_written gates proved a write happened —
        do not call this on an empty run.

        If the run ledger recorded any content loss (failed node exports or
        failed asset downloads), the published name gets a `_partial` marker
        inserted before the extension, e.g. `bookstack-<ts>_partial.tgz`. This
        only reflects content loss known at this point — upload-stage failures
        happen after this rename and can't be folded into the name. The marker
        goes after the timestamp (not as a prefix) so lexical and chronological
        order stay identical for local retention, and so the remote managed-object
        prefix filter (a startswith match on the timestamped base name) still
        matches partial archives.
        """
        self._tar_stream.finalize()
        if self.failed_node_exports or self.failed_asset_downloads:
            tgz_ext = _FILE_EXTENSION_MAP['tgz']
            self.archive_file = (
                f"{self.archive_file.removesuffix(tgz_ext)}_partial{tgz_ext}")
        os.rename(self.incomplete_file, self.archive_file)

    def abort_archive(self):
        """Close the stream best-effort so the discard path can unlink the .incomplete."""
        self._tar_stream.abort()

    @property
    def file_extension_map(self) -> dict[str, str]:
        """File extension metadata."""
        return _FILE_EXTENSION_MAP


class BookArchiver(NodeArchiver):
    """Archives one combined export file per book per format."""

    def archive(self, book_nodes: dict[int, Node]):
        """Export book contents for each book node."""
        self._archive_level(book_nodes, "books", "book")


class ChapterArchiver(NodeArchiver):
    """Archives one combined export file per chapter per format."""

    def archive(self, chapter_nodes: dict[int, Node]):
        """Export chapter contents for each chapter node."""
        self._archive_level(chapter_nodes, "chapters", "chapter")


class PageArchiver(NodeArchiver):
    """
    PageArchiver handles all data extraction and modifications
    to Bookstack page contents including assets like images or attachments.

    Args:
        :archive_dir: <str> = directory where data will be put into.
        :config: <ConfigNode> = Configuration with user inputs and general options.
        :http_client: <HttpHelper> = http helper functions with config from user inputs

    Returns:
        :PageArchiver: instance with methods to help collect page content from a Bookstack instance.
    """
    def __init__(self, archive_dir: str, config: ConfigNode, http_client: HttpHelper,
                 *, asset_archiver=None) -> None:
        super().__init__(
            archive_dir=archive_dir,
            api_urls=config.urls,
            export_formats=config.user_inputs.formats,
            http_client=http_client,
            export_meta=config.user_inputs.assets.export_meta,
            asset_config=config.user_inputs.assets,
            asset_archiver=asset_archiver,
            export_workers=config.user_inputs.export_workers,
        )

    def _asset_page_map(self, node: Node) -> dict[int, str]:
        return {node.id_: node.name}

    def _asset_parent_path(self, node: Node) -> str:
        return node.parent.file_path

    def _node_output_path(self, node: Node) -> str:
        return node.file_path

    def archive(self, page_nodes: dict[int, Node]):
        """Export page contents and their images/attachments."""
        image_map = self._get_image_meta()
        attachment_map = self._get_attachment_meta()
        self._export_nodes(page_nodes, "pages", image_map, attachment_map)
