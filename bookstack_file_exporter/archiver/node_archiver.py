import logging
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
                 export_meta: bool, asset_config=None, asset_archiver=None) -> None:
        self.api_urls = api_urls
        self.export_formats = export_formats
        self.http_client = http_client
        self.export_meta = export_meta
        # full path with .tgz extension
        self.archive_file = f"{archive_dir}{_FILE_EXTENSION_MAP['tgz']}"
        # intermediate tar before gzip
        self.tar_file = f"{archive_dir}{_FILE_EXTENSION_MAP['tar']}"
        # base folder name inside the tgz archive
        self.archive_base_path = archive_dir.split("/")[-1]
        # asset handling (shared by page/book/chapter); None => disabled
        self.asset_config = asset_config
        self.asset_archiver = asset_archiver if asset_archiver is not None else (
            AssetArchiver(api_urls, http_client) if asset_config else None
        )
        self.modify_links: bool = self._check_links_modify()

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
        return self.asset_archiver.get_asset_nodes('images')

    def _get_attachment_meta(self) -> dict[int, list]:
        if not self.export_attachments:
            return {}
        return self.asset_archiver.get_asset_nodes('attachments')

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
        image_map: dict[int, list] = {}
        attachment_map: dict[int, list] = {}
        if self.modify_links:
            image_map = self._get_image_meta()
            attachment_map = self._get_attachment_meta()
        self._export_nodes(non_empty, resource_type, image_map, attachment_map)

    def _export_nodes(self, nodes: dict[int, Node], resource_type: str,
                      image_map: dict[int, list],
                      attachment_map: dict[int, list]):
        """Fetch and archive each node in every requested format.

        The only caller (_archive_level) always passes real maps (empty when
        modify_links is off), so no None-defaulting is needed.
        """
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
                if fmt == "markdown" and self.modify_links:
                    data = self._rewrite_combined_markdown(data, assets_by_page)
                elif fmt == "html" and self.modify_links:
                    data = self._rewrite_combined_html(data, assets_by_page)
                self._archive_node(node, fmt, data)
            if self.export_meta:
                self._archive_node_meta(node, node.meta)

    def _download_node_assets(self, node: Node, image_map: dict[int, list],
                              attachment_map: dict[int, list]) -> dict:
        """Download this node's descendant-page assets; return survivors grouped per page+type."""
        if not (image_map or attachment_map):
            return {}
        page_names = self._asset_page_map(node)
        grouped = {"images": {}, "attachments": {}}
        for asset_type, amap in (("images", image_map), ("attachments", attachment_map)):
            for page_id, page_name in page_names.items():
                assets = amap.get(page_id)
                if not assets:
                    continue
                failed = self._archive_node_assets(
                    asset_type, self._asset_parent_path(node), page_name, assets)
                survivors = [a for a in assets if a.id_ not in failed]
                if survivors:
                    grouped[asset_type][page_name] = survivors
        return grouped

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
        """Write data to a tar file.

        Args:
            :file_path: <str> path of file relative to tar file inner directory
            :data: <bytes> data to write to that file_path within the tar
        """
        archiver_util.write_tar(self.tar_file, file_path, data)

    def gzip_archive(self):
        """Provide the tar to gzip and the name of the gzip output file."""
        archiver_util.create_gzip(self.tar_file, self.archive_file)

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
