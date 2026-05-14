import gzip
import json
import os
import tarfile
from pathlib import Path

import pytest

from bookstack_file_exporter.archiver import util


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
# write_tar
# ---------------------------------------------------------------------------

def test_write_tar_creates_tar_file(tmp_path):
    tar_path = str(tmp_path / "archive.tar")
    util.write_tar(tar_path, "hello.txt", b"hello world")
    assert os.path.isfile(tar_path)


def test_write_tar_appends_entry(tmp_path):
    tar_path = str(tmp_path / "archive.tar")
    util.write_tar(tar_path, "file1.txt", b"data1")
    util.write_tar(tar_path, "file2.txt", b"data2")
    with tarfile.open(tar_path, "r") as tar:
        names = tar.getnames()
    assert "file1.txt" in names
    assert "file2.txt" in names


def test_write_tar_correct_content(tmp_path):
    tar_path = str(tmp_path / "archive.tar")
    content = b"exact bytes"
    util.write_tar(tar_path, "doc.txt", content)
    with tarfile.open(tar_path, "r") as tar:
        member = tar.getmember("doc.txt")
        extracted = tar.extractfile(member).read()
    assert extracted == content


def test_write_tar_entry_size_matches(tmp_path):
    tar_path = str(tmp_path / "archive.tar")
    content = b"size check"
    util.write_tar(tar_path, "check.txt", content)
    with tarfile.open(tar_path, "r") as tar:
        member = tar.getmember("check.txt")
    assert member.size == len(content)


# ---------------------------------------------------------------------------
# create_gzip
# ---------------------------------------------------------------------------

def test_create_gzip_produces_gzip_file(tmp_path):
    src = tmp_path / "source.tar"
    src.write_bytes(b"raw bytes")
    gz = tmp_path / "source.tar.gz"
    util.create_gzip(str(src), str(gz))
    assert gz.is_file()


def test_create_gzip_removes_original_by_default(tmp_path):
    src = tmp_path / "source.tar"
    src.write_bytes(b"raw bytes")
    gz = tmp_path / "source.tar.gz"
    util.create_gzip(str(src), str(gz))
    assert not src.exists()


def test_create_gzip_keeps_original_when_remove_old_false(tmp_path):
    src = tmp_path / "source.tar"
    src.write_bytes(b"raw bytes")
    gz = tmp_path / "source.tar.gz"
    util.create_gzip(str(src), str(gz), remove_old=False)
    assert src.exists()


def test_create_gzip_content_survives_round_trip(tmp_path):
    original = b"important data"
    src = tmp_path / "data.tar"
    src.write_bytes(original)
    gz = tmp_path / "data.tar.gz"
    util.create_gzip(str(src), str(gz), remove_old=False)
    with gzip.open(str(gz), "rb") as f:
        recovered = f.read()
    assert recovered == original


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
    assert results == []


def test_scan_archives_extension_filter(tmp_path):
    base = str(tmp_path / "backup")
    Path(f"{base}_v1.tar.gz").touch()
    Path(f"{base}_v2.zip").touch()
    gz_results = util.scan_archives(base, ".tar.gz")
    zip_results = util.scan_archives(base, ".zip")
    assert len(gz_results) == 1
    assert len(zip_results) == 1
