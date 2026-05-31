# pylint: disable=missing-class-docstring,missing-function-docstring
# pylint: disable=redefined-outer-name,protected-access
"""Unit tests for AssetArchiver markdown link-rewrite behavior (Phase 0 + Phase 1)."""
import logging

import pytest

from bookstack_file_exporter.archiver.asset_archiver import (
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

        Models the upstream contract: PageArchiver.archive_pages drops failed-asset
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
    with pytest.raises(ValueError, match="unsupported asset type"):
        asset_archiver.get_asset_bytes("widgets", "https://wiki.example.com/x")
