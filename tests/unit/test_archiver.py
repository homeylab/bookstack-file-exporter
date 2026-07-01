# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name,unused-argument,protected-access,too-few-public-methods
"""Unit tests for Archiver archive and clean-up behavior."""
import logging
import os
import re
import threading
from datetime import datetime
from typing import List
from unittest.mock import MagicMock

import pytest

from bookstack_file_exporter.archiver.archiver import Archiver, AggregateUploadError
from bookstack_file_exporter.archiver.s3_archiver import S3CompatibleArchiver
from bookstack_file_exporter.notify.models import ExportStatus, UploadOutcome
from bookstack_file_exporter.archiver.node_archiver import (
    BookArchiver,
    ChapterArchiver,
    PageArchiver,
    _FILE_EXTENSION_MAP,
)
from tests.fixtures.mock_config import make_mock_config as _make_config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_config():
    config = MagicMock()
    config.base_dir_name = "bkps"
    config.user_inputs.keep_last = 1
    config.user_inputs.output_path = ""
    config.user_inputs.export_level = "pages"
    config.object_storage_config = []
    return config


@pytest.fixture
def archiver_instance(mock_config, mock_http_client):
    return Archiver(mock_config, mock_http_client, node_archiver=MagicMock())


# ---------------------------------------------------------------------------
# _generate_root_folder
# ---------------------------------------------------------------------------

class TestSetStop:
    def test_set_stop_forwards_to_node_archiver(self, archiver_instance):
        ev = threading.Event()
        archiver_instance.set_stop(ev)
        assert archiver_instance._archiver._stop is ev


class TestDiscardPartial:
    def test_removes_tar_and_partial_when_present(self, archiver_instance, tmp_path):
        tar = tmp_path / "bkps_2026.tar"
        partial = tmp_path / "bkps_2026.tgz.partial"
        tar.write_bytes(b"x")
        partial.write_bytes(b"y")
        archiver_instance._archiver.tar_file = str(tar)
        archiver_instance._archiver.archive_file = str(tmp_path / "bkps_2026.tgz")

        archiver_instance.discard_partial()

        assert not tar.exists()
        assert not partial.exists()

    def test_logs_each_removed_path(self, archiver_instance, tmp_path, caplog):
        tar = tmp_path / "bkps_2026.tar"
        tar.write_bytes(b"x")
        archiver_instance._archiver.tar_file = str(tar)
        archiver_instance._archiver.archive_file = str(tmp_path / "bkps_2026.tgz")

        with caplog.at_level(logging.INFO):
            archiver_instance.discard_partial()

        assert any(str(tar) in r.message and "partial" in r.message.lower()
                   for r in caplog.records)

    def test_no_log_when_nothing_to_discard(self, archiver_instance, tmp_path, caplog):
        archiver_instance._archiver.tar_file = str(tmp_path / "absent.tar")
        archiver_instance._archiver.archive_file = str(tmp_path / "absent.tgz")
        with caplog.at_level(logging.INFO):
            archiver_instance.discard_partial()
        assert not any("partial" in r.message.lower() for r in caplog.records)

    def test_no_error_when_nothing_to_discard(self, archiver_instance, tmp_path):
        archiver_instance._archiver.tar_file = str(tmp_path / "absent.tar")
        archiver_instance._archiver.archive_file = str(tmp_path / "absent.tgz")
        # must not raise (all-empty cycle writes no tar)
        archiver_instance.discard_partial()

    def test_does_not_touch_final_tgz(self, archiver_instance, tmp_path):
        final = tmp_path / "bkps_2026.tgz"
        final.write_bytes(b"done")
        archiver_instance._archiver.tar_file = str(tmp_path / "bkps_2026.tar")
        archiver_instance._archiver.archive_file = str(final)
        archiver_instance.discard_partial()
        assert final.exists()


class TestSweepOrphans:
    def test_removes_prior_tar_and_partial_orphans(self, archiver_instance, tmp_path):
        archiver_instance.config.base_dir_name = str(tmp_path / "bkps")
        archiver_instance._archiver.file_extension_map = _FILE_EXTENSION_MAP
        orphan_tar = tmp_path / "bkps_2026-01-01.tar"
        orphan_partial = tmp_path / "bkps_2026-01-01.tgz.partial"
        keep_tgz = tmp_path / "bkps_2026-01-01.tgz"
        for f in (orphan_tar, orphan_partial, keep_tgz):
            f.write_bytes(b"x")

        archiver_instance.sweep_orphans()

        assert not orphan_tar.exists()
        assert not orphan_partial.exists()
        assert keep_tgz.exists()  # finished archives are not swept

    def test_sweeps_orphans_across_export_levels(self, mock_config, mock_http_client,
                                                 tmp_path):
        """Orphan intermediates are always junk, so the sweep clears partials left by
        prior runs at OTHER export levels, not just its own level's base."""
        mock_config.base_dir_name = str(tmp_path / "bkps")
        mock_config.user_inputs.export_level = "books"
        archiver = Archiver(mock_config, mock_http_client, node_archiver=MagicMock())
        archiver._archiver.file_extension_map = _FILE_EXTENSION_MAP
        pages_partial = tmp_path / "bkps_2026-01-01.tgz.partial"
        books_partial = tmp_path / "bkps_books_2026-01-01.tgz.partial"
        chapters_partial = tmp_path / "bkps_chapters_2026-01-01.tgz.partial"
        keep_tgz = tmp_path / "bkps_2026-01-01.tgz"
        for f in (pages_partial, books_partial, chapters_partial, keep_tgz):
            f.write_bytes(b"x")

        archiver.sweep_orphans()

        assert not pages_partial.exists()
        assert not books_partial.exists()
        assert not chapters_partial.exists()
        assert keep_tgz.exists()  # finished archives are never swept


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

    def test_books_level_flows_into_archive_dir(self, mock_config, mock_http_client):
        mock_config.user_inputs.export_level = "books"
        archiver = Archiver(mock_config, mock_http_client, node_archiver=MagicMock())
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
# _build_archiver — level → type selection
# ---------------------------------------------------------------------------

class TestBuildArchiver:
    """_build_archiver returns the correct NodeArchiver subtype for each export level."""

    def test_books_level_returns_book_archiver(self, mock_http_client):
        config = _make_config(export_level="books", formats=["markdown"])
        config.base_dir_name = "bkps"
        config.user_inputs.keep_last = 0
        config.user_inputs.output_path = ""
        config.object_storage_config = []
        archiver = Archiver(config, mock_http_client)
        assert isinstance(archiver._archiver, BookArchiver)

    def test_chapters_level_returns_chapter_archiver(self, mock_http_client):
        config = _make_config(export_level="chapters", formats=["markdown"])
        config.base_dir_name = "bkps"
        config.user_inputs.keep_last = 0
        config.user_inputs.output_path = ""
        config.object_storage_config = []
        archiver = Archiver(config, mock_http_client)
        assert isinstance(archiver._archiver, ChapterArchiver)

    def test_pages_level_returns_page_archiver(self, mock_http_client):
        config = _make_config(export_level="pages", formats=["markdown"])
        config.base_dir_name = "bkps"
        config.user_inputs.keep_last = 0
        config.user_inputs.output_path = ""
        config.object_storage_config = []
        archiver = Archiver(config, mock_http_client)
        assert isinstance(archiver._archiver, PageArchiver)


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

# ---------------------------------------------------------------------------
# archive_remote — attempt-all, returns list[UploadOutcome]
# ---------------------------------------------------------------------------

def _provider_entry(label="target-b"):
    obj = MagicMock()
    obj.name = label
    return obj


def test_archive_remote_empty_list_no_outcomes(archiver_instance, mock_config):
    mock_config.object_storage_config = []
    fake_cls = MagicMock()
    archiver_instance._s3_archiver_cls = fake_cls
    assert archiver_instance.archive_remote() == []
    fake_cls.assert_not_called()


def test_archive_remote_all_success(archiver_instance, mock_config):
    mock_config.object_storage_config = [
        _provider_entry("minio/b"), _provider_entry("s3/aws")]
    fake_instance = MagicMock()
    fake_instance.upload_backup.side_effect = ["minio-b/a.tgz", "s3-aws/a.tgz"]
    archiver_instance._s3_archiver_cls = MagicMock(return_value=fake_instance)
    archiver_instance._archiver.archive_file = "/local/archive.tgz"
    archiver_instance._archiver.file_extension_map = {"tgz": ".tgz"}

    outcomes = archiver_instance.archive_remote()

    assert [(o.label, o.dest, o.error) for o in outcomes] == [
        ("minio/b", "minio-b/a.tgz", None), ("s3/aws", "s3-aws/a.tgz", None)]


def test_archive_remote_one_fails_others_still_attempted(archiver_instance, mock_config):
    """A failing target does not abort the loop; its outcome records the error."""
    mock_config.object_storage_config = [
        _provider_entry("minio/b"), _provider_entry("s3/dr")]
    good = MagicMock()
    good.upload_backup.return_value = "minio-b/a.tgz"
    bad = MagicMock()
    bad.upload_backup.side_effect = RuntimeError("connection refused")
    archiver_instance._s3_archiver_cls = MagicMock(side_effect=[good, bad])
    archiver_instance._archiver.archive_file = "/local/archive.tgz"
    archiver_instance._archiver.file_extension_map = {"tgz": ".tgz"}

    outcomes = archiver_instance.archive_remote()

    assert outcomes[0].dest == "minio-b/a.tgz" and outcomes[0].error is None
    assert outcomes[1].dest is None
    assert "connection refused" in outcomes[1].error


def test_archive_remote_construction_failure_recorded(archiver_instance, mock_config):
    """A failure constructing the archiver (e.g. bucket validation) is also caught."""
    mock_config.object_storage_config = [_provider_entry("s3/dr")]
    archiver_instance._s3_archiver_cls = MagicMock(side_effect=ValueError("no such bucket"))
    archiver_instance._archiver.archive_file = "/local/archive.tgz"
    archiver_instance._archiver.file_extension_map = {"tgz": ".tgz"}

    outcomes = archiver_instance.archive_remote()

    assert outcomes[0].label == "s3/dr"
    assert outcomes[0].dest is None
    assert "no such bucket" in outcomes[0].error


# ---------------------------------------------------------------------------
# resolve_remote_status
# ---------------------------------------------------------------------------

def _ok(label="a"):
    return UploadOutcome(label=label, dest=f"{label}/x.tgz", error=None)


def _fail(label="a"):
    return UploadOutcome(label=label, dest=None, error="boom")


def test_resolve_status_all_success(archiver_instance):
    status = archiver_instance.resolve_remote_status([_ok("a"), _ok("b")])
    assert status is ExportStatus.SUCCESS


def test_resolve_status_some_fail_is_partial(archiver_instance, mock_config):
    mock_config.user_inputs.keep_last = -1   # even with -1, a remote copy survived
    status = archiver_instance.resolve_remote_status([_ok("a"), _fail("b")])
    assert status is ExportStatus.PARTIAL


def test_resolve_status_all_fail_local_kept_is_partial(archiver_instance, mock_config):
    mock_config.user_inputs.keep_last = 0    # local copy retained -> degraded, not lost
    status = archiver_instance.resolve_remote_status([_fail("a"), _fail("b")])
    assert status is ExportStatus.PARTIAL


def test_resolve_status_all_fail_no_local_raises(archiver_instance, mock_config):
    mock_config.user_inputs.keep_last = -1   # local deleted + all uploads fail = total loss
    with pytest.raises(AggregateUploadError, match="a, b"):
        archiver_instance.resolve_remote_status([_fail("a"), _fail("b")])


def test_resolve_status_empty_is_success(archiver_instance):
    assert archiver_instance.resolve_remote_status([]) is ExportStatus.SUCCESS


def test_archive_remote_retention_failure_is_warning_not_failure(archiver_instance, mock_config):
    """Upload succeeds but remote retention cleanup raises -> dest kept, warning set."""
    mock_config.object_storage_config = [_provider_entry("s3/aws")]
    inst = MagicMock()
    inst.upload_backup.return_value = "s3-aws/a.tgz"
    inst.clean_up.side_effect = RuntimeError("delete denied")
    archiver_instance._s3_archiver_cls = MagicMock(return_value=inst)
    archiver_instance._archiver.archive_file = "/local/archive.tgz"
    archiver_instance._archiver.file_extension_map = {"tgz": ".tgz"}

    outcomes = archiver_instance.archive_remote()

    assert outcomes[0].dest == "s3-aws/a.tgz"
    assert outcomes[0].error is None
    assert "delete denied" in outcomes[0].warning


def test_resolve_status_upload_ok_but_warning_is_partial(archiver_instance):
    out = [UploadOutcome(label="a", dest="a/x.tgz", error=None, warning="prune failed")]
    assert archiver_instance.resolve_remote_status(out) is ExportStatus.PARTIAL


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
    result = archiver_instance.clean_up()
    assert not scan_calls
    assert not delete_calls
    assert result == []


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


def test_clean_up_keep_last_negative_returns_full_list(
    monkeypatch, archiver_instance, mock_config, patch_scan_archives
):
    """keep_last < 0: all archives are in the returned deleted list (current .tgz included)."""
    mock_config.user_inputs.keep_last = -1
    file_list = ["/data/current.tgz", "/data/old.tgz", "/data/older.tgz"]
    patch_scan_archives(file_list)
    archiver_instance._delete_files = MagicMock()
    result = archiver_instance.clean_up()
    assert result == file_list
    archiver_instance._delete_files.assert_called_once_with(file_list)


def test_clean_up_keep_last_positive_returns_only_old_archives(
    monkeypatch, archiver_instance, mock_config, patch_scan_archives
):
    """keep_last > 0 with more archives than cap: only the excess (old) ones returned."""
    mock_config.user_inputs.keep_last = 1
    # Three archives; keep_last=1 → 2 oldest should be deleted, newest kept
    file_list = ["old1.tgz", "old2.tgz", "current.tgz"]
    patch_scan_archives(file_list)
    fake_ctimes = {"old1.tgz": 100, "old2.tgz": 200, "current.tgz": 300}
    monkeypatch.setattr(os, "stat", _make_stat_patcher(fake_ctimes))
    archiver_instance._delete_files = MagicMock()
    result = archiver_instance.clean_up()
    assert result == ["old1.tgz", "old2.tgz"]
    assert "current.tgz" not in result


# ---------------------------------------------------------------------------
# S3CompatibleArchiver._generate_prefix — trailing-slash normalisation
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
    """_generate_prefix must strip ALL trailing slashes, not just one."""
    result = S3CompatibleArchiver._generate_prefix(None, input_path)
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
        config.object_storage_config = []
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
        config.object_storage_config = []
        archiver = Archiver(config, mock_http_client)
        assert archiver._archiver.modify_links is True
