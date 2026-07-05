# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name,unused-argument,protected-access,too-few-public-methods
"""Archive finalize/abort and poisoned-stream tests for PageArchiver."""
import os
import tarfile

import pytest

from bookstack_file_exporter.archiver.util import ArchiveWriteError


# ---------------------------------------------------------------------------
# 4. finalize_archive closes the stream then renames .tgz.incomplete -> .tgz
# ---------------------------------------------------------------------------
class TestFinalizeArchive:

    def test_finalize_renames_incomplete_to_final(self, page_archiver):
        page_archiver.write_data("notes/page.md", b"# hi")
        page_archiver.finalize_archive()
        assert os.path.exists(page_archiver.archive_file)
        assert not os.path.exists(page_archiver.incomplete_file)
        with tarfile.open(page_archiver.archive_file, "r:gz") as tar:
            assert tar.getnames() == ["notes/page.md"]

    def test_finalize_close_failure_does_not_publish(self, page_archiver, monkeypatch, request):
        page_archiver.write_data("notes/page.md", b"# hi")

        def boom():
            raise OSError("flush failed")
        monkeypatch.setattr(page_archiver._tar_stream._tar, "close", boom)
        # Mocking close() out entirely means the real gzip handle underneath is
        # never actually closed; close it directly at teardown so its finalizer
        # doesn't raise "lost gzip_file" as an unraisable warning that could mask
        # a real one.
        request.addfinalizer(page_archiver._tar_stream._tar.fileobj.close)
        with pytest.raises(ArchiveWriteError):
            page_archiver.finalize_archive()
        assert not os.path.exists(page_archiver.archive_file)

    def test_abort_archive_never_raises(self, page_archiver):
        page_archiver.write_data("notes/page.md", b"# hi")
        page_archiver.abort_archive()
        page_archiver.abort_archive()

    def test_finalize_renames_to_partial_marker_on_failed_node_exports(self, page_archiver):
        page_archiver.write_data("notes/page.md", b"# hi")
        page_archiver.failed_node_exports.append("books/broken-page")
        page_archiver.finalize_archive()
        assert page_archiver.archive_file.endswith("_partial.tgz")
        assert os.path.exists(page_archiver.archive_file)
        assert not os.path.exists(page_archiver.incomplete_file)

    def test_finalize_renames_to_partial_marker_on_failed_asset_downloads(self, page_archiver):
        page_archiver.write_data("notes/page.md", b"# hi")
        page_archiver.failed_asset_downloads.append("images/broken-image.png")
        page_archiver.finalize_archive()
        assert page_archiver.archive_file.endswith("_partial.tgz")
        assert os.path.exists(page_archiver.archive_file)
        assert not os.path.exists(page_archiver.incomplete_file)

    def test_finalize_keeps_plain_name_on_clean_run(self, page_archiver):
        page_archiver.write_data("notes/page.md", b"# hi")
        page_archiver.finalize_archive()
        assert not page_archiver.archive_file.endswith("_partial.tgz")
        assert page_archiver.archive_file.endswith(".tgz")
        assert os.path.exists(page_archiver.archive_file)


class TestPoisonedStreamChain:
    """Mid-run write failure poisons the stream; finalize refuses to publish."""

    def test_poison_then_finalize_refuses_publish(self, page_archiver, monkeypatch, request):
        page_archiver.write_data("book/page1.md", b"# ok")   # node 1 landed
        # finalize_archive() refuses to publish (below), so the underlying gzip
        # handle is never closed; abort it at teardown so its finalizer doesn't
        # raise "lost gzip_file" as an unraisable warning that could mask a real one.
        request.addfinalizer(page_archiver._tar_stream.abort)

        def boom(*_args, **_kwargs):
            raise OSError("disk full")
        monkeypatch.setattr(page_archiver._tar_stream._tar, "addfile", boom)
        with pytest.raises(ArchiveWriteError):
            page_archiver.write_data("book/page2.md", b"# fails")   # node 2 poisons
        with pytest.raises(ArchiveWriteError):
            page_archiver.finalize_archive()                        # publish refused
        assert not os.path.exists(page_archiver.archive_file)
