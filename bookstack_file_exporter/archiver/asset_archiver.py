from __future__ import annotations

import logging
import base64
from typing import Union, Literal

from markdown_it import MarkdownIt
# pylint: disable=import-error
from requests import Response
from bs4 import BeautifulSoup, SoupStrainer

from bookstack_file_exporter.common.util import HttpHelper

# Module-level singleton avoids reconstructing the parser on every call.
_md = MarkdownIt()

log = logging.getLogger(__name__)

_IMAGE_DIR_NAME = "images"
_ATTACHMENT_DIR_NAME = "attachments"


class AssetNode:
    """
    Base class for other asset nodes. This class should not be used directly.

    Args:
        :meta_data: <dict[str, Union[int, str, bool]]> = asset meta data

    Returns:
        AssetNode instance for use in other classes
    """
    def __init__(self, meta_data: dict[str, int | str | bool]):
        self.id_: int = meta_data['id']
        self.page_id: int = meta_data['uploaded_to']
        self.download_url: str = ""
        self.page_url: str = ""
        self.name: str = ""
        self._relative_path_prefix: str = ""

    def get_relative_path(self, page_name: str) -> str:
        """image path local to page directory"""
        return f"{self._relative_path_prefix}/{page_name}/{self.name}"

    def all_urls(
            self, asset_data: dict[str, Union[int, str, bool, dict]],
            kind: Literal["markdown", "html"]) -> list[str]:
        """All URLs for this asset that may appear in an exported page.

        Canonical page_url always included — the per-asset content API
        may omit it (e.g. anchor href wrapping a scaled img src).
        Empty strings are filtered out (AttachmentNode.page_url is '').
        """
        extracted = (
            self._get_md_url_strs(asset_data)
            if kind == "markdown"
            else self._get_html_url_strs(asset_data)
        )
        # Build the full set of URLs that could appear in the exported page so
        # _build_url_map can map every variant to the same local path.
        #
        # Why append page_url:
        #   BookStack's per-asset content API can omit the canonical (full-res)
        #   URL — only the variants it embeds in content.markdown/content.html
        #   show up in `extracted`. Examples:
        #
        #     ImageNode (markdown): "[![alt](.../scaled-1680-/foo.png)](.../foo.png)"
        #       extracted = [".../foo.png", ".../scaled-1680-/foo.png"]
        #                    ^^^^^^^^^^^^^   ^^^^^^^^^^^^^^^^^^^^^^^^^
        #                    link_open href  inner image src
        #       page_url  =  ".../foo.png"
        #
        #     ImageNode (html): '<a href=".../foo.png"><img src="data:image/png;base64,..."></a>'
        #       extracted = [".../foo.png"]      # base64 src skipped by _get_html_url_strs
        #       page_url  =  ".../foo.png"
        #
        #     AttachmentNode (markdown): "[file.dat](.../attachments/6)"
        #       extracted = [".../attachments/6"]
        #       page_url  =  ""                  # attachments have no "view" URL
        #
        #   If page_url were missing, an exported page that contained ONLY the
        #   full-res URL (e.g. simple `![alt](full)` markdown without anchor
        #   wrap) would have nothing to match against and never get rewritten.
        #
        #   `*extracted` unpacks the list — [*extracted, page_url] builds a
        #   new list with page_url tacked on the end.
        #   Example: extracted=[1, 2] -> [*extracted, page_url] -> [1, 2, page_url]
        #
        # Why dedup:
        #   ImageNode.page_url IS the full-res URL, which `extracted` already
        #   contains for any anchor-wrapped markdown image. So the combined
        #   list typically has the full-res URL twice:
        #
        #     [*extracted, page_url]
        #       = [".../foo.png", ".../scaled-1680-/foo.png", ".../foo.png"]
        #          ^^^^^^^^^^^^^                              ^^^^^^^^^^^^^
        #          from extracted (link href)                 appended page_url (duplicate)
        #
        #   Dedup collapses it to one entry per URL:
        #     [".../foo.png", ".../scaled-1680-/foo.png"]
        #
        #   Functionally harmless to leave duplicates (every URL maps to the
        #   same local_path, so _build_url_map just overwrites the slot), but
        #   dedup keeps url_map clean and debug logs readable.
        #
        # Why dict.fromkeys instead of set():
        #   set() iteration order is implementation-defined and not stable
        #   across runs — log lines and any failure traces would shuffle.
        #   dict.fromkeys creates a dict using each URL as a key (value=None)
        #   and preserves insertion order, so output is deterministic.
        #
        # Why filter empties (the trailing `if u`):
        #   AttachmentNode.page_url is "" by design (no canonical view URL).
        #   An empty key here would land in url_map and trigger
        #   bytes.replace(b"", b"attachments/page/file.dat") downstream, which
        #   inserts the replacement BETWEEN EVERY BYTE of the page and
        #   destroys it.
        return [u for u in dict.fromkeys([*extracted, self.page_url]) if u]

    @staticmethod
    def _get_md_url_strs(asset_data: dict[str, Union[int, str]]) -> list[str]:
        """Extract image src and link href values from content.markdown.
        Uses markdown-it-py for spec-compliant parsing — handles URLs with
        parentheses and alt-text containing parens without regex brittleness."""
        md_str = ""
        if 'content' in asset_data and 'markdown' in asset_data.get('content', {}):
            md_str = asset_data['content']['markdown']
        if not md_str:
            return []
        urls = []
        for block_token in _md.parse(md_str):
            for token in (block_token.children or []):
                # `image` = single self-contained token for a markdown image.
                #   markdown: ![alt](URL)
                #   tokens:   image(src=URL, alt=alt)
                if token.type == 'image':
                    urls.append(token.attrs['src'])
                # `link_open` = opening half of a link pair; text and link_close
                # follow. We only need the opener's href; link_close has no attrs.
                #   markdown: [text](URL)
                #   tokens:   link_open(href=URL), text("text"), link_close
                #
                # For BookStack's anchor-wrapped image (click-to-zoom) shape,
                # both branches fire on the same construct:
                #   markdown: [![alt](inner)](outer)
                #   tokens:   link_open(href=outer), image(src=inner), link_close
                #   result:   [outer, inner]
                elif token.type == 'link_open':
                    urls.append(token.attrs['href'])
        return urls

    @staticmethod
    def _get_html_url_strs(asset_data: dict[str, Union[int, str]]) -> list[str]:
        """Extract URLs from content.html using bs4. Skips data: URIs."""
        html_str = ""
        if 'content' in asset_data and 'html' in asset_data['content']:
            html_str = asset_data['content']['html']
        if not html_str:
            return []
        strainer = SoupStrainer(["img", "a"])
        soup = BeautifulSoup(html_str, "html.parser", parse_only=strainer)
        urls: list[str] = []
        # collect outer anchor href first (click-to-zoom target)
        for anchor in soup.find_all("a", href=True):
            urls.append(anchor["href"])
        # collect img src only if not base64
        for img in soup.find_all("img", src=True):
            src = img["src"]
            if not src.startswith("data:"):
                urls.append(src)
        return urls


class ImageNode(AssetNode):
    """
    ImageNode handles image meta data and markdown url replacement.

    Args:
        :meta_data: <dict[str, Union[int, str]]> = image meta data

    Returns:
        ImageNode instance for use in archiving images for a page
    """
    def __init__(self, meta_data: dict[str, Union[int, str]]):
        super().__init__(meta_data)
        self.download_url: str = meta_data['url']
        self.page_url: str = meta_data['url']
        self.name: str = self.download_url.split('/')[-1]
        log.debug("Image node has generated url: %s", self.download_url)
        self._relative_path_prefix = f"{_IMAGE_DIR_NAME}"

class AttachmentNode(AssetNode):
    """
    AttachmentNode handles attachment meta data and markdown url replacement.

    Args:
        :meta_data: <dict[str, Union[int, str, bool]]> = attachment meta data
        :base_url: <str> = base url for attachment download

    Returns:
        AttachmentNode instance for use in archiving attachments for a page
    """
    def __init__(self, meta_data: dict[str, Union[int, str, bool]],
                 base_url: str):
        super().__init__(meta_data)
        self.download_url: str = f"{base_url}/{self.id_}"
        self.page_url: str = ""
        self.name = meta_data['name']
        log.debug("Attachment node has generated url: %s", self.download_url)
        self._relative_path_prefix = f"{_ATTACHMENT_DIR_NAME}"

    @staticmethod
    def _get_md_url_strs(asset_data: dict[str, int | str | dict]) -> list[str]:
        """Extract link href from links.markdown using markdown-it-py."""
        md_str = ""
        if 'links' in asset_data and 'markdown' in asset_data.get('links', {}):
            md_str = asset_data['links']['markdown']
        if not md_str:
            return []
        urls = []
        for block_token in _md.parse(md_str):
            for token in (block_token.children or []):
                # `image` = single self-contained token for a markdown image.
                # Attachments don't normally render as images, but links.markdown
                # is user-controllable so we handle defensively.
                #   markdown: ![alt](URL)
                #   tokens:   image(src=URL, alt=alt)
                if token.type == 'image':
                    urls.append(token.attrs['src'])
                # `link_open` = opening half of a link pair; this is the normal
                # shape BookStack returns for attachment links.
                #   markdown: [file.dat](URL)
                #   tokens:   link_open(href=URL), text("file.dat"), link_close
                elif token.type == 'link_open':
                    urls.append(token.attrs['href'])
        return urls

    @staticmethod
    def _get_html_url_strs(asset_data: dict[str, int | str | dict]) -> list[str]:
        """Extract href URL from links.html for attachments."""
        html_str = ""
        if 'links' in asset_data and 'html' in asset_data['links']:
            html_str = asset_data['links']['html']
        if not html_str:
            return []
        strainer = SoupStrainer("a")
        soup = BeautifulSoup(html_str, "html.parser", parse_only=strainer)
        return [a["href"] for a in soup.find_all("a", href=True)]


class AssetArchiver:
    """
    AssetArchiver handles image and attachment exports for a page.

    Args:
        :urls: <dict[str, str]> = api urls for images and attachments
        :http_client: <HttpHelper> = http helper functions with config from user inputs

    Returns:
        AssetArchiver instance for use in archiving images and attachments for a page
    """
    def __init__(self, urls: dict[str, str], http_client: HttpHelper):
        self.api_urls = urls
        self._asset_map = {
            'images': self._create_image_map,
            'attachments': self._create_attachment_map
        }
        self.http_client = http_client

    def get_asset_nodes(self, asset_type: str) -> dict[int, list[ImageNode | AttachmentNode]]:
        """Get image or attachment helpers for a page (paginated to cover all assets)."""
        asset_json = self.http_client.http_get_all(self.api_urls[asset_type])
        return self._asset_map[asset_type](asset_json)

    def get_asset_data(self, asset_type: str,
            meta_data: Union[AttachmentNode, ImageNode]) -> dict[str, str | bool | int | dict]:
        """Get asset data based on type"""
        data_url = f"{self.api_urls[asset_type]}/{meta_data.id_}"
        asset_data_response: Response = self.http_client.http_get_request(
            data_url)
        return asset_data_response.json()

    def get_asset_bytes(self, asset_type: str, url: str) -> bytes:
        """Get raw asset data"""
        asset_response: Response = self.http_client.http_get_request(
            url)
        match asset_type:
            case "images":
                asset_data = asset_response.content
            case "attachments":
                asset_data = self._decode_attachment_data(asset_response.json()['content'])
            case _:
                raise ValueError(f"unsupported asset type: {asset_type}")
        return asset_data

    def update_asset_links(self, asset_type: str, page_name: str, page_data: bytes,
            asset_nodes: list[ImageNode | AttachmentNode]) -> bytes:
        """Update markdown links in page data using literal bytes.replace."""
        url_map = self._build_url_map(asset_type, page_name, asset_nodes, kind="markdown")
        return self._apply_url_substitutions(page_data, url_map)

    def update_asset_links_html(self, asset_type: str, page_name: str, page_data: bytes,
            asset_nodes: list[ImageNode | AttachmentNode]) -> bytes:
        """Update HTML links in page data using bs4 URL discovery + bytes.replace.

        Caller must guard on modify_links before invoking this method.
        """
        if not asset_nodes:
            return page_data
        url_map = self._build_url_map(asset_type, page_name, asset_nodes, kind="html")
        # Parse to find which URLs appear in HTML element attributes (img src, a href).
        # Do NOT remove this filter — passing url_map directly to _apply_url_substitutions
        # would let bytes.replace hit URLs inside <code>, <pre>, comments, and text nodes.
        strainer = SoupStrainer(["img", "a"])
        soup = BeautifulSoup(page_data, "html.parser", parse_only=strainer)
        matched_urls: dict[str, str] = {}

        # Anchor-wrapped images: check img src and parent href
        for img in soup.find_all("img", src=True):
            src = img["src"]
            if src in url_map:
                matched_urls[src] = url_map[src]
            parent = img.parent
            if parent and parent.name == "a":
                href = parent.get("href", "")
                if href in url_map:
                    matched_urls[href] = url_map[href]
        # Catch-all for attachments and any anchor-wrapped image hrefs not captured above.
        # Dict assignment is idempotent for hrefs already seen in the img-parent branch.
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if href in url_map:
                matched_urls[href] = url_map[href]
        return self._apply_url_substitutions(page_data, matched_urls)

    def _build_url_map(self, asset_type: str, page_name: str,
            asset_nodes: list[ImageNode | AttachmentNode],
            kind: Literal["markdown", "html"]) -> dict[str, str]:
        """Build a {remote_url: local_relative_path} map for all asset nodes.

        For each node we collect every URL variant that could appear in the
        exported page (the per-asset API content URL, e.g. scaled image src,
        plus the canonical listing URL) and map each to the same local path.
        Callers then run literal bytes.replace of every key against the page
        body to rewrite remote links to local relative paths.

        For HTML exports, ImageNode.page_url already covers the anchor href
        that BookStack embeds in content.html (the img src is base64 and
        skipped by _get_html_url_strs). Skip the per-asset API call.
        """
        url_map: dict[str, str] = {}
        for asset_node in asset_nodes:
            # In HTML mode, ImageNode.page_url is the only useful URL —
            # content.html img src is base64 (filtered out) and the outer
            # anchor href equals page_url. Skip the redundant API call.
            if kind == "html" and isinstance(asset_node, ImageNode):
                asset_data: dict = {}
            else:
                asset_data = self.get_asset_data(asset_type, asset_node)
            local_path = asset_node.get_relative_path(page_name)
            for url in asset_node.all_urls(asset_data, kind):
                url_map[url] = local_path
        return url_map

    @staticmethod
    def _apply_url_substitutions(page_data: bytes, url_map: dict[str, str]) -> bytes:
        """Apply literal bytes.replace substitutions for each URL in url_map.

        Replace longest URLs first to avoid prefix-corruption. Attachment URLs
        use sequential IDs (`.../attachments/6`, `.../attachments/60`), so a
        shorter URL CAN be a prefix of a longer one when both attachments
        appear on the same page. Without sort:

          page:    "[a](.../attachments/6) [b](.../attachments/60)"
          replace .../attachments/6  first -> "[a](local/a.dat) [b](local/a.dat0)"
                                                                            ^^^
                                                  orphaned "0" from ID 60 — corruption

        With longest-first sort:

          replace .../attachments/60 first -> "[a](.../attachments/6) [b](local/b.dat)"
          replace .../attachments/6  next  -> "[a](local/a.dat) [b](local/b.dat)"  ✓

        Same risk applies to image filenames that share prefixes
        (`foo.png` vs `foo.png.thumb`), though BookStack's standard image
        URLs don't exhibit this. `sorted(dict, key=len, reverse=True)`
        iterates the dict's keys in descending length order.

        Logs debug when a URL has zero matches in page_data (silent-miss surface).
        """
        for url in sorted(url_map, key=len, reverse=True):
            if not url:
                # bytes.replace(b"", ...) inserts replacement between every byte —
                # guard here even though _build_url_map already filters empties.
                continue
            url_bytes = url.encode()
            local_path_bytes = url_map[url].encode()
            # isEnabledFor short-circuits the `not in` scan when debug is off,
            # avoiding a redundant O(n) pass before replace() runs.
            if log.isEnabledFor(logging.DEBUG) and url_bytes not in page_data:
                log.debug("URL has zero matches in page data (no substitution made): %s", url)
            page_data = page_data.replace(url_bytes, local_path_bytes)
        return page_data

    @staticmethod
    def _group_by_page(nodes: list["ImageNode | AttachmentNode"]
                       ) -> dict[int, list["ImageNode | AttachmentNode"]]:
        grouped: dict[int, list] = {}
        for node in nodes:
            grouped.setdefault(node.page_id, []).append(node)
        return grouped

    @classmethod
    def _create_image_map(cls, json_data) -> dict[int, list[ImageNode]]:
        return cls._group_by_page([ImageNode(meta) for meta in json_data])

    def _create_attachment_map(self, json_data) -> dict[int, list[AttachmentNode]]:
        nodes = [AttachmentNode(meta, self.api_urls['attachments'])
                 for meta in json_data if not meta['external']]
        return self._group_by_page(nodes)

    @staticmethod
    def _decode_attachment_data(b64encoded_data: str) -> bytes:
        """decode base64 encoded data"""
        asset_data = b64encoded_data.encode()
        return base64.b64decode(asset_data)
