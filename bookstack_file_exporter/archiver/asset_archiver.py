from __future__ import annotations

import logging
import re
import base64
import binascii
from typing import Literal
from urllib.parse import urlparse

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

# Matches BookStack's scaled-thumbnail path segment, e.g. /scaled-1680-/ or /scaled-300-/.
# Used to strip the scaled variant back to the canonical URL for url_map lookup.
_SCALED_RE = re.compile(r'/scaled-\d+-/')


class AssetDecodeError(Exception):
    """Attachment payload did not match the documented base64-JSON shape.

    Raised instead of letting KeyError/JSONDecodeError/binascii.Error escape:
    those builtins are ambiguous (they could equally be our own bug), while
    this type means specifically "the server sent something we cannot decode",
    so callers can treat it exactly like a failed download (skip the asset ->
    PARTIAL) without a broad except masking real defects. Also covers an image
    fetch that returned login-page/HTML instead of image bytes (issue #145).
    """


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
            self, asset_data: dict[str, int | str | bool | dict],
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
    def _walk_md_urls(md_str: str) -> list[str]:
        """Walk markdown-it-py tokens and return all image src and link href values.

        Uses markdown-it-py for spec-compliant parsing — handles URLs with
        parentheses and alt-text containing parens without regex brittleness.

        Token shapes:
          `image` = single self-contained token for a markdown image.
            markdown: ![alt](URL)
            tokens:   image(src=URL, alt=alt)

          `link_open` = opening half of a link pair; text and link_close follow.
          We only need the opener's href; link_close has no attrs.
            markdown: [text](URL)
            tokens:   link_open(href=URL), text("text"), link_close

          For BookStack's anchor-wrapped image (click-to-zoom) shape, both
          branches fire on the same construct:
            markdown: [![alt](inner)](outer)
            tokens:   link_open(href=outer), image(src=inner), link_close
            result:   [outer, inner]

          Attachments don't normally render as images, but links.markdown is
          user-controllable so the image branch is handled defensively.
        """
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
    def _get_md_url_strs(asset_data: dict[str, int | str]) -> list[str]:
        """Extract image src and link href values from content.markdown.
        Uses markdown-it-py for spec-compliant parsing — handles URLs with
        parentheses and alt-text containing parens without regex brittleness."""
        md_str = ""
        if 'content' in asset_data and 'markdown' in asset_data.get('content', {}):
            md_str = asset_data['content']['markdown']
        return AssetNode._walk_md_urls(md_str)

    @staticmethod
    def _get_html_url_strs(asset_data: dict[str, int | str]) -> list[str]:
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
    def __init__(self, meta_data: dict[str, int | str]):
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
    def __init__(self, meta_data: dict[str, int | str | bool],
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
        return AssetNode._walk_md_urls(md_str)

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
            meta_data: AttachmentNode | ImageNode) -> dict[str, str | bool | int | dict]:
        """Get asset data based on type"""
        data_url = f"{self.api_urls[asset_type]}/{meta_data.id_}"
        asset_data_response: Response = self.http_client.http_get_request(
            data_url)
        return asset_data_response.json()

    def get_asset_bytes(self, asset_type: str,
            node: ImageNode | AttachmentNode) -> bytes:
        """Get raw asset bytes for one node.

        Images are fetched via their legacy /uploads/... URL first, falling back
        to the authenticated image-data API only on a login/HTML response (see
        _get_image_bytes); attachments use their base64-JSON API route.
        """
        match asset_type:
            case "images":
                return self._get_image_bytes(node)
            case "attachments":
                response = self.http_client.http_get_request(node.download_url)
                return self._decode_attachment_response(response)
            case _:
                raise ValueError(f"unsupported asset type: {asset_type}")

    def _get_image_bytes(self, node: ImageNode) -> bytes:
        """Fetch image bytes: legacy web URL first, authenticated API as recovery.

        The legacy /uploads/... URL is served directly by the web tier for public
        images (STORAGE_IMAGE_TYPE local or s3) — fast, and the only route that
        reaches an image stranded in the non-current storage dir on a migrated
        instance. A SECURE image (local_secure / local_secure_restricted) instead
        302-redirects that URL to /login and returns login HTML;
        _validate_image_response catches that (AssetDecodeError) and we recover the
        real bytes from the authenticated image-data API (GET .../{id}/data,
        BookStack v25.11+).

        The API fallback fires ONLY on that login/HTML signal, never on a legacy
        HTTPError/RetryError: a missing image (404) or a transient legacy 5xx must
        fail cleanly to a skipped asset (-> PARTIAL), not detour into /data and its
        retry ladder. Secure images always surface as login HTML, so narrowing the
        trigger loses no coverage. On a pre-v25.11 instance the /data recovery 404s
        -> propagates -> PARTIAL (secure images are unfetchable there by any route).
        """
        try:
            return self._validate_image_response(
                self.http_client.http_get_request(node.download_url))
        except AssetDecodeError:
            api_url = f"{self.api_urls['images']}/{node.id_}/data"
            return self._validate_image_response(
                self.http_client.http_get_request(api_url))

    @staticmethod
    def _validate_image_response(response: Response) -> bytes:
        """Return image bytes, or raise AssetDecodeError on login/HTML corruption.

        Deny-list, NOT an image-magic allowlist: BookStack's accepted gallery
        formats (jpeg/png/gif/webp/avif) change over time, so an allowlist would
        flag healthy new formats. Reject only the specific #145 corruption — a
        login page / HTML served instead of image bytes:
          (a) body starts with <!doctype or <html (no image format starts '<');
          (b) the request was redirected (response.history) to a URL whose path
              ends /login — parsed via urlparse because BookStack redirects to
              /login?intended=... and a naive endswith('/login') would miss it.
        Content-Type is deliberately NOT a trigger: a proxy/CDN can mislabel
        correct image bytes as text/html. Runs on both API and legacy paths.
        """
        content = response.content
        # Strip a leading UTF-8 BOM before the marker check: bytes.lstrip() removes
        # ASCII whitespace but not the BOM (\xef\xbb\xbf), and this HTML-body rule is
        # now the primary signal that a secure image redirected to a login page.
        head = content.removeprefix(b"\xef\xbb\xbf").lstrip()
        if head[:9].lower().startswith((b"<!doctype", b"<html")):
            raise AssetDecodeError(
                "image response body is HTML (login page/error), not image bytes")
        if response.history and urlparse(response.url).path.endswith("/login"):
            raise AssetDecodeError(
                "image request was redirected to a login page, not image bytes")
        return content

    @staticmethod
    def _decode_attachment_response(response: Response) -> bytes:
        """Validate-then-decode the attachment payload ({'content': <base64 str>}).

        requests raises a ValueError subclass on a non-JSON body; b64decode
        raises binascii.Error on bad padding. Both, plus a missing/mistyped
        'content' field, become AssetDecodeError so one malformed attachment is
        skipped (-> failed_assets -> PARTIAL) instead of aborting the export.
        """
        try:
            payload = response.json()
        except ValueError as exc:
            raise AssetDecodeError(f"attachment response is not JSON: {exc}") from exc
        content = payload.get('content') if isinstance(payload, dict) else None
        if not isinstance(content, str):
            raise AssetDecodeError(
                "attachment response has no base64 string 'content' field")
        try:
            return base64.b64decode(content.encode())
        except binascii.Error as exc:
            raise AssetDecodeError(
                f"attachment 'content' is not valid base64: {exc}") from exc

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

        # Anchor-wrapped images: three-branch src resolution + parent href.
        for img in soup.find_all("img", src=True):
            src = img["src"]
            # Compute parent anchor once; shared by branch 1 (base64 reuse) and
            # the href-localization pass below.
            parent = img.parent
            href = parent.get("href", "") if parent and parent.name == "a" else ""
            if src.startswith("data:"):
                # Branch 1: base64 inline. If the wrapping anchor's href is a downloaded
                # asset, slim the blob by reusing that file (BookStack click-to-zoom:
                # the inline img IS the anchor's image). Bare base64 left inline.
                if href in url_map:
                    matched_urls[src] = url_map[href]
            elif src in url_map:
                # Branch 2: src is already the canonical URL — direct hit.
                matched_urls[src] = url_map[src]
            else:
                # Branch 3: src carries a scaled segment (e.g. /scaled-1680-/).
                # Strip it to recover the canonical URL and retry the lookup.
                # We never construct a scaled URL — constructing a key could
                # silently mis-match; stripping can only fail to match, never corrupt.
                canonical = _SCALED_RE.sub('/', src)
                if canonical in url_map:
                    matched_urls[src] = url_map[canonical]
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
                # bytes.replace(b"", local_path) inserts the replacement between
                # every byte of the page, silently destroying the whole document.
                # Redundant while every url_map producer filters empties (it does),
                # but kept as cheap defense against a future key that bypasses them.
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
    def _group_by_page(nodes: list[ImageNode | AttachmentNode]
                       ) -> dict[int, list[ImageNode | AttachmentNode]]:
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
