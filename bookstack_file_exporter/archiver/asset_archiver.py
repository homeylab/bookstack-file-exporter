from __future__ import annotations

import logging
import base64
import html
from typing import Union, List, Dict, Literal

from markdown_it import MarkdownIt
# pylint: disable=import-error
from requests import Response
from bs4 import BeautifulSoup, SoupStrainer

from bookstack_file_exporter.common.util import HttpHelper

_md = MarkdownIt()

log = logging.getLogger(__name__)

_IMAGE_DIR_NAME = "images"
_ATTACHMENT_DIR_NAME = "attachments"


class AssetNode:
    """
    Base class for other asset nodes. This class should not be used directly.

    Args:
        :meta_data: <Dict[str, Union[int, str, bool]]> = asset meta data

    Returns:
        AssetNode instance for use in other classes
    """
    def __init__(self, meta_data: Dict[str, int | str | bool]):
        self.id_: int = meta_data['id']
        self.page_id: int = meta_data['uploaded_to']
        self.download_url: str = ""
        self.page_url: str = ""
        self.name: str = ""
        self._relative_path_prefix: str = ""

    def get_relative_path(self, page_name: str) -> str:
        """image path local to page directory"""
        return f"{self._relative_path_prefix}/{page_name}/{self.name}"

    def all_urls(self, asset_data: Dict[str, Union[int, str, bool, dict]], kind: Literal["markdown", "html"]) -> List[str]:
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
        return [u for u in dict.fromkeys([*extracted, self.page_url]) if u]

    @staticmethod
    def _get_md_url_strs(asset_data: Dict[str, Union[int, str]]) -> list[str]:
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
                if token.type == 'image':
                    urls.append(token.attrs['src'])
                elif token.type == 'link_open':
                    urls.append(token.attrs['href'])
        return urls

    @staticmethod
    def _get_html_url_strs(asset_data: Dict[str, Union[int, str]]) -> list[str]:
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
        :meta_data: <Dict[str, Union[int, str]]> = image meta data

    Returns:
        ImageNode instance for use in archiving images for a page
    """
    def __init__(self, meta_data: Dict[str, Union[int, str]]):
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
        :meta_data: <Dict[str, Union[int, str, bool]]> = attachment meta data
        :base_url: <str> = base url for attachment download

    Returns:
        AttachmentNode instance for use in archiving attachments for a page
    """
    def __init__(self, meta_data: Dict[str, Union[int, str, bool]],
                 base_url: str):
        super().__init__(meta_data)
        self.download_url: str = f"{base_url}/{self.id_}"
        self.page_url: str = ""
        self.name = meta_data['name']
        log.debug("Attachment node has generated url: %s", self.download_url)
        self._relative_path_prefix = f"{_ATTACHMENT_DIR_NAME}"

    @staticmethod
    def _get_md_url_strs(asset_data: Dict[str, int | str | dict]) -> list[str]:
        """Extract link href from links.markdown using markdown-it-py."""
        md_str = ""
        if 'links' in asset_data and 'markdown' in asset_data.get('links', {}):
            md_str = asset_data['links']['markdown']
        if not md_str:
            return []
        urls = []
        for block_token in _md.parse(md_str):
            for token in (block_token.children or []):
                if token.type == 'image':
                    urls.append(token.attrs['src'])
                elif token.type == 'link_open':
                    urls.append(token.attrs['href'])
        return urls

    @staticmethod
    def _get_html_url_strs(asset_data: Dict[str, int | str | dict]) -> list[str]:
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
        :urls: <Dict[str, str]> = api urls for images and attachments
        :http_client: <HttpHelper> = http helper functions with config from user inputs

    Returns:
        AssetArchiver instance for use in archiving images and attachments for a page
    """
    def __init__(self, urls: Dict[str, str], http_client: HttpHelper):
        self.api_urls = urls
        self._asset_map = {
            'images': self._create_image_map,
            'attachments': self._create_attachment_map
        }
        self.http_client = http_client

    def get_asset_nodes(self, asset_type: str) -> Dict[int, List[ImageNode | AttachmentNode]]:
        """Get image or attachment helpers for a page (paginated to cover all assets)."""
        asset_json = self.http_client.http_get_all(self.api_urls[asset_type])
        return self._asset_map[asset_type](asset_json)

    def get_asset_data(self, asset_type: str,
            meta_data: Union[AttachmentNode, ImageNode]) -> Dict[str, str | bool | int | dict]:
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
        return asset_data

    def update_asset_links(self, asset_type: str, page_name: str, page_data: bytes,
            asset_nodes: List[ImageNode | AttachmentNode]) -> bytes:
        """Update markdown links in page data using literal bytes.replace."""
        url_map = self._build_url_map(asset_type, page_name, asset_nodes, kind="markdown")
        return self._apply_url_substitutions(page_data, url_map)

    def update_asset_links_html(self, asset_type: str, page_name: str, page_data: bytes,
            asset_nodes: List[ImageNode | AttachmentNode]) -> bytes:
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

        def _add_url(url: str, local_path: str) -> None:
            """Add URL and its HTML entity-encoded form — bs4 decodes &amp; to & but
            raw page bytes may still contain &amp;, causing bytes.replace to miss."""
            matched_urls[url] = local_path
            escaped = html.escape(url, quote=False)
            if escaped != url:
                matched_urls[escaped] = local_path

        # Anchor-wrapped images: check img src and parent href
        for img in soup.find_all("img", src=True):
            src = img["src"]
            if src in url_map:
                _add_url(src, url_map[src])
            parent = img.parent
            if parent and parent.name == "a":
                href = parent.get("href", "")
                if href in url_map:
                    _add_url(href, url_map[href])
        # Catch-all for attachments and any anchor-wrapped image hrefs not captured above.
        # Dict assignment is idempotent for hrefs already seen in the img-parent branch.
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if href in url_map:
                _add_url(href, url_map[href])
        return self._apply_url_substitutions(page_data, matched_urls)

    def _build_url_map(self, asset_type: str, page_name: str,
            asset_nodes: List[ImageNode | AttachmentNode],
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
                if url:
                    url_map[url] = local_path
        return url_map

    @staticmethod
    def _apply_url_substitutions(page_data: bytes, url_map: dict[str, str]) -> bytes:
        """Apply literal bytes.replace substitutions for each URL in url_map.

        Logs debug when a URL has zero matches in page_data (silent-miss surface).
        """
        # Sort by URL length descending so longer/more-specific URLs replace first.
        # Prevents shorter URLs that are substrings of longer ones from corrupting
        # subsequent matches.
        for url, local_path in sorted(url_map.items(), key=lambda item: len(item[0]), reverse=True):
            if not url:
                # bytes.replace(b"", ...) inserts replacement between every byte —
                # guard here even though _build_url_map already filters empties.
                continue
            url_bytes = url.encode()
            # isEnabledFor short-circuits the `not in` scan when debug is off,
            # avoiding a redundant O(n) pass before replace() runs.
            if log.isEnabledFor(logging.DEBUG) and url_bytes not in page_data:
                log.debug("URL has zero matches in page data (no substitution made): %s", url)
            page_data = page_data.replace(url_bytes, local_path.encode())
        return page_data

    @staticmethod
    def _create_image_map(json_data: Dict[str,
            List[Dict[str, str | int | bool | dict]]]) -> Dict[int, List[ImageNode]]:
        image_page_map = {}
        for img_meta in json_data:
            img_node = ImageNode(img_meta)
            if img_node.page_id in image_page_map:
                image_page_map[img_node.page_id].append(img_node)
            else:
                image_page_map[img_node.page_id] = [img_node]
        return image_page_map

    def _create_attachment_map(self,
            json_data: Dict[str, List[Dict[str, str | int | bool | dict]]]) -> Dict[int, List[AttachmentNode]]:
        asset_nodes = {}
        for asset_meta in json_data:
            asset_node = None
            if asset_meta['external']:
                continue # skip external link, only get attachments
            asset_node = AttachmentNode(asset_meta, self.api_urls['attachments'])
            if asset_node.page_id in asset_nodes:
                asset_nodes[asset_node.page_id].append(asset_node)
            else:
                asset_nodes[asset_node.page_id] = [asset_node]
        return asset_nodes

    @staticmethod
    def _decode_attachment_data(b64encoded_data: str) -> bytes:
        """decode base64 encoded data"""
        asset_data = b64encoded_data.encode()
        return base64.b64decode(asset_data)
