# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name,unused-argument,protected-access,too-few-public-methods,duplicate-code
"""Core construction, config, and property tests for PageArchiver."""
import logging
from unittest.mock import MagicMock, patch

import pytest

from bookstack_file_exporter.archiver.node_archiver import NodeArchiver, PageArchiver
from tests.fixtures.mock_config import make_mock_config as _make_config


# ---------------------------------------------------------------------------
# 1. Construction
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_archive_file_ends_with_tgz(self, tmp_path):
        archive_dir = str(tmp_path / "bookstack-20260514")
        archiver = PageArchiver(archive_dir, _make_config(), MagicMock(),
                                asset_archiver=MagicMock())
        assert archiver.archive_file == f"{archive_dir}.tgz"

    def test_partial_file_is_tgz_partial(self, tmp_path):
        archive_dir = str(tmp_path / "bookstack-20260514")
        archiver = PageArchiver(archive_dir, _make_config(), MagicMock(),
                                asset_archiver=MagicMock())
        assert archiver.partial_file == f"{archiver.archive_file}.partial"
        assert archiver.archive_file.endswith(".tgz")

    def test_archive_base_path_is_last_segment(self, tmp_path):
        archive_dir = str(tmp_path / "bookstack-20260514")
        archiver = PageArchiver(archive_dir, _make_config(), MagicMock(),
                                asset_archiver=MagicMock())
        assert archiver.archive_base_path == "bookstack-20260514"

    def test_http_client_stored(self, tmp_path):
        http_client = MagicMock()
        archive_dir = str(tmp_path / "bookstack-20260514")
        archiver = PageArchiver(archive_dir, _make_config(), http_client,
                                asset_archiver=MagicMock())
        assert archiver.http_client is http_client


# ---------------------------------------------------------------------------
# 2. Export URL formation (via archive → _export_nodes)
# ---------------------------------------------------------------------------

class TestExportUrl:
    @pytest.mark.parametrize("export_format", ["markdown", "html", "pdf", "plaintext", "zip"])
    def test_url_contains_export_api_path(self, tmp_path, build_node, export_format):
        """archive should call get_byte_response with the correct pages export URL."""
        config = _make_config(formats=[export_format], export_images=False,
                              export_attachments=False, export_meta=False)
        archiver = PageArchiver(str(tmp_path / "bs"), config, MagicMock(),
                                asset_archiver=MagicMock())
        archiver.asset_archiver.get_asset_nodes.return_value = {}
        parent_node = build_node(id=1, name="my-book", slug="my-book")
        page = build_node(id=42, name="my-page", slug="my-page", parent=parent_node)

        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response"
        ) as mock_get_bytes, patch(
            "bookstack_file_exporter.archiver.util.TarStream.write"
        ):
            mock_get_bytes.return_value = b"page content"
            archiver.archive({42: page})
            called_url = mock_get_bytes.call_args.kwargs["url"]

        expected = f"https://wiki.test.example/api/pages/42/export/{export_format}"
        assert called_url == expected


# ---------------------------------------------------------------------------
# 3. File extension map property
# ---------------------------------------------------------------------------

class TestFileExtensionMap:
    def test_markdown_extension(self, page_archiver):
        assert page_archiver.file_extension_map["markdown"] == ".md"

    def test_html_extension(self, page_archiver):
        assert page_archiver.file_extension_map["html"] == ".html"

    def test_pdf_extension(self, page_archiver):
        assert page_archiver.file_extension_map["pdf"] == ".pdf"

    def test_plaintext_extension(self, page_archiver):
        assert page_archiver.file_extension_map["plaintext"] == ".txt"

    def test_zip_extension(self, page_archiver):
        assert page_archiver.file_extension_map["zip"] == ".zip"

    def test_tgz_extension(self, page_archiver):
        assert page_archiver.file_extension_map["tgz"] == ".tgz"

    def test_meta_extension(self, page_archiver):
        assert page_archiver.file_extension_map["meta"] == "_meta.json"


# ---------------------------------------------------------------------------
# 5. write_data delegates to TarStream.write
# ---------------------------------------------------------------------------

class TestWriteData:  # pylint: disable=too-few-public-methods  # test scaffolding stub
    def test_write_data_delegates_to_stream(self, page_archiver):
        with patch(
            "bookstack_file_exporter.archiver.util.TarStream.write"
        ) as mock_write:
            page_archiver.write_data("some/file.md", b"content")
        mock_write.assert_called_once_with("some/file.md", b"content")


# ---------------------------------------------------------------------------
# 7. Regression: broken verify_ssl property must not exist on PageArchiver
# ---------------------------------------------------------------------------

def test_page_archiver_has_no_verify_ssl_property():
    """verify_ssl was broken (read nonexistent Assets field); confirm it is gone."""
    assert not hasattr(PageArchiver, "verify_ssl")


# ---------------------------------------------------------------------------
# 8. R8: asset_archiver injection seam
# ---------------------------------------------------------------------------

class TestAssetArchiverInjection:
    """Constructor-injected asset_archiver double is stored as self.asset_archiver."""

    def test_injected_double_is_stored(self, tmp_path):
        """When asset_archiver= is supplied, NodeArchiver stores it
        without constructing a real one."""
        double = MagicMock()
        config = _make_config(export_images=True)
        archive_dir = str(tmp_path / "bookstack-r8")
        archiver = PageArchiver(archive_dir, config, MagicMock(), asset_archiver=double)
        assert archiver.asset_archiver is double

    def test_no_injection_no_asset_config_is_none(self, tmp_path):
        """When asset_archiver= not supplied and asset_config=None, asset_archiver is None."""
        archive_dir = str(tmp_path / "bookstack-r8-none")
        # Direct NodeArchiver construction: asset_config=None => no AssetArchiver built
        archiver = NodeArchiver(
            archive_dir=archive_dir,
            api_urls={"images": "https://x", "attachments": "https://y"},
            export_formats=["markdown"],
            http_client=MagicMock(),
            export_meta=False,
            asset_config=None,
        )
        assert archiver.asset_archiver is None

    def test_injected_double_overrides_real_construction(self, tmp_path):
        """When asset_archiver= injected and asset_config is truthy, the injected double wins."""
        double = MagicMock()
        archive_dir = str(tmp_path / "bookstack-r8-override")
        archiver = NodeArchiver(
            archive_dir=archive_dir,
            api_urls={"images": "https://x", "attachments": "https://y"},
            export_formats=["markdown"],
            http_client=MagicMock(),
            export_meta=False,
            asset_config=MagicMock(),  # truthy: without injection, would build real AssetArchiver
            asset_archiver=double,
        )
        assert archiver.asset_archiver is double


# ---------------------------------------------------------------------------
# 9. R5: page output path = page.file_path (no /name double-suffix)
# ---------------------------------------------------------------------------

class TestPageOutputPath:
    def test_page_content_written_to_file_path_not_file_path_slash_name(
            self, tmp_path, build_node):
        """Page export must be written to <base>/<page.file_path>.md, NOT <base>/<fp>/<name>.md."""
        config = _make_config(formats=["markdown"], export_images=False,
                              export_attachments=False, export_meta=False)
        archiver = PageArchiver(str(tmp_path / "bs"), config, MagicMock(),
                                asset_archiver=MagicMock())
        archiver.asset_archiver.get_asset_nodes.return_value = {}

        parent_node = build_node(id=1, name="my-book", slug="my-book")
        page = build_node(id=7, name="my-page", slug="my-page", parent=parent_node)
        # page.file_path = "my-book/my-page"

        written = {}
        archiver.write_data = written.__setitem__
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"data",
        ):
            archiver.archive({7: page})

        expected_key = f"{archiver.archive_base_path}/my-book/my-page.md"
        assert expected_key in written, f"Expected key {expected_key!r}, got {list(written)}"

    def test_page_meta_written_to_file_path(self, tmp_path, build_node):
        """Page meta must be <base>/<page.file_path>_meta.json."""
        config = _make_config(formats=["markdown"], export_images=False,
                              export_attachments=False, export_meta=True)
        archiver = PageArchiver(str(tmp_path / "bs"), config, MagicMock(),
                                asset_archiver=MagicMock())
        archiver.asset_archiver.get_asset_nodes.return_value = {}

        parent_node = build_node(id=1, name="my-book", slug="my-book")
        page = build_node(id=7, name="my-page", slug="my-page", parent=parent_node)

        written = {}
        archiver.write_data = written.__setitem__
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"data",
        ):
            archiver.archive({7: page})

        expected_meta_key = f"{archiver.archive_base_path}/my-book/my-page_meta.json"
        assert expected_meta_key in written, (
            f"Expected meta key {expected_meta_key!r}, got {list(written)}"
        )


# ---------------------------------------------------------------------------
# 10. R5: page assets written under parent.file_path
# ---------------------------------------------------------------------------

class TestPageAssetParentPath:
    def test_page_image_written_under_parent_file_path(self, tmp_path, build_node):
        """Image assets for a page must be stored under the parent book/chapter path."""
        config = _make_config(formats=["markdown"], export_images=True,
                              export_attachments=False, export_meta=False,
                              modify_links=True)
        archiver = PageArchiver(str(tmp_path / "bs"), config, MagicMock(),
                                asset_archiver=MagicMock())

        parent_node = build_node(id=1, name="my-book", slug="my-book")
        page = build_node(id=7, name="my-page", slug="my-page", parent=parent_node)

        img = MagicMock(id_=42, download_url="http://x/img", uploaded_to=7)
        img.get_relative_path = lambda page_name: f"images/{page_name}/img.png"

        archiver.asset_archiver.get_asset_nodes.side_effect = (
            lambda kind: {7: [img]} if kind == "images" else {}
        )
        archiver.asset_archiver.get_asset_bytes.return_value = b"PNGDATA"
        archiver.asset_archiver.update_asset_links.side_effect = lambda *a, **kw: a[2]

        written = {}
        archiver.write_data = written.__setitem__
        with patch(
            "bookstack_file_exporter.archiver.node_archiver.archiver_util.get_byte_response",
            return_value=b"data",
        ):
            archiver.archive({7: page})

        # asset must live under parent.file_path ("my-book"), NOT page.file_path ("my-book/my-page")
        expected_asset_key = f"{archiver.archive_base_path}/my-book/images/my-page/img.png"
        assert expected_asset_key in written, (
            f"Expected {expected_asset_key!r} in written; got {list(written)}"
        )


# ---------------------------------------------------------------------------
# 13. export_workers stored and soft-warned
# ---------------------------------------------------------------------------

class TestExportWorkers:
    def test_defaults_to_one(self, tmp_path):
        archiver = PageArchiver(str(tmp_path / "bs"), _make_config(), MagicMock(),
                                asset_archiver=MagicMock())
        assert archiver.export_workers == 1

    def test_reads_value_from_config(self, tmp_path):
        config = _make_config(export_workers=8)
        archiver = PageArchiver(str(tmp_path / "bs"), config, MagicMock(),
                                asset_archiver=MagicMock())
        assert archiver.export_workers == 8

    def test_soft_warns_when_above_threshold(self, tmp_path, caplog):
        config = _make_config(export_workers=32)
        with caplog.at_level(logging.WARNING):
            PageArchiver(str(tmp_path / "bs"), config, MagicMock(),
                         asset_archiver=MagicMock())
        assert any("export_workers" in r.message and "429" in r.message
                   for r in caplog.records)

    def test_no_warn_at_or_below_threshold(self, tmp_path, caplog):
        config = _make_config(export_workers=16)
        with caplog.at_level(logging.WARNING):
            PageArchiver(str(tmp_path / "bs"), config, MagicMock(),
                         asset_archiver=MagicMock())
        assert not any("export_workers" in r.message for r in caplog.records)
