# pylint: disable=missing-class-docstring,missing-function-docstring
# pylint: disable=redefined-outer-name,protected-access
"""Unit tests for AssetNode.all_urls, _build_url_map, and update_asset_links_html (Phase 3)."""
import logging


# ---------------------------------------------------------------------------
# Phase 3 — all_urls extraction
# ---------------------------------------------------------------------------

class TestAllUrls:
    """Tests for AssetNode.all_urls() — pure extraction + canonical URL."""

    def test_image_all_urls_html_includes_outer_anchor_href(
        self, image_node, image_api_content
    ):
        """all_urls(kind='html') should include the outer anchor href."""
        urls = image_node.all_urls(image_api_content, "html")
        assert (
            "https://wiki.example.com/uploads/images/gallery/2024-01/screenshot.png"
            in urls
        )

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
        assert (
            "https://wiki.example.com/uploads/images/gallery/2024-01/screenshot.png"
            in urls
        )

    def test_all_urls_markdown_returns_extracted_urls(
        self, image_node, image_api_content
    ):
        """all_urls(kind='markdown') should return URLs extracted from markdown content."""
        urls = image_node.all_urls(image_api_content, "markdown")
        assert (
            "https://wiki.example.com/uploads/images/gallery/2024-01/"
            "scaled-1680-/screenshot.png"
        ) in urls

    def test_all_urls_returns_only_canonical_when_no_content(
        self, image_node
    ):
        """all_urls should return only the full-res URL when asset_data has no content key."""
        urls = image_node.all_urls({}, "html")
        assert urls == [
            "https://wiki.example.com/uploads/images/gallery/2024-01/screenshot.png"
        ]

    def test_attachment_all_urls_empty_page_url_filtered_by_build_url_map(
        self, asset_archiver, attachment_node, attachment_api_content
    ):
        """AttachmentNode.page_url is '' — _build_url_map must not add it to the map."""
        asset_archiver.http_client.http_get_request.return_value.json.return_value = (
            attachment_api_content
        )
        url_map = asset_archiver._build_url_map(
            "attachments", "my-page", [attachment_node], kind="html"
        )
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


class TestPhase2HtmlPath:  # pylint: disable=too-few-public-methods
    """Tests for _build_url_map behaviour in HTML mode — test scaffolding stub."""

    def test_build_url_map_skips_api_call_for_image_nodes_in_html_mode(
        self, asset_archiver, image_node
    ):
        """ImageNode.page_url is known from listing data — no per-asset API call needed for
        HTML mode.

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


# ---------------------------------------------------------------------------
# Phase 3 — HTML rewrite
# ---------------------------------------------------------------------------

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
        asset_archiver.http_client.http_get_request.return_value.json.return_value = (
            image_api_content
        )

        result = asset_archiver.update_asset_links_html(
            "images", "my-page", html_anchor_wrapped_page, [image_node]
        )
        outer_url = (
            b"https://wiki.example.com/uploads/images/gallery/2024-01/screenshot.png"
        )
        local_path = image_node.get_relative_path("my-page").encode()

        assert outer_url not in result
        assert local_path in result

    def test_update_asset_links_html_rewrites_wrapped_base64_src(
        self, asset_archiver, image_node, image_api_content, html_anchor_wrapped_page
    ):
        """update_asset_links_html must slim wrapped base64 src to the anchor's local path
        (Phase 2). The fixture uses <a href=canonical><img src=data:...> where canonical
        is the image_node's page_url, so the blob is replaced by images/my-page/screenshot.png."""
        asset_archiver.http_client.http_get_request.return_value.json.return_value = (
            image_api_content
        )

        result = asset_archiver.update_asset_links_html(
            "images", "my-page", html_anchor_wrapped_page, [image_node]
        )
        local_path = image_node.get_relative_path("my-page").encode()
        assert b"data:image/png;base64," not in result, (
            "wrapped base64 blob must be slimmed to local path (Phase 2)"
        )
        assert local_path in result

    def test_update_asset_links_html_rewrites_attachment_href(
        self, asset_archiver, attachment_node, attachment_api_content, html_attachment_page
    ):
        """update_asset_links_html should rewrite attachment <a href> to local path."""
        asset_archiver.http_client.http_get_request.return_value.json.return_value = (
            attachment_api_content
        )

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
        asset_archiver.http_client.http_get_request.return_value.json.return_value = (
            attachment_api_content
        )

        result = asset_archiver.update_asset_links_html(
            "attachments", "my-page", html_attachment_page, [attachment_node]
        )
        assert b"https://wiki.example.com/books/my-book" in result

    def test_apply_url_substitutions_logs_debug_on_zero_match(
        self, asset_archiver, caplog
    ):
        """_apply_url_substitutions should log debug when a URL has zero matches in page_data."""
        # url_map contains a URL that does NOT appear in page_data
        url_map = {"https://wiki.example.com/missing-url.png": "images/page/foo.png"}
        page_data = b"<html><body><p>No image here</p></body></html>"

        logger_name = "bookstack_file_exporter.archiver.asset_archiver"
        with caplog.at_level(logging.DEBUG, logger=logger_name):
            result = asset_archiver._apply_url_substitutions(page_data, url_map)

        # page_data unchanged
        assert result == page_data
        debug_msgs = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("zero matches" in m.lower() for m in debug_msgs)

    def test_apply_url_substitutions_prefix_overlapping_urls_no_corruption(
        self, asset_archiver
    ):
        """Two attachment URLs where one is a prefix of the other (IDs 6 vs 60)
        must both rewrite cleanly. Insertion-order iteration would replace the
        shorter URL first and orphan the trailing '0' from ID 60, producing
        e.g. 'local/a.dat0'. Length-descending sort prevents this."""
        url_map = {
            "https://wiki.example.com/attachments/6":  "attachments/page/a.dat",
            "https://wiki.example.com/attachments/60": "attachments/page/b.dat",
        }
        page_data = (
            b"[a](https://wiki.example.com/attachments/6) "
            b"text "
            b"[b](https://wiki.example.com/attachments/60)"
        )
        result = asset_archiver._apply_url_substitutions(page_data, url_map)

        assert b"attachments/page/a.dat0" not in result, (
            "shorter URL replaced first corrupts longer URL's trailing chars"
        )
        assert b"[a](attachments/page/a.dat)" in result
        assert b"[b](attachments/page/b.dat)" in result
        assert b"https://wiki.example.com/attachments/" not in result, (
            "no remote URL fragments should remain"
        )
