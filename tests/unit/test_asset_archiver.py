# pylint: disable=missing-function-docstring,redefined-outer-name,protected-access
"""Unit tests for AssetArchiver, ImageNode, and AttachmentNode."""
import json
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from bookstack_file_exporter.archiver.asset_archiver import (
    AssetArchiver,
    AssetNode,
    AttachmentNode,
    ImageNode,
)
from bookstack_file_exporter.common.util import HttpHelper

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _load_json(name: str) -> dict:
    with open(FIXTURES_DIR / name, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _load_bytes(name: str) -> bytes:
    with open(FIXTURES_DIR / name, "rb") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def image_api_content():
    return _load_json("api_image_content.json")


@pytest.fixture
def attachment_api_content():
    return _load_json("api_attachment_content.json")


@pytest.fixture
def html_anchor_wrapped_page():
    return _load_bytes("html_page_anchor_wrapped_image.html")


@pytest.fixture
def html_attachment_page():
    return _load_bytes("html_page_attachment.html")


@pytest.fixture
def image_node():
    meta = {
        "id": 42,
        "uploaded_to": 7,
        "url": "https://wiki.example.com/uploads/images/gallery/2024-01/screenshot.png",
    }
    return ImageNode(meta)


@pytest.fixture
def attachment_node():
    meta = {
        "id": 99,
        "uploaded_to": 7,
        "name": "project-spec.pdf",
        "external": False,
    }
    return AttachmentNode(meta, "https://wiki.example.com/attachments")


@pytest.fixture
def asset_archiver():
    urls = {
        "images": "https://wiki.example.com/api/image-gallery",
        "attachments": "https://wiki.example.com/api/attachments",
    }
    http_client = MagicMock()
    return AssetArchiver(urls, http_client)


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
        inner_url = "https://wiki.example.com/uploads/images/gallery/2024-01/scaled-1680-/screenshot.png"
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
        """_get_md_url_strs should return both inner src and outer href from [![alt](INNER)](OUTER)."""
        result = ImageNode._get_md_url_strs(image_api_content)
        assert len(result) == 2
        assert "https://wiki.example.com/uploads/images/gallery/2024-01/scaled-1680-/screenshot.png" in result
        assert "https://wiki.example.com/uploads/images/gallery/2024-01/screenshot.png" in result

    def test_get_md_url_strs_attachment_returns_url(self, attachment_api_content):
        """_get_md_url_strs on attachment should return the href URL."""
        result = AttachmentNode._get_md_url_strs(attachment_api_content)
        assert "https://wiki.example.com/attachments/99" in result
        assert len(result) == 1

    def test_get_md_url_strs_empty_when_no_content(self):
        """_get_md_url_strs returns empty list when asset_data has no markdown content."""
        result = ImageNode._get_md_url_strs({})
        assert result == []

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
        """update_asset_links should rewrite both inner and outer URLs from anchor-wrapped markdown."""
        inner_url = "https://wiki.example.com/uploads/images/gallery/2024-01/scaled-1680-/screenshot.png"
        outer_url = "https://wiki.example.com/uploads/images/gallery/2024-01/screenshot.png"
        page_data = (
            b"[![screenshot]("
            + inner_url.encode()
            + b")]("
            + outer_url.encode()
            + b")"
        )

        asset_archiver.http_client.http_get_request.return_value.json.return_value = image_api_content

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
        scaled_url = "https://wiki.example.com/uploads/images/gallery/2024-01/scaled-1680-/screenshot.png"
        full_res_url = "https://wiki.example.com/uploads/images/gallery/2024-01/screenshot.png"

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
        import logging
        asset_data = {
            "id": 42,
            "content": {
                "markdown": "![img](https://wiki.example.com/img/nonexistent.png)"
            }
        }
        asset_archiver.http_client.http_get_request.return_value.json.return_value = asset_data
        page_data = b"This page has no image references."

        with caplog.at_level(logging.DEBUG, logger="bookstack_file_exporter.archiver.asset_archiver"):
            asset_archiver.update_asset_links("images", "my-page", page_data, [image_node])

        assert any("zero" in r.message.lower() or "no match" in r.message.lower()
                   for r in caplog.records if r.levelno == logging.DEBUG)


# ---------------------------------------------------------------------------
# Phase 2 — Assets model + alias
# ---------------------------------------------------------------------------

class TestPhase2AssetsModel:
    """Tests for pydantic Assets model with modify_links / modify_markdown alias."""

    def test_assets_accepts_modify_links(self):
        from bookstack_file_exporter.config_helper.models import Assets
        assets = Assets(modify_links=True)
        assert assets.modify_links is True

    def test_assets_accepts_legacy_modify_markdown(self):
        from bookstack_file_exporter.config_helper.models import Assets
        assets = Assets(modify_markdown=True)
        assert assets.modify_links is True

    def test_assets_default_modify_links_is_false(self):
        from bookstack_file_exporter.config_helper.models import Assets
        assets = Assets()
        assert assets.modify_links is False

    def test_assets_modify_links_wins_when_both_keys_present(self):
        from bookstack_file_exporter.config_helper.models import Assets
        # modify_links=False should win over modify_markdown=True
        assets = Assets(**{"modify_links": False, "modify_markdown": True})
        assert assets.modify_links is False


class TestPhase2ConfigHelperDeprecationWarning:
    """Tests for deprecation warning in config_helper.py."""

    def _write_config(self, tmp_path, content: str) -> str:
        config_file = tmp_path / "config.yml"
        config_file.write_text(content)
        return str(config_file)

    def test_deprecation_warning_emitted_when_legacy_key_present(self, tmp_path, caplog):
        import logging
        import argparse
        from bookstack_file_exporter.config_helper.config_helper import ConfigNode

        config_content = """
host: https://wiki.example.com
credentials:
  token_id: abc
  token_secret: def
formats:
  - markdown
assets:
  modify_markdown: true
"""
        config_file = self._write_config(tmp_path, config_content)
        args = argparse.Namespace(config_file=config_file, output_dir=None)

        with caplog.at_level(logging.WARNING, logger="bookstack_file_exporter.config_helper.config_helper"):
            ConfigNode(args)

        warning_msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("DEPRECATED" in m and "modify_markdown" in m for m in warning_msgs)

    def test_deprecation_warning_emitted_exactly_once(self, tmp_path, caplog):
        import logging
        import argparse
        from bookstack_file_exporter.config_helper.config_helper import ConfigNode

        config_content = """
host: https://wiki.example.com
credentials:
  token_id: abc
  token_secret: def
formats:
  - markdown
assets:
  modify_markdown: true
"""
        config_file = self._write_config(tmp_path, config_content)
        args = argparse.Namespace(config_file=config_file, output_dir=None)

        with caplog.at_level(logging.WARNING, logger="bookstack_file_exporter.config_helper.config_helper"):
            ConfigNode(args)

        deprecation_warnings = [
            r for r in caplog.records
            if r.levelno == logging.WARNING and "DEPRECATED" in r.message
        ]
        assert len(deprecation_warnings) == 1

    def test_second_warning_when_both_keys_present_different_values(self, tmp_path, caplog):
        import logging
        import argparse
        from bookstack_file_exporter.config_helper.config_helper import ConfigNode

        config_content = """
host: https://wiki.example.com
credentials:
  token_id: abc
  token_secret: def
formats:
  - markdown
assets:
  modify_links: false
  modify_markdown: true
"""
        config_file = self._write_config(tmp_path, config_content)
        args = argparse.Namespace(config_file=config_file, output_dir=None)

        with caplog.at_level(logging.WARNING, logger="bookstack_file_exporter.config_helper.config_helper"):
            ConfigNode(args)

        warning_msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        # Should have the deprecation warning + ignored legacy warning
        assert len(warning_msgs) >= 2
        assert any("ignored" in m.lower() for m in warning_msgs)

    def test_check_legacy_modify_markdown_non_dict_assets_does_not_crash(self, caplog):
        """assets: true (or other non-dict) must not crash before pydantic validates."""
        from bookstack_file_exporter.config_helper.config_helper import ConfigNode
        import logging
        logger_name = "bookstack_file_exporter.config_helper.config_helper"
        with caplog.at_level(logging.WARNING, logger=logger_name):
            ConfigNode._check_legacy_modify_markdown({"assets": True})
            ConfigNode._check_legacy_modify_markdown({"assets": "bad_string"})
            ConfigNode._check_legacy_modify_markdown({"assets": 42})
        our_records = [r for r in caplog.records if r.name == logger_name]
        assert our_records == [], (
            f"non-dict assets must produce zero warnings from this logger; "
            f"got: {[r.message for r in our_records]}"
        )


# ---------------------------------------------------------------------------
# Phase 3 — HTML rewrite
# ---------------------------------------------------------------------------

class TestAllUrls:
    """Tests for AssetNode.all_urls() — pure extraction + canonical URL."""

    def test_image_all_urls_html_includes_outer_anchor_href(
        self, image_node, image_api_content
    ):
        """all_urls(kind='html') should include the outer anchor href."""
        urls = image_node.all_urls(image_api_content, "html")
        assert "https://wiki.example.com/uploads/images/gallery/2024-01/screenshot.png" in urls

    def test_image_all_urls_html_skips_base64_src(
        self, image_node, image_api_content
    ):
        """all_urls(kind='html') should NOT include data: URLs."""
        urls = image_node.all_urls(image_api_content, "html")
        assert not any(u.startswith("data:") for u in urls)

    def test_attachment_all_urls_html_extracts_href(
        self, attachment_node, attachment_api_content
    ):
        """all_urls(kind='html') on attachment should return the attachment href."""
        urls = attachment_node.all_urls(attachment_api_content, "html")
        assert "https://wiki.example.com/attachments/99" in urls

    def test_all_urls_always_includes_canonical_node_url(
        self, image_node, image_api_content
    ):
        """all_urls should include the full-res page URL even when content API omits it."""
        urls = image_node.all_urls(image_api_content, "html")
        assert "https://wiki.example.com/uploads/images/gallery/2024-01/screenshot.png" in urls

    def test_all_urls_markdown_returns_extracted_urls(
        self, image_node, image_api_content
    ):
        """all_urls(kind='markdown') should return URLs extracted from markdown content."""
        urls = image_node.all_urls(image_api_content, "markdown")
        assert "https://wiki.example.com/uploads/images/gallery/2024-01/scaled-1680-/screenshot.png" in urls

    def test_all_urls_returns_only_canonical_when_no_content(
        self, image_node
    ):
        """all_urls should return only the full-res URL when asset_data has no content key."""
        urls = image_node.all_urls({}, "html")
        assert urls == ["https://wiki.example.com/uploads/images/gallery/2024-01/screenshot.png"]

    def test_attachment_all_urls_empty_page_url_filtered_by_build_url_map(
        self, asset_archiver, attachment_node, attachment_api_content
    ):
        """AttachmentNode.page_url is '' — _build_url_map must not add it to the map."""
        asset_archiver.http_client.http_get_request.return_value.json.return_value = attachment_api_content
        url_map = asset_archiver._build_url_map("attachments", "my-page", [attachment_node], kind="html")
        assert "" not in url_map
        # Positive: the public attachment URL from links.html IS in the map
        assert "https://wiki.example.com/attachments/99" in url_map

    def test_attachment_all_urls_filters_empty_page_url_at_source(
        self, attachment_node, attachment_api_content
    ):
        """all_urls on AttachmentNode must not return '' — filtering happens inside all_urls."""
        urls = attachment_node.all_urls(attachment_api_content, "html")
        assert "" not in urls
        assert "https://wiki.example.com/attachments/99" in urls

    def test_attachment_all_urls_markdown_returns_extracted_url(
        self, attachment_node, attachment_api_content
    ):
        """all_urls(kind='markdown') on attachment should return the markdown href."""
        urls = attachment_node.all_urls(attachment_api_content, "markdown")
        assert "https://wiki.example.com/attachments/99" in urls


class TestPhase2HtmlPath:
    """Tests for _build_url_map behaviour in HTML mode."""

    def test_build_url_map_skips_api_call_for_image_nodes_in_html_mode(
        self, asset_archiver, image_node
    ):
        """ImageNode.page_url is known from listing data — no per-asset API call needed for HTML mode.

        Asserts both:
          (a) http_get_request was not called (no redundant API roundtrip), and
          (b) url_map content is exactly {page_url: local_path} — locks the contract
              that page_url is the only URL contributed for ImageNode in HTML mode.
        """
        # Stub json() so the current (unfixed) code runs cleanly and the assertion
        # isolates the "no HTTP call" contract rather than failing on MagicMock parsing.
        asset_archiver.http_client.http_get_request.return_value.json.return_value = {}

        # Directly exercise _build_url_map so we can assert on its return value.
        url_map = asset_archiver._build_url_map(
            "images", "my-page", [image_node], kind="html"
        )

        asset_archiver.http_client.http_get_request.assert_not_called()
        local_path = image_node.get_relative_path("my-page")
        assert url_map == {image_node.page_url: local_path}


class TestPhase3HtmlRewrite:
    """Tests for update_asset_links_html byte-exact replacement."""

    def test_update_asset_links_html_skips_when_empty_asset_nodes(
        self, asset_archiver, html_anchor_wrapped_page
    ):
        """update_asset_links_html should return page_data unchanged when asset_nodes is empty."""
        result = asset_archiver.update_asset_links_html(
            "images", "my-page", html_anchor_wrapped_page, []
        )
        assert result == html_anchor_wrapped_page

    def test_update_asset_links_html_rewrites_anchor_href(
        self, asset_archiver, image_node, image_api_content, html_anchor_wrapped_page
    ):
        """update_asset_links_html should rewrite outer anchor href to local path."""
        asset_archiver.http_client.http_get_request.return_value.json.return_value = image_api_content

        result = asset_archiver.update_asset_links_html(
            "images", "my-page", html_anchor_wrapped_page, [image_node]
        )
        outer_url = b"https://wiki.example.com/uploads/images/gallery/2024-01/screenshot.png"
        local_path = image_node.get_relative_path("my-page").encode()

        assert outer_url not in result
        assert local_path in result

    def test_update_asset_links_html_leaves_base64_src_unchanged(
        self, asset_archiver, image_node, image_api_content, html_anchor_wrapped_page
    ):
        """update_asset_links_html should NOT modify base64 data: src attributes."""
        asset_archiver.http_client.http_get_request.return_value.json.return_value = image_api_content

        result = asset_archiver.update_asset_links_html(
            "images", "my-page", html_anchor_wrapped_page, [image_node]
        )
        assert b"data:image/png;base64," in result

    def test_update_asset_links_html_rewrites_attachment_href(
        self, asset_archiver, attachment_node, attachment_api_content, html_attachment_page
    ):
        """update_asset_links_html should rewrite attachment <a href> to local path."""
        asset_archiver.http_client.http_get_request.return_value.json.return_value = attachment_api_content

        result = asset_archiver.update_asset_links_html(
            "attachments", "my-page", html_attachment_page, [attachment_node]
        )
        attachment_url = b"https://wiki.example.com/attachments/99"
        local_path = attachment_node.get_relative_path("my-page").encode()

        assert attachment_url not in result
        assert local_path in result

    def test_update_asset_links_html_preserves_non_asset_anchors(
        self, asset_archiver, attachment_node, attachment_api_content, html_attachment_page
    ):
        """update_asset_links_html must not rewrite anchors that are not asset URLs."""
        asset_archiver.http_client.http_get_request.return_value.json.return_value = attachment_api_content

        result = asset_archiver.update_asset_links_html(
            "attachments", "my-page", html_attachment_page, [attachment_node]
        )
        assert b"https://wiki.example.com/books/my-book" in result

    def test_apply_url_substitutions_logs_debug_on_zero_match(
        self, asset_archiver, caplog
    ):
        """_apply_url_substitutions should log debug when a URL has zero matches in page_data."""
        import logging
        # url_map contains a URL that does NOT appear in page_data
        url_map = {"https://wiki.example.com/missing-url.png": "images/page/foo.png"}
        page_data = b"<html><body><p>No image here</p></body></html>"

        with caplog.at_level(logging.DEBUG, logger="bookstack_file_exporter.archiver.asset_archiver"):
            result = asset_archiver._apply_url_substitutions(page_data, url_map)

        # page_data unchanged
        assert result == page_data
        debug_msgs = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("zero matches" in m.lower() for m in debug_msgs)


# ---------------------------------------------------------------------------
# Phase 4 — PageArchiver dispatch
# ---------------------------------------------------------------------------

class TestPhase4PageArchiverDispatch:
    """Tests for _check_links_modify, _modify_html, and archive_pages dispatch."""

    def _make_config(self, formats=None, export_images=False, export_attachments=False,
                     export_meta=False, modify_links=False):
        config = MagicMock()
        config.urls = {
            "pages": "https://wiki.test.example/api/pages",
            "images": "https://wiki.test.example/api/image-gallery",
            "attachments": "https://wiki.test.example/api/attachments",
        }
        config.user_inputs.formats = formats or ["markdown"]
        config.user_inputs.assets.export_images = export_images
        config.user_inputs.assets.export_attachments = export_attachments
        config.user_inputs.assets.export_meta = export_meta
        config.user_inputs.assets.modify_links = modify_links
        return config

    def _make_archiver(self, tmp_path, monkeypatch, **config_kwargs):
        monkeypatch.setattr(
            "bookstack_file_exporter.archiver.page_archiver.AssetArchiver",
            MagicMock(),
        )
        config = self._make_config(**config_kwargs)
        archive_dir = str(tmp_path / "bookstack-test")
        from bookstack_file_exporter.archiver.page_archiver import PageArchiver
        return PageArchiver(archive_dir, config, MagicMock())

    def test_check_links_modify_true_for_html_format(self, tmp_path, monkeypatch):
        archiver = self._make_archiver(
            tmp_path, monkeypatch,
            formats=["html"],
            modify_links=True,
            export_images=True,
        )
        assert archiver.modify_links is True

    def test_check_links_modify_true_for_markdown_format(self, tmp_path, monkeypatch):
        archiver = self._make_archiver(
            tmp_path, monkeypatch,
            formats=["markdown"],
            modify_links=True,
            export_images=True,
        )
        assert archiver.modify_links is True

    def test_check_links_modify_true_for_both_formats(self, tmp_path, monkeypatch):
        archiver = self._make_archiver(
            tmp_path, monkeypatch,
            formats=["markdown", "html"],
            modify_links=True,
            export_images=True,
        )
        assert archiver.modify_links is True

    def test_check_links_modify_false_when_no_assets(self, tmp_path, monkeypatch):
        archiver = self._make_archiver(
            tmp_path, monkeypatch,
            formats=["html"],
            modify_links=True,
            export_images=False,
            export_attachments=False,
        )
        assert archiver.modify_links is False

    def test_check_links_modify_false_when_format_not_rewritable(self, tmp_path, monkeypatch):
        archiver = self._make_archiver(
            tmp_path, monkeypatch,
            formats=["pdf"],
            modify_links=True,
            export_images=True,
        )
        assert archiver.modify_links is False

    def test_warning_when_modify_links_true_but_no_rewritable_format(
        self, tmp_path, monkeypatch, caplog
    ):
        import logging
        with caplog.at_level(logging.WARNING, logger="bookstack_file_exporter.archiver.page_archiver"):
            self._make_archiver(
                tmp_path, monkeypatch,
                formats=["pdf"],
                modify_links=True,
                export_images=True,
            )
        warning_msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("MODIFY_LINKS" in m or "rewritable" in m.lower() for m in warning_msgs)

    def test_archive_pages_dispatches_html_branch(
        self, tmp_path, monkeypatch, build_node
    ):
        """archive_pages should call _modify_html when format='html' and modify_links=True."""
        mock_asset_archiver_class = MagicMock()
        monkeypatch.setattr(
            "bookstack_file_exporter.archiver.page_archiver.AssetArchiver",
            mock_asset_archiver_class,
        )
        config = self._make_config(
            formats=["html"],
            modify_links=True,
            export_images=True,
        )
        archive_dir = str(tmp_path / "bookstack-test")
        from bookstack_file_exporter.archiver.page_archiver import PageArchiver
        archiver = PageArchiver(archive_dir, config, MagicMock())

        # Set up mock asset nodes
        mock_image_node = MagicMock()
        mock_image_node.id_ = 1
        archiver.asset_archiver.get_asset_nodes.side_effect = lambda asset_type: (
            {5: [mock_image_node]} if asset_type == "images" else {}
        )
        archiver.asset_archiver.get_asset_bytes.return_value = b"img_bytes"

        parent_node = build_node(id=1, name="my-book", slug="my-book")
        page = build_node(id=5, name="test-page", slug="test-page", parent=parent_node)

        with patch(
            "bookstack_file_exporter.archiver.page_archiver.archiver_util.get_byte_response",
            return_value=b"<html><body>content</body></html>",
        ), patch(
            "bookstack_file_exporter.archiver.page_archiver.archiver_util.write_tar"
        ), patch.object(archiver, "_modify_html", wraps=archiver._modify_html) as mock_modify_html:
            archiver.archive_pages({5: page})

        mock_modify_html.assert_called_once()

    def test_modify_html_short_circuits_when_modify_links_false(
        self, tmp_path, monkeypatch
    ):
        """_modify_html should return page_data unchanged when modify_links is False."""
        monkeypatch.setattr(
            "bookstack_file_exporter.archiver.page_archiver.AssetArchiver",
            MagicMock(),
        )
        config = self._make_config(formats=["html"], modify_links=False)
        archive_dir = str(tmp_path / "bookstack-test")
        from bookstack_file_exporter.archiver.page_archiver import PageArchiver
        archiver = PageArchiver(archive_dir, config, MagicMock())

        page_data = b"<html><body>test</body></html>"
        mock_nodes = [MagicMock()]

        result = archiver._modify_html("images", "test-page", page_data, mock_nodes)
        assert result == page_data
        # ensure no call to update_asset_links_html
        archiver.asset_archiver.update_asset_links_html.assert_not_called()

    def test_failed_assets_filtered_from_html_rewrite(
        self, tmp_path, monkeypatch, build_node
    ):
        """Failed assets should be excluded from both md and html rewrite paths."""
        mock_asset_archiver_class = MagicMock()
        monkeypatch.setattr(
            "bookstack_file_exporter.archiver.page_archiver.AssetArchiver",
            mock_asset_archiver_class,
        )
        config = self._make_config(
            formats=["html"],
            modify_links=True,
            export_images=True,
        )
        archive_dir = str(tmp_path / "bookstack-test")
        from bookstack_file_exporter.archiver.page_archiver import PageArchiver
        from requests.exceptions import HTTPError
        archiver = PageArchiver(archive_dir, config, MagicMock())

        mock_image_node = MagicMock()
        mock_image_node.id_ = 42
        archiver.asset_archiver.get_asset_nodes.side_effect = lambda asset_type: (
            {5: [mock_image_node]} if asset_type == "images" else {}
        )
        # Simulate asset download failure
        archiver.asset_archiver.get_asset_bytes.side_effect = HTTPError("404")

        parent_node = build_node(id=1, name="my-book", slug="my-book")
        page = build_node(id=5, name="test-page", slug="test-page", parent=parent_node)

        with patch(
            "bookstack_file_exporter.archiver.page_archiver.archiver_util.get_byte_response",
            return_value=b"<html><body>content</body></html>",
        ), patch(
            "bookstack_file_exporter.archiver.page_archiver.archiver_util.write_tar"
        ):
            archiver.archive_pages({5: page})

        # When all assets fail, _rewrite_page_data short-circuits on empty nodes list
        # and never calls update_asset_links_html.
        calls = archiver.asset_archiver.update_asset_links_html.call_args_list
        assert calls == [], f"expected no html rewrite calls when all assets fail, got {len(calls)}"

    def test_partially_failed_assets_excluded_from_html_rewrite(
        self, tmp_path, monkeypatch, build_node
    ):
        """When some assets fail, only successful nodes are passed to update_asset_links_html."""
        mock_asset_archiver_class = MagicMock()
        monkeypatch.setattr(
            "bookstack_file_exporter.archiver.page_archiver.AssetArchiver",
            mock_asset_archiver_class,
        )
        config = self._make_config(
            formats=["html"],
            modify_links=True,
            export_images=True,
        )
        archive_dir = str(tmp_path / "bookstack-test")
        from bookstack_file_exporter.archiver.page_archiver import PageArchiver
        from requests.exceptions import HTTPError
        archiver = PageArchiver(archive_dir, config, MagicMock())

        good_node = MagicMock(spec=ImageNode)
        good_node.id_ = 10
        good_node.download_url = "https://wiki.example.com/uploads/images/10/good.png"
        bad_node = MagicMock(spec=ImageNode)
        bad_node.id_ = 99
        bad_node.download_url = "https://wiki.example.com/uploads/images/99/bad.png"

        archiver.asset_archiver.get_asset_nodes.side_effect = lambda asset_type: (
            {5: [good_node, bad_node]} if asset_type == "images" else {}
        )

        def _fail_bad_node(asset_type, url):
            if "99" in url:
                raise HTTPError("404")
            return b"img_bytes"

        archiver.asset_archiver.get_asset_bytes.side_effect = _fail_bad_node

        parent_node = build_node(id=1, name="my-book", slug="my-book")
        page = build_node(id=5, name="test-page", slug="test-page", parent=parent_node)

        with patch(
            "bookstack_file_exporter.archiver.page_archiver.archiver_util.get_byte_response",
            return_value=b"<html><body>content</body></html>",
        ), patch(
            "bookstack_file_exporter.archiver.page_archiver.archiver_util.write_tar"
        ):
            archiver.archive_pages({5: page})

        calls = archiver.asset_archiver.update_asset_links_html.call_args_list
        assert len(calls) >= 1, "update_asset_links_html should be called when some assets succeed"
        for c in calls:
            nodes_arg = c.args[3] if len(c.args) > 3 else c.kwargs.get("asset_nodes", [])
            assert bad_node not in nodes_arg, "failed node must not be passed to html rewrite"
            assert good_node in nodes_arg, "successful node must be passed to html rewrite"


# ---------------------------------------------------------------------------
# E2E — full pipeline integration
# ---------------------------------------------------------------------------

class TestE2eHtmlRewrite:
    """Full pipeline: PageArchiver → AssetArchiver → bytes.replace, HTTP mocked only.

    Verifies that archive_pages rewrites image URLs in HTML exports
    to local relative paths end-to-end without mocking internal components.
    Requires Task 1 fix (skip redundant API call for ImageNode in HTML mode).

    PAGE_HTML uses a base64 data: URI for img src — matching how real
    BookStack page exports embed images. This is fixture realism only.

    Task 1's optimization is proven by the http_get_request.call_count
    assertion below, NOT by the base64 src. With Task 1: 1 HTTP call
    (asset bytes only). Without Task 1: 2 HTTP calls (asset bytes +
    redundant get_asset_data). The other assertions (anchor rewritten,
    IMAGE_URL absent) pass in both states because 'content' in MagicMock()
    is False, so _get_html_url_strs returns [] and url_map falls back to
    {page_url: local_path} either way.
    """

    IMAGE_ID = 42
    PAGE_ID = 5
    IMAGE_URL = "https://wiki.example.com/uploads/images/gallery/2024-01/photo.png"
    PAGE_HTML = (
        '<html><body>'
        f'<a href="{IMAGE_URL}">'
        '<img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==" alt="photo">'
        '</a></body></html>'
    )

    def _make_config(self):
        config = MagicMock()
        config.urls = {
            "pages": "https://wiki.example.com/api/pages",
            "images": "https://wiki.example.com/api/image-gallery",
            "attachments": "https://wiki.example.com/api/attachments",
        }
        config.user_inputs.formats = ["html"]
        config.user_inputs.assets.export_images = True
        config.user_inputs.assets.export_attachments = False
        config.user_inputs.assets.export_meta = False
        config.user_inputs.assets.modify_links = True
        return config

    def test_html_image_url_rewritten_to_local_path(self, tmp_path, build_node):
        """Full pipeline rewrites remote image URL in HTML export to local relative path."""
        import re
        from bookstack_file_exporter.archiver.page_archiver import PageArchiver

        config = self._make_config()
        archive_dir = str(tmp_path / "bookstack-test")

        http_client = MagicMock(spec=HttpHelper)
        http_client.http_get_all.return_value = [{
            "id": self.IMAGE_ID,
            "uploaded_to": self.PAGE_ID,
            "url": self.IMAGE_URL,
        }]
        http_client.http_get_request.return_value.content = b"fake_png_bytes"

        written: dict = {}

        def capture_write(base_tar_dir: str, file_path: str, data: bytes) -> None:
            written[file_path] = data

        parent = build_node(id=1, name="my-book", slug="my-book")
        page = build_node(id=self.PAGE_ID, name="test-page", slug="test-page", parent=parent)

        archiver = PageArchiver(archive_dir, config, http_client)

        with patch(
            "bookstack_file_exporter.archiver.page_archiver.archiver_util.get_byte_response",
            return_value=self.PAGE_HTML.encode(),
        ), patch(
            "bookstack_file_exporter.archiver.page_archiver.archiver_util.write_tar",
            side_effect=capture_write,
        ):
            archiver.archive_pages({self.PAGE_ID: page})

        html_files = {k: v for k, v in written.items() if k.endswith(".html")}
        assert len(html_files) == 1, (
            f"expected exactly one HTML file; got {len(html_files)}: {list(html_files)}"
        )

        html_bytes = next(iter(html_files.values()))

        assert re.search(
            rb'<a href="images/test-page/photo\.png">',
            html_bytes,
        ), "anchor href must be rewritten to local relative path"

        assert self.IMAGE_URL.encode() not in html_bytes, (
            "remote URL must be fully removed from HTML output"
        )

        assert b'src="data:image/png;base64,' in html_bytes, (
            "base64 data: src must be preserved across rewrite"
        )

        assert http_client.http_get_request.call_count == 1, (
            f"expected 1 HTTP call (asset bytes only); "
            f"got {http_client.http_get_request.call_count} — "
            f"Task 1 short-circuit not firing"
        )
