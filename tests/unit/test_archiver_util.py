# pylint: disable=missing-class-docstring,missing-function-docstring,protected-access
"""Unit tests for archiver utility functions (scan, compress, delete)."""
import json
import tarfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from bookstack_file_exporter.archiver import util
from bookstack_file_exporter.archiver.util import ArchiveWriteError, TarStream


# ---------------------------------------------------------------------------
# create_dir
# ---------------------------------------------------------------------------

def test_create_dir_creates_new_directory(tmp_path):
    target = tmp_path / "new_dir"
    util.create_dir(str(target))
    assert target.is_dir()


def test_create_dir_creates_nested_directories(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    util.create_dir(str(target))
    assert target.is_dir()


def test_create_dir_existing_does_not_raise(tmp_path):
    target = tmp_path / "existing"
    target.mkdir()
    util.create_dir(str(target))  # should not raise
    assert target.is_dir()


# ---------------------------------------------------------------------------
# remove_file
# ---------------------------------------------------------------------------

def test_remove_file_removes_existing_file(tmp_path):
    f = tmp_path / "to_delete.txt"
    f.write_text("hello")
    util.remove_file(str(f))
    assert not f.exists()


def test_remove_file_raises_on_missing_file(tmp_path):
    missing = tmp_path / "ghost.txt"
    with pytest.raises(FileNotFoundError):
        util.remove_file(str(missing))


# ---------------------------------------------------------------------------
# get_json_bytes
# ---------------------------------------------------------------------------

def test_get_json_bytes_returns_bytes():
    data = {"key": "value", "num": 42}
    result = util.get_json_bytes(data)
    assert isinstance(result, bytes)


def test_get_json_bytes_round_trips():
    data = {"title": "Book", "id": 7}
    result = util.get_json_bytes(data)
    parsed = json.loads(result.decode("utf-8"))
    assert parsed == data


def test_get_json_bytes_empty_dict():
    result = util.get_json_bytes({})
    parsed = json.loads(result.decode("utf-8"))
    assert parsed == {}


def test_get_json_bytes_is_indented():
    data = {"a": 1}
    result = util.get_json_bytes(data)
    text = result.decode("utf-8")
    assert "\n" in text  # indent=4 produces newlines


# ---------------------------------------------------------------------------
# scan_archives
# ---------------------------------------------------------------------------

def test_scan_archives_finds_matching_files(tmp_path):
    base = str(tmp_path / "backup")
    # create files that match the pattern  <base>_*<ext>
    Path(f"{base}_20240101.tar.gz").touch()
    Path(f"{base}_20240102.tar.gz").touch()
    results = util.scan_archives(base, ".tar.gz")
    assert len(results) == 2


def test_scan_archives_excludes_non_matching_files(tmp_path):
    base = str(tmp_path / "backup")
    Path(f"{base}_20240101.tar.gz").touch()
    Path(str(tmp_path / "other_20240101.tar.gz")).touch()
    results = util.scan_archives(base, ".tar.gz")
    assert len(results) == 1


def test_scan_archives_empty_when_no_matches(tmp_path):
    base = str(tmp_path / "backup")
    results = util.scan_archives(base, ".tar.gz")
    assert not results


def test_scan_archives_extension_filter(tmp_path):
    base = str(tmp_path / "backup")
    Path(f"{base}_v1.tar.gz").touch()
    Path(f"{base}_v2.zip").touch()
    gz_results = util.scan_archives(base, ".tar.gz")
    zip_results = util.scan_archives(base, ".zip")
    assert len(gz_results) == 1
    assert len(zip_results) == 1


# ---------------------------------------------------------------------------
# TarStream
# ---------------------------------------------------------------------------

class TestTarStreamWrite:
    """TarStream streams members into a gzip'd tar at the given path."""

    def test_lazy_open_no_file_before_first_write(self, tmp_path):
        incomplete = str(tmp_path / "bkps.tgz.incomplete")
        TarStream(incomplete)
        assert not (tmp_path / "bkps.tgz.incomplete").exists()

    def test_first_write_creates_incomplete(self, tmp_path):
        incomplete = str(tmp_path / "bkps.tgz.incomplete")
        stream = TarStream(incomplete)
        stream.write("hello.txt", b"hello world")
        assert (tmp_path / "bkps.tgz.incomplete").exists()
        stream.finalize()

    def test_members_readable_after_finalize(self, tmp_path):
        incomplete = str(tmp_path / "bkps.tgz.incomplete")
        stream = TarStream(incomplete)
        stream.write("file1.txt", b"data1")
        stream.write("dir/file2.txt", b"data2")
        stream.finalize()
        with tarfile.open(incomplete, "r:gz") as tar:
            names = tar.getnames()
            assert names == ["file1.txt", "dir/file2.txt"]
            member = tar.extractfile("dir/file2.txt")
            assert member.read() == b"data2"

    def test_member_size_matches_payload(self, tmp_path):
        incomplete = str(tmp_path / "bkps.tgz.incomplete")
        stream = TarStream(incomplete)
        payload = b"x" * 4096
        stream.write("big.bin", payload)
        stream.finalize()
        with tarfile.open(incomplete, "r:gz") as tar:
            info = tar.getmember("big.bin")
            assert info.size == len(payload)

    def test_concurrent_writes_all_present(self, tmp_path):
        """Writes from a pool serialize under the internal lock; nothing is lost."""
        incomplete = str(tmp_path / "bkps.tgz.incomplete")
        stream = TarStream(incomplete)
        n = 32
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [
                pool.submit(stream.write, f"file{i}.txt", f"data{i}".encode())
                for i in range(n)
            ]
            for future in futures:
                future.result()
        stream.finalize()
        with tarfile.open(incomplete, "r:gz") as tar:
            assert sorted(tar.getnames()) == sorted(f"file{i}.txt" for i in range(n))


class TestTarStreamPoison:
    """First write failure poisons the stream: later writes and finalize fail fast."""

    def _poisoned_stream(self, tmp_path, monkeypatch, request) -> TarStream:
        incomplete = str(tmp_path / "bkps.tgz.incomplete")
        stream = TarStream(incomplete)
        stream.write("ok.txt", b"fine")
        # The poisoned stream is returned still-open; close the gzip handle at teardown
        # so its finalizer doesn't raise "lost gzip_file" as an unraisable warning that
        # could mask a real one. abort() is idempotent and swallows close errors.
        request.addfinalizer(stream.abort)

        def boom(*_args, **_kwargs):
            raise OSError("disk full")
        # Poison via a failing member write on the underlying handle.
        monkeypatch.setattr(stream._tar, "addfile", boom)
        with pytest.raises(ArchiveWriteError):
            stream.write("bad.txt", b"payload")
        return stream

    def test_failed_write_raises_archive_write_error(self, tmp_path, monkeypatch, request):
        self._poisoned_stream(tmp_path, monkeypatch, request)

    def test_subsequent_write_fails_fast(self, tmp_path, monkeypatch, request):
        stream = self._poisoned_stream(tmp_path, monkeypatch, request)
        with pytest.raises(ArchiveWriteError):
            stream.write("later.txt", b"payload")

    def test_finalize_refuses_poisoned_stream(self, tmp_path, monkeypatch, request):
        stream = self._poisoned_stream(tmp_path, monkeypatch, request)
        with pytest.raises(ArchiveWriteError):
            stream.finalize()

    def test_subsequent_write_carries_first_error(self, tmp_path, monkeypatch, request):
        """Poisoned-stream raises must name the ROOT cause, not just 'already failed'."""
        stream = self._poisoned_stream(tmp_path, monkeypatch, request)
        with pytest.raises(ArchiveWriteError, match="disk full"):
            stream.write("later.txt", b"payload")

    def test_finalize_carries_first_error(self, tmp_path, monkeypatch, request):
        stream = self._poisoned_stream(tmp_path, monkeypatch, request)
        with pytest.raises(ArchiveWriteError, match="disk full"):
            stream.finalize()

    def test_open_failure_poisons(self, tmp_path):
        # Unwritable target: first write fails, second fails fast as poisoned.
        stream = TarStream(str(tmp_path / "no_such_dir" / "bkps.tgz.incomplete"))
        with pytest.raises(ArchiveWriteError):
            stream.write("a.txt", b"a")
        with pytest.raises(ArchiveWriteError):
            stream.write("b.txt", b"b")


class TestTarStreamLifecycle:
    """finalize/abort close semantics: idempotent, safe on every terminal path."""

    def test_finalize_without_writes_is_noop(self, tmp_path):
        stream = TarStream(str(tmp_path / "bkps.tgz.incomplete"))
        stream.finalize()  # nothing written, nothing to close, no error
        assert not (tmp_path / "bkps.tgz.incomplete").exists()

    def test_abort_never_raises_and_is_idempotent(self, tmp_path):
        incomplete = str(tmp_path / "bkps.tgz.incomplete")
        stream = TarStream(incomplete)
        stream.write("a.txt", b"a")
        stream.abort()
        stream.abort()  # double-abort: no error

    def test_abort_swallows_close_errors(self, tmp_path, monkeypatch, request):
        stream = TarStream(str(tmp_path / "bkps.tgz.incomplete"))
        stream.write("a.txt", b"a")

        def boom():
            raise OSError("flush failed")
        monkeypatch.setattr(stream._tar, "close", boom)
        # Mocking close() out entirely means the real gzip handle underneath is
        # never actually closed; close it directly at teardown so its finalizer
        # doesn't raise "lost gzip_file" as an unraisable warning that could mask
        # a real one.
        request.addfinalizer(stream._tar.fileobj.close)
        stream.abort()  # never raises, even when close blows up

    def test_finalize_close_failure_raises_archive_write_error(self, tmp_path, monkeypatch,
                                                                 request):
        stream = TarStream(str(tmp_path / "bkps.tgz.incomplete"))
        stream.write("a.txt", b"a")

        def boom():
            raise OSError("flush failed")
        monkeypatch.setattr(stream._tar, "close", boom)
        # Same as above: close() is mocked out, so the real fileobj is orphaned
        # unless we close it ourselves at teardown.
        request.addfinalizer(stream._tar.fileobj.close)
        with pytest.raises(ArchiveWriteError):
            stream.finalize()

    def test_abort_after_finalize_is_noop(self, tmp_path):
        """Success path: finalize() then the finally-block discard's abort()."""
        incomplete = str(tmp_path / "bkps.tgz.incomplete")
        stream = TarStream(incomplete)
        stream.write("a.txt", b"a")
        stream.finalize()
        stream.abort()
        # finalize's close already flushed a valid archive; abort didn't break it
        with tarfile.open(incomplete, "r:gz") as tar:
            assert tar.getnames() == ["a.txt"]

    def test_write_after_abort_raises(self, tmp_path):
        stream = TarStream(str(tmp_path / "bkps.tgz.incomplete"))
        stream.write("a.txt", b"a")
        stream.abort()
        with pytest.raises(ArchiveWriteError):
            stream.write("b.txt", b"b")
