# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name,unused-argument,protected-access
"""Unit tests for Archiver archive and clean-up behavior."""
import logging
import os
import re
from datetime import datetime
from typing import List
from unittest.mock import MagicMock

import pytest

from bookstack_file_exporter.archiver.archiver import Archiver
from bookstack_file_exporter.archiver.minio_archiver import MinioArchiver
from tests.fixtures.mock_config import make_mock_config as _make_config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def patched_page_archiver(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr(
        "bookstack_file_exporter.archiver.archiver.PageArchiver",
        MagicMock(return_value=mock),
    )
    return mock


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.base_dir_name = "bkps"
    config.user_inputs.keep_last = 1
    config.user_inputs.output_path = ""
    config.user_inputs.export_level = "pages"
    config.object_storage_config = {}
    return config


@pytest.fixture
def archiver_instance(patched_page_archiver, mock_config, mock_http_client):
    return Archiver(mock_config, mock_http_client)


# ---------------------------------------------------------------------------
# _generate_root_folder
# ---------------------------------------------------------------------------

class TestHasExportedContent:
    """has_exported_content reflects whether the intermediate tar exists on disk."""

    def test_false_when_tar_missing(self, archiver_instance, tmp_path):
        archiver_instance._archiver.tar_file = str(tmp_path / "absent.tar")
        assert archiver_instance.has_exported_content is False

    def test_true_when_tar_exists(self, archiver_instance, tmp_path):
        tar_path = tmp_path / "present.tar"
        tar_path.write_bytes(b"data")
        archiver_instance._archiver.tar_file = str(tar_path)
        assert archiver_instance.has_exported_content is True


class TestLevelBaseDir:
    """Non-default export levels suffix the archive base name (and thus scope keep_last)."""

    def test_pages_unchanged(self):
        assert Archiver._level_base_dir("bkps", "pages") == "bkps"

    @pytest.mark.parametrize("level", ["books", "chapters"])
    def test_non_pages_suffixed(self, level):
        assert Archiver._level_base_dir("bkps", level) == f"bkps_{level}"

    def test_books_level_flows_into_archive_dir(self, patched_page_archiver,
                                                mock_config, mock_http_client):
        mock_config.user_inputs.export_level = "books"
        archiver = Archiver(mock_config, mock_http_client)
        assert archiver.base_dir == "bkps_books"
        assert archiver.archive_dir.startswith("bkps_books_")


@pytest.mark.parametrize("base_name", ["bkps", "my_export", "abc-123"])
def test_generate_root_folder_format(monkeypatch, base_name):
    fixed_dt = datetime(2024, 3, 15, 10, 30, 45)
    monkeypatch.setattr(
        "bookstack_file_exporter.archiver.archiver.datetime",
        type("_FakeDT", (), {"now": staticmethod(lambda: fixed_dt)})(),
    )
    result = Archiver._generate_root_folder(base_name)
    expected = f"{base_name}_2024-03-15_10-30-45"
    assert result == expected


def test_archive_dir_has_timestamp_suffix(archiver_instance):
    """Archiver.archive_dir must end with _YYYY-MM-DD_HH-MM-SS."""
    assert re.search(r"_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$", archiver_instance.archive_dir)


# ---------------------------------------------------------------------------
# _filter_archives
# ---------------------------------------------------------------------------

@pytest.fixture
def five_files():
    return ["oldest.tgz", "old.tgz", "mid.tgz", "new.tgz", "newest.tgz"]


@pytest.fixture
def three_files():
    return ["oldest.tgz", "mid.tgz", "newest.tgz"]


@pytest.fixture
def one_file():
    return ["only.tgz"]


_real_os_stat = os.stat


def _make_stat_patcher(mapping: dict):
    """Return a callable that intercepts only known filenames; falls back to real os.stat."""
    stats = {f: MagicMock(st_ctime=ct) for f, ct in mapping.items()}

    def _patched(f, *args, **kwargs):
        key = f if isinstance(f, str) else str(f)
        if key in stats:
            return stats[key]
        return _real_os_stat(f, *args, **kwargs)

    return _patched


def test_filter_archives_5_files_keep_2(
    monkeypatch, archiver_instance, mock_config, five_files
):
    keep_last = 2
    expected_len = 3
    expected_oldest = ["oldest.tgz", "old.tgz", "mid.tgz"]
    mock_config.user_inputs.keep_last = keep_last
    fake_ctimes = {
        "oldest.tgz": 100,
        "old.tgz": 150,
        "mid.tgz": 200,
        "new.tgz": 250,
        "newest.tgz": 300,
    }
    monkeypatch.setattr(os, "stat", _make_stat_patcher(fake_ctimes))
    result = archiver_instance._filter_archives(five_files)
    assert len(result) == expected_len
    assert result == expected_oldest


def test_filter_archives_3_files_keep_5(
    monkeypatch, archiver_instance, mock_config, three_files
):
    """keep_last=5 with only 3 files — nothing to delete, returns []."""
    mock_config.user_inputs.keep_last = 5
    fake_ctimes = {"oldest.tgz": 100, "mid.tgz": 200, "newest.tgz": 300}
    monkeypatch.setattr(os, "stat", _make_stat_patcher(fake_ctimes))
    result = archiver_instance._filter_archives(three_files)
    assert not result


def test_filter_archives_3_files_keep_3(
    monkeypatch, archiver_instance, mock_config, three_files
):
    """keep_last=3 equal to count — nothing to delete, returns []."""
    mock_config.user_inputs.keep_last = 3
    fake_ctimes = {"oldest.tgz": 100, "mid.tgz": 200, "newest.tgz": 300}
    monkeypatch.setattr(os, "stat", _make_stat_patcher(fake_ctimes))
    result = archiver_instance._filter_archives(three_files)
    assert not result


def test_filter_archives_1_file_keep_1(
    monkeypatch, archiver_instance, mock_config, one_file
):
    """1 file, keep_last=1 — nothing to delete, returns []."""
    mock_config.user_inputs.keep_last = 1
    fake_ctimes = {"only.tgz": 100}
    monkeypatch.setattr(os, "stat", _make_stat_patcher(fake_ctimes))
    result = archiver_instance._filter_archives(one_file)
    assert not result


# ---------------------------------------------------------------------------
# _get_stale_archives
# ---------------------------------------------------------------------------

@pytest.fixture
def patch_scan_archives(monkeypatch):
    """Callable fixture: call it with a list to control util.scan_archives return value."""
    holder: List[List[str]] = [[]]

    def _set(file_list: List[str]):
        holder[0] = file_list
        monkeypatch.setattr(
            "bookstack_file_exporter.archiver.archiver.util.scan_archives",
            lambda base_dir, ext: holder[0],
        )

    return _set


def test_get_stale_archives_keep_last_negative(
    monkeypatch, archiver_instance, mock_config, patch_scan_archives
):
    """keep_last < 0 returns full archive list."""
    mock_config.user_inputs.keep_last = -1
    file_list = ["a.tgz", "b.tgz", "c.tgz"]
    patch_scan_archives(file_list)
    result = archiver_instance._get_stale_archives()
    assert result == file_list


def test_get_stale_archives_keep_last_zero_with_archives(
    monkeypatch, archiver_instance, mock_config, patch_scan_archives
):
    """keep_last=0: clean_up returns early before calling _get_stale_archives.
    But _get_stale_archives itself with keep_last=0 and 3 files:
    len(3) > 0 → calls _filter_archives(list) which returns 3 oldest."""
    mock_config.user_inputs.keep_last = 0
    file_list = ["a.tgz", "b.tgz", "c.tgz"]
    patch_scan_archives(file_list)
    fake_ctimes = {"a.tgz": 100, "b.tgz": 200, "c.tgz": 300}
    monkeypatch.setattr(os, "stat", _make_stat_patcher(fake_ctimes))
    result = archiver_instance._get_stale_archives()
    # to_delete = 3 - 0 = 3, so all 3 are returned
    assert result == ["a.tgz", "b.tgz", "c.tgz"]


def test_get_stale_archives_count_lte_keep_last(
    monkeypatch, archiver_instance, mock_config, patch_scan_archives
):
    """keep_last > 0, count <= keep_last → returns []."""
    mock_config.user_inputs.keep_last = 5
    patch_scan_archives(["a.tgz", "b.tgz"])
    result = archiver_instance._get_stale_archives()
    assert not result


def test_get_stale_archives_count_gt_keep_last(
    monkeypatch, archiver_instance, mock_config, patch_scan_archives
):
    """keep_last > 0, count > keep_last → returns oldest excess."""
    mock_config.user_inputs.keep_last = 2
    file_list = ["a.tgz", "b.tgz", "c.tgz", "d.tgz"]
    patch_scan_archives(file_list)
    fake_ctimes = {"a.tgz": 100, "b.tgz": 200, "c.tgz": 300, "d.tgz": 400}
    monkeypatch.setattr(os, "stat", _make_stat_patcher(fake_ctimes))
    result = archiver_instance._get_stale_archives()
    assert result == ["a.tgz", "b.tgz"]


def test_get_stale_archives_empty_list(
    monkeypatch, archiver_instance, mock_config, patch_scan_archives
):
    """No archive files found → returns []."""
    mock_config.user_inputs.keep_last = 3
    patch_scan_archives([])
    result = archiver_instance._get_stale_archives()
    assert not result


# ---------------------------------------------------------------------------
# create_export_dir
# ---------------------------------------------------------------------------

def test_create_export_dir_empty_path_skips_create_dir(
    monkeypatch, archiver_instance, mock_config
):
    """output_path='' → util.create_dir NOT called."""
    mock_config.user_inputs.output_path = ""
    calls: List[str] = []
    monkeypatch.setattr(
        "bookstack_file_exporter.archiver.archiver.util.create_dir",
        calls.append,
    )
    archiver_instance.create_export_dir()
    assert not calls


def test_create_export_dir_with_path_calls_create_dir(
    monkeypatch, archiver_instance, mock_config
):
    """output_path='x/y' → util.create_dir called with that path."""
    mock_config.user_inputs.output_path = "x/y"
    calls: List[str] = []
    monkeypatch.setattr(
        "bookstack_file_exporter.archiver.archiver.util.create_dir",
        calls.append,
    )
    archiver_instance.create_export_dir()
    assert calls == ["x/y"]


def test_create_export_dir_permission_error_logs_warning(
    monkeypatch, archiver_instance, mock_config, caplog
):
    """util.create_dir raises PermissionError → warning logged, no exception raised."""
    mock_config.user_inputs.output_path = "some/path"

    def _raise_perm(path):
        raise PermissionError("access denied")

    monkeypatch.setattr(
        "bookstack_file_exporter.archiver.archiver.util.create_dir",
        _raise_perm,
    )
    caplog.set_level(logging.WARNING, logger="bookstack_file_exporter.archiver.archiver")
    archiver_instance.create_export_dir()  # must not raise
    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("Failed to create base directory" in msg for msg in warning_messages)


# ---------------------------------------------------------------------------
# archive_remote
# ---------------------------------------------------------------------------

def test_archive_remote_dispatches_minio(monkeypatch, archiver_instance, mock_config):
    """object_storage_config has 'minio' key → _archive_minio invoked."""
    minio_mock = MagicMock()
    mock_config.object_storage_config = {"minio": minio_mock}
    minio_handler = MagicMock()
    monkeypatch.setattr(archiver_instance, "_archive_minio", minio_handler)
    archiver_instance.archive_remote()
    minio_handler.assert_called_once_with(minio_mock)


def test_archive_remote_raises_on_unknown_storage_type(
    patched_page_archiver, mock_config, mock_http_client
):
    """object_storage_config has unknown key → ValueError raised."""
    mock_config.object_storage_config = {"gcs": MagicMock()}
    archiver = Archiver(mock_config, mock_http_client)
    with pytest.raises(ValueError, match="unsupported remote storage type"):
        archiver.archive_remote()


def test_archive_remote_s3_raises_not_implemented(
    patched_page_archiver, mock_config, mock_http_client
):
    """archive_remote routes 's3' to _archive_s3 which is intentionally not implemented"""
    config = MagicMock()
    config.object_storage_config = {"s3": MagicMock()}
    config.base_dir_name = "bkps"
    archiver = Archiver(config, MagicMock())
    with pytest.raises(NotImplementedError, match="S3 remote storage"):
        archiver.archive_remote()


def test_archive_remote_empty_config_no_calls(archiver_instance, mock_config):
    """object_storage_config={} → no remote export methods called."""
    mock_config.object_storage_config = {}
    archiver_instance._archive_minio = MagicMock()
    archiver_instance._archive_s3 = MagicMock()
    archiver_instance.archive_remote()
    archiver_instance._archive_minio.assert_not_called()
    archiver_instance._archive_s3.assert_not_called()


# ---------------------------------------------------------------------------
# clean_up
# ---------------------------------------------------------------------------

def test_clean_up_keep_last_zero_returns_early(
    monkeypatch, archiver_instance, mock_config
):
    """keep_last=0 → early return, no scan, no delete."""
    mock_config.user_inputs.keep_last = 0
    scan_calls: List = []
    delete_calls: List = []
    monkeypatch.setattr(
        "bookstack_file_exporter.archiver.archiver.util.scan_archives",
        lambda *a, **kw: scan_calls.append(a) or [],
    )
    archiver_instance._delete_files = MagicMock(
        side_effect=lambda f: delete_calls.extend(f)  # pylint: disable=unnecessary-lambda
    )
    archiver_instance.clean_up()
    assert not scan_calls
    assert not delete_calls


def test_clean_up_with_stale_archives_calls_delete(
    monkeypatch, archiver_instance, mock_config
):
    """keep_last > 0 with stale archives → _delete_files called with stale list."""
    mock_config.user_inputs.keep_last = 1
    stale = ["old1.tgz", "old2.tgz"]
    archiver_instance._get_stale_archives = MagicMock(return_value=stale)
    archiver_instance._delete_files = MagicMock()
    archiver_instance.clean_up()
    archiver_instance._delete_files.assert_called_once_with(stale)


# ---------------------------------------------------------------------------
# MinioArchiver._generate_path — trailing-slash normalisation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("input_path,expected", [
    ("backups/",   "backups"),
    ("backups//",  "backups"),   # double-slash: old code leaves one slash, new code strips all
    ("backups",    "backups"),
    ("a/b/c/",     "a/b/c"),
    (None,         ""),
    ("",           ""),
])
def test_generate_path_strips_all_trailing_slashes(input_path, expected):
    """_generate_path must strip ALL trailing slashes, not just one."""
    result = MinioArchiver._generate_path(None, input_path)
    assert result == expected


# ---------------------------------------------------------------------------
# books-level archiver wires modify_links (Task 6)
# ---------------------------------------------------------------------------

class TestBooksArchiverModifyLinksWiring:
    def test_books_archiver_modify_links_active_when_configured(self, mock_http_client):
        config = _make_config(
            export_level="books",
            formats=["markdown"],
            modify_links=True,
            export_images=True,
        )
        config.base_dir_name = "bkps"
        config.user_inputs.keep_last = 0
        config.user_inputs.output_path = ""
        config.object_storage_config = {}
        archiver = Archiver(config, mock_http_client)
        assert archiver._archiver.modify_links is True

    def test_chapters_archiver_modify_links_active_when_configured(self, mock_http_client):
        config = _make_config(
            export_level="chapters",
            formats=["markdown"],
            modify_links=True,
            export_images=True,
        )
        config.base_dir_name = "bkps"
        config.user_inputs.keep_last = 0
        config.user_inputs.output_path = ""
        config.object_storage_config = {}
        archiver = Archiver(config, mock_http_client)
        assert archiver._archiver.modify_links is True
