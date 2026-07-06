# pylint: disable=missing-class-docstring,missing-function-docstring
# pylint: disable=redefined-outer-name,protected-access
"""Unit tests for AssetArchiver markdown link-rewrite behavior (Phase 0 + Phase 1)."""
import logging
from unittest.mock import MagicMock

import pytest
from requests.exceptions import HTTPError, RetryError

from bookstack_file_exporter.archiver.asset_archiver import (
    AssetDecodeError,
    AttachmentNode,
    ImageNode,
)


# ---------------------------------------------------------------------------
# Phase 0 — baseline: existing _modify_markdown behavior
# ---------------------------------------------------------------------------

class TestPhase0BaselineMd:
    """Anchor existing markdown behavior before any rename."""

    def test_update_asset_links_rewrites_url_in_page_data(
        self, asset_archiver, image_node, image_api_content
    ):
        """update_asset_links should replace the image markdown URL with the local path."""
        # The fixture markdown: [![alt](INNER_URL)](OUTER_URL)
        # existing code extracts the INNER url (first parenthesis group)
        inner_url = (
            "https://wiki.example.com/uploads/images/gallery/2024-01/"
            "scaled-1680-/screenshot.png"
        )
        page_data = (
            b"Some text\n"
            b"[![screenshot]("
            + inner_url.encode()
            + b")](https://wiki.example.com/uploads/images/gallery/2024-01/screenshot.png)\n"
            b"More text\n"
        )

        asset_archiver.http_client.http_get_request.return_value.json.return_value = (
            image_api_content
        )

        result = asset_archiver.update_asset_links("images", "my-page", page_data, [image_node])

        local_path = image_node.get_relative_path("my-page").encode()
        assert local_path in result
        assert inner_url.encode() not in result

    def test_update_asset_links_noop_when_no_markdown_content(
        self, asset_archiver, image_node
    ):
        """update_asset_links should not modify page_data when asset has no markdown content."""
        # Provide asset_data with no content key
        asset_archiver.http_client.http_get_request.return_value.json.return_value = {
            "id": 42,
            "name": "screenshot.png",
        }

        original = b"No image links here."
        result = asset_archiver.update_asset_links("images", "my-page", original, [image_node])
        assert result == original

    def test_update_asset_links_rewrites_only_urls_from_passed_nodes(
        self, asset_archiver, image_node, image_api_content
    ):
        """Filtered-out (failed) assets stay in page_data; passed assets get rewritten.

        Models the upstream contract: PageArchiver.archive drops failed-asset
        nodes from page_images before calling update_asset_links. Only the URLs
        of the surviving (passed) nodes should be rewritten — URLs of dropped
        nodes must remain untouched.
        """
        success_url = (
            "https://wiki.example.com/uploads/images/gallery/2024-01/"
            "scaled-1680-/screenshot.png"
        )
        failed_url = (
            "https://wiki.example.com/uploads/images/gallery/2024-01/failed-image.png"
        )
        page_data = (
            b"[![ok](" + success_url.encode() + b")]"
            b"(https://wiki.example.com/uploads/images/gallery/2024-01/screenshot.png)\n"
            b"[![bad](" + failed_url.encode() + b")](" + failed_url.encode() + b")"
        )

        # image_node corresponds to success_url; the "failed" node is never passed in.
        asset_archiver.http_client.http_get_request.return_value.json.return_value = (
            image_api_content
        )

        result = asset_archiver.update_asset_links(
            "images", "my-page", page_data, [image_node]
        )

        # Passed node's URLs rewritten to local path
        assert success_url.encode() not in result
        assert b"images/my-page/screenshot.png" in result
        # Filtered node's URL must remain — never reached the substitution loop
        assert failed_url.encode() in result


# ---------------------------------------------------------------------------
# Phase 1 — md path fixes
# ---------------------------------------------------------------------------

class TestPhase1MdFixes:
    """Tests for _get_md_url_strs returning both inner and outer URLs."""

    def test_get_md_url_strs_returns_both_urls_from_anchor_wrapped(
        self, image_api_content
    ):
        """_get_md_url_strs should return both inner src and outer href from [![alt](INNER)](OUTER).
        """
        result = ImageNode._get_md_url_strs(image_api_content)
        assert len(result) == 2
        assert (
            "https://wiki.example.com/uploads/images/gallery/2024-01/"
            "scaled-1680-/screenshot.png"
        ) in result
        assert (
            "https://wiki.example.com/uploads/images/gallery/2024-01/screenshot.png"
        ) in result

    def test_get_md_url_strs_anchor_wrapped_order_outer_then_inner(
        self, image_api_content
    ):
        """Token walk on [![alt](INNER)](OUTER) yields link_open(href=OUTER) before
        image(src=INNER), so the result order must be [OUTER, INNER]."""
        outer_url = (
            "https://wiki.example.com/uploads/images/gallery/2024-01/screenshot.png"
        )
        inner_url = (
            "https://wiki.example.com/uploads/images/gallery/2024-01/"
            "scaled-1680-/screenshot.png"
        )
        result = ImageNode._get_md_url_strs(image_api_content)
        assert result == [outer_url, inner_url]

    def test_get_md_url_strs_attachment_returns_url(self, attachment_api_content):
        """_get_md_url_strs on attachment should return the href URL."""
        result = AttachmentNode._get_md_url_strs(attachment_api_content)
        assert "https://wiki.example.com/attachments/99" in result
        assert len(result) == 1

    def test_get_md_url_strs_empty_when_no_content(self):
        """_get_md_url_strs returns empty list when asset_data has no markdown content."""
        result = ImageNode._get_md_url_strs({})
        assert not result

    def test_get_md_url_strs_handles_url_with_parentheses(self):
        """_get_md_url_strs must extract URLs containing balanced parentheses.
        The old regex ([^)]+) would truncate these; markdown-it-py handles them correctly."""
        asset_data = {
            "content": {
                "markdown": "![diagram](https://en.wikipedia.org/wiki/Foo_(bar))"
            }
        }
        result = ImageNode._get_md_url_strs(asset_data)
        assert "https://en.wikipedia.org/wiki/Foo_(bar)" in result

    def test_update_asset_links_replaces_url_with_special_chars(
        self, asset_archiver, image_node
    ):
        """update_asset_links (bytes.replace) correctly handles URLs with ?query, ., +."""
        url_with_query = "https://wiki.example.com/img/photo.jpg?width=200&scale=1.5"
        page_data = b"Check: ![img](" + url_with_query.encode() + b")"

        asset_data = {
            "id": 42,
            "content": {
                "markdown": f"![img]({url_with_query})"
            }
        }
        asset_archiver.http_client.http_get_request.return_value.json.return_value = asset_data

        result = asset_archiver.update_asset_links("images", "my-page", page_data, [image_node])
        # The URL with ? . + should have been replaced literally (not as regex)
        local_path = image_node.get_relative_path("my-page").encode()
        assert local_path in result
        assert url_with_query.encode() not in result

    def test_update_asset_links_rewrites_both_urls_from_anchor_wrapped_md(
        self, asset_archiver, image_node, image_api_content
    ):
        """update_asset_links should rewrite both inner and outer URLs from anchor-wrapped
        markdown."""
        inner_url = (
            "https://wiki.example.com/uploads/images/gallery/2024-01/"
            "scaled-1680-/screenshot.png"
        )
        outer_url = (
            "https://wiki.example.com/uploads/images/gallery/2024-01/screenshot.png"
        )
        page_data = (
            b"[![screenshot]("
            + inner_url.encode()
            + b")]("
            + outer_url.encode()
            + b")"
        )

        asset_archiver.http_client.http_get_request.return_value.json.return_value = (
            image_api_content
        )

        result = asset_archiver.update_asset_links("images", "my-page", page_data, [image_node])
        local_path = image_node.get_relative_path("my-page").encode()

        assert inner_url.encode() not in result
        assert outer_url.encode() not in result
        assert local_path in result

    def test_update_asset_links_rewrites_outer_anchor_when_content_only_has_scaled_url(
        self, asset_archiver, image_node
    ):
        """_build_url_map includes page_url so full-res anchor href gets rewritten even when
        content.markdown only contains the simple (scaled-only) image form."""
        scaled_url = (
            "https://wiki.example.com/uploads/images/gallery/2024-01/"
            "scaled-1680-/screenshot.png"
        )
        full_res_url = (
            "https://wiki.example.com/uploads/images/gallery/2024-01/screenshot.png"
        )

        # API content.markdown has ONLY the scaled URL — no anchor wrap
        asset_data_scaled_only = {
            "id": 42,
            "content": {
                "markdown": f"![Screenshot]({scaled_url})"
            }
        }
        asset_archiver.http_client.http_get_request.return_value.json.return_value = (
            asset_data_scaled_only
        )

        # Page export produces anchor-wrapped form with both URLs
        page_data = (
            b"[![alt]("
            + scaled_url.encode()
            + b")]("
            + full_res_url.encode()
            + b")"
        )

        result = asset_archiver.update_asset_links("images", "test-page", page_data, [image_node])

        assert scaled_url.encode() not in result
        assert full_res_url.encode() not in result
        assert b"images/test-page/screenshot.png" in result

    def test_update_asset_links_logs_debug_on_zero_match(
        self, asset_archiver, image_node, caplog
    ):
        """update_asset_links should log debug when a URL has zero matches in page_data."""
        asset_data = {
            "id": 42,
            "content": {
                "markdown": "![img](https://wiki.example.com/img/nonexistent.png)"
            }
        }
        asset_archiver.http_client.http_get_request.return_value.json.return_value = asset_data
        page_data = b"This page has no image references."

        logger_name = "bookstack_file_exporter.archiver.asset_archiver"
        with caplog.at_level(logging.DEBUG, logger=logger_name):
            asset_archiver.update_asset_links("images", "my-page", page_data, [image_node])

        assert any("no substitution" in r.message.lower()
                   for r in caplog.records if r.levelno == logging.DEBUG)


def test_get_asset_bytes_unknown_type_raises_valueerror(asset_archiver):
    # ValueError fires before the node is touched, so any object works as arg 2.
    with pytest.raises(ValueError, match="unsupported asset type"):
        asset_archiver.get_asset_bytes("widgets", MagicMock())


def test_create_attachment_map_skips_external(asset_archiver):
    json_data = [
        {"id": 1, "uploaded_to": 7, "name": "a.pdf", "external": False},
        {"id": 2, "uploaded_to": 7, "name": "ext", "external": True},
        {"id": 3, "uploaded_to": 9, "name": "b.pdf", "external": False},
    ]
    result = asset_archiver._create_attachment_map(json_data)
    assert set(result.keys()) == {7, 9}
    assert [n.id_ for n in result[7]] == [1]


def test_create_image_map_groups_by_page(asset_archiver):
    json_data = [
        {"id": 1, "uploaded_to": 7, "url": "https://x/a.png"},
        {"id": 2, "uploaded_to": 7, "url": "https://x/b.png"},
    ]
    result = asset_archiver._create_image_map(json_data)
    assert [n.id_ for n in result[7]] == [1, 2]


@pytest.mark.parametrize("response_setup", [
    {"json.side_effect": ValueError("Expecting value")},  # non-JSON body
    {"json.return_value": {"name": "x"}},                 # missing 'content'
    {"json.return_value": {"content": None}},             # content not a string
    {"json.return_value": {"content": "AAA"}},            # bad base64 padding
])
def test_get_asset_bytes_attachment_decode_failure_raises_asset_decode_error(
        asset_archiver, response_setup):
    response = MagicMock()
    response.configure_mock(**response_setup)
    asset_archiver.http_client.http_get_request.return_value = response
    node = MagicMock(spec=AttachmentNode)
    node.download_url = "https://wiki.example.com/api/attachments/6"
    with pytest.raises(AssetDecodeError):
        asset_archiver.get_asset_bytes("attachments", node)


# ---------------------------------------------------------------------------
# Issue #145 — legacy-first image fetch with authenticated image-data API
# fallback + defense-in-depth login/HTML detection.
# ---------------------------------------------------------------------------

def _make_response(content: bytes, history=None, url: str = "") -> MagicMock:
    """Build a minimal Response-like mock for image-fetch assertions."""
    response = MagicMock()
    response.content = content
    response.history = history if history is not None else []
    response.url = url
    return response


def _make_http_error(status_code: int) -> HTTPError:
    """Build an HTTPError carrying a .response with the given status_code."""
    error = HTTPError(f"{status_code} error")
    error.response = MagicMock(status_code=status_code)
    return error


class TestGetImageBytesLegacyFirst:
    """Legacy-first fetch with authenticated /data recovery on login/HTML."""

    def test_saved_filename_derives_from_content_url_not_data_route(
            self, asset_archiver, image_node):
        """ImageNode.name/get_relative_path come from the gallery content URL
        (set at construction) regardless of which URL bytes were fetched from
        — the '/data' fetch route must never leak into the saved filename."""
        asset_archiver.http_client.http_get_request.return_value = _make_response(
            b"real_png_bytes")

        asset_archiver.get_asset_bytes("images", image_node)

        assert image_node.name == "screenshot.png"
        relative_path = image_node.get_relative_path("my-page")
        assert relative_path == "images/my-page/screenshot.png"
        assert not relative_path.endswith("data")

    def test_public_image_uses_legacy_url_only(self, asset_archiver, image_node):
        """Public image (STORAGE_IMAGE_TYPE local/s3): legacy 200s with real
        bytes, so the /data API is never requested."""
        asset_archiver.http_client.http_get_request.return_value = _make_response(
            b"real_png_bytes")

        result = asset_archiver.get_asset_bytes("images", image_node)

        assert result == b"real_png_bytes"
        asset_archiver.http_client.http_get_request.assert_called_once_with(
            image_node.download_url)

    def test_secure_image_login_html_falls_back_to_data_api(
            self, asset_archiver, image_node):
        """The #145 fix: legacy redirects a secure image to a login page
        (HTML body); the detector raises AssetDecodeError internally and the
        authenticated /data API recovers the real bytes."""
        login_response = _make_response(b"<!DOCTYPE html><html>login</html>")
        api_response = _make_response(b"real_bytes_from_api")
        asset_archiver.http_client.http_get_request.side_effect = [
            login_response, api_response,
        ]

        result = asset_archiver.get_asset_bytes("images", image_node)

        assert result == b"real_bytes_from_api"
        calls = asset_archiver.http_client.http_get_request.call_args_list
        assert calls[0].args[0] == image_node.download_url
        assert calls[1].args[0] == f"{asset_archiver.api_urls['images']}/{image_node.id_}/data"

    def test_secure_image_login_redirect_falls_back_to_data_api(
            self, asset_archiver, image_node):
        """Rule (b) path: legacy 200s with non-HTML-looking bytes but the
        request was redirected to /login — still triggers the /data fallback."""
        redirect_response = _make_response(
            b"not html, not empty",
            history=[MagicMock()],
            url="https://wiki.example.com/login?intended=%2Fx",
        )
        api_response = _make_response(b"real_bytes_from_api")
        asset_archiver.http_client.http_get_request.side_effect = [
            redirect_response, api_response,
        ]

        result = asset_archiver.get_asset_bytes("images", image_node)

        assert result == b"real_bytes_from_api"
        calls = asset_archiver.http_client.http_get_request.call_args_list
        assert calls[0].args[0] == image_node.download_url
        assert calls[1].args[0] == f"{asset_archiver.api_urls['images']}/{image_node.id_}/data"

    def test_missing_image_legacy_404_propagates_without_api_fallback(
            self, asset_archiver, image_node):
        """A deleted/missing image (legacy 404) must fail cleanly — no
        wasteful detour into the /data API on a non-login error."""
        asset_archiver.http_client.http_get_request.side_effect = _make_http_error(404)

        with pytest.raises(HTTPError):
            asset_archiver.get_asset_bytes("images", image_node)

        asset_archiver.http_client.http_get_request.assert_called_once_with(
            image_node.download_url)

    def test_transient_legacy_5xx_propagates_without_api_fallback(
            self, asset_archiver, image_node):
        """A transient legacy RetryError must propagate — not trigger the
        /data fallback (that's reserved for the login/HTML signal only)."""
        asset_archiver.http_client.http_get_request.side_effect = RetryError("max retries")

        with pytest.raises(RetryError):
            asset_archiver.get_asset_bytes("images", image_node)

        asset_archiver.http_client.http_get_request.assert_called_once_with(
            image_node.download_url)

    def test_secure_image_on_pre_v25_11_data_api_404s_and_propagates(
            self, asset_archiver, image_node):
        """Secure image on a pre-v25.11 instance: legacy login-HTML triggers
        the fallback attempt, but /data 404s there too (route doesn't exist
        yet) -> propagates -> caller marks the run PARTIAL."""
        login_response = _make_response(b"<!DOCTYPE html><html>login</html>")
        asset_archiver.http_client.http_get_request.side_effect = [
            login_response, _make_http_error(404),
        ]

        with pytest.raises(HTTPError):
            asset_archiver.get_asset_bytes("images", image_node)

        calls = asset_archiver.http_client.http_get_request.call_args_list
        assert len(calls) == 2
        assert calls[1].args[0] == f"{asset_archiver.api_urls['images']}/{image_node.id_}/data"

    def test_data_api_also_returns_login_html_raises_asset_decode_error(
            self, asset_archiver, image_node):
        """Defense-in-depth: if the /data recovery attempt also comes back as
        login/HTML (e.g. an odd proxy), AssetDecodeError propagates -> PARTIAL."""
        login_response = _make_response(b"<!DOCTYPE html><html>login</html>")
        also_login_response = _make_response(b"<!DOCTYPE html><html>login2</html>")
        asset_archiver.http_client.http_get_request.side_effect = [
            login_response, also_login_response,
        ]

        with pytest.raises(AssetDecodeError):
            asset_archiver.get_asset_bytes("images", image_node)


class TestValidateImageResponse:
    """C. Defense-in-depth detector."""

    def test_ignores_mislabeled_content_type_header(self, asset_archiver):
        """Content-Type is not a trigger: a proxy/CDN can mislabel correct
        image bytes as text/html."""
        response = _make_response(b"\x89PNG\r\n\x1a\nrest-of-real-png-bytes")
        response.headers = {"Content-Type": "text/html"}

        result = asset_archiver._validate_image_response(response)

        assert result == response.content

    @pytest.mark.parametrize("body", [
        b"<!DOCTYPE html><html><body>login</body></html>",
        b"<html><head></head><body>login</body></html>",
        b"   <!DOCTYPE html><html></html>",
        b"  <HTML><body>login</body></html>",
    ])
    def test_rejects_html_body(self, asset_archiver, body):
        response = _make_response(body)
        with pytest.raises(AssetDecodeError):
            asset_archiver._validate_image_response(response)

    def test_rejects_html_body_with_leading_utf8_bom(self, asset_archiver):
        """bytes.lstrip() strips ASCII whitespace but not a leading UTF-8 BOM
        (\\xef\\xbb\\xbf); the marker check must strip it first so a
        BOM-prefixed login page is still detected as HTML."""
        response = _make_response(b"\xef\xbb\xbf<!DOCTYPE html><html>login</html>")
        with pytest.raises(AssetDecodeError):
            asset_archiver._validate_image_response(response)

    def test_rejects_redirect_to_login_path_with_query_string(self, asset_archiver):
        """BookStack redirects to /login?intended=..., so the check must parse
        the URL (urlparse) rather than naive endswith('/login')."""
        response = _make_response(
            b"not html, not empty",
            history=[MagicMock()],
            url="https://wiki.example.com/login?intended=%2Fx",
        )
        with pytest.raises(AssetDecodeError):
            asset_archiver._validate_image_response(response)

    def test_login_suffixed_url_without_redirect_history_is_not_flagged(
            self, asset_archiver):
        """Redirect evidence (response.history) is required — a URL that merely
        ends in /login with no redirect history is not corruption."""
        response = _make_response(
            b"not html, not empty", history=[], url="https://wiki.example.com/login")

        result = asset_archiver._validate_image_response(response)

        assert result == response.content

    @pytest.mark.parametrize("body", [
        b"RIFF\x00\x00\x00\x00WEBPVP8 \x00\x00\x00\x00",
        b"\x00\x00\x00\x20ftypavif\x00\x00\x00\x00",
    ])
    def test_accepts_non_png_jpeg_formats_deny_list_not_allow_list(self, asset_archiver, body):
        """Deny-list, not an image-magic allowlist: newer gallery formats
        (webp/avif) must pass through untouched."""
        response = _make_response(body)

        result = asset_archiver._validate_image_response(response)

        assert result == body
