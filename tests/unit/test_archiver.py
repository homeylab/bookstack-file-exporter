# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name,unused-argument,protected-access,too-few-public-methods
"""Unit tests for Archiver archive and clean-up behavior."""
import logging
import os
import re
import threading
from datetime import datetime, timezone
from typing import List
from unittest.mock import MagicMock

import pytest

from bookstack_file_exporter.archiver.archiver import Archiver, AggregateUploadError
from bookstack_file_exporter.notify.models import ExportStatus, UploadOutcome
from bookstack_file_exporter.archiver.node_archiver import (
    BookArchiver,
    ChapterArchiver,
    PageArchiver,
    _FILE_EXTENSION_MAP,
)
from bookstack_file_exporter.common.util import EXPORT_BASENAME
from tests.fixtures.mock_config import make_mock_config as _make_config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_config():
    config = MagicMock()
    config.base_dir_name = "bkps"
    config.output_dir = ""
    config.user_inputs.keep_last = 1
    config.user_inputs.output_path = ""
    config.user_inputs.export_level = "pages"
    config.user_inputs.prune_on_partial = False
    config.object_storage_config = []
    return config


@pytest.fixture
def archiver_instance(mock_config, mock_http_client):
    archiver = Archiver(mock_config, mock_http_client, node_archiver=MagicMock())
    # Real empty lists (not a truthy MagicMock) so prune_allowed's `failed_nodes or
    # failed_assets` check reflects a clean run by default; tests that need a
    # degraded run overwrite these locally.
    archiver._archiver.failed_node_exports = []
    archiver._archiver.failed_asset_downloads = []
    return archiver


# ---------------------------------------------------------------------------
# _generate_root_folder
# ---------------------------------------------------------------------------

class TestSetStop:
    def test_set_stop_forwards_to_node_archiver(self, archiver_instance):
        ev = threading.Event()
        archiver_instance.set_stop(ev)
        archiver_instance._archiver.set_stop.assert_called_once_with(ev)


class TestDiscardIncomplete:
    """discard_incomplete aborts the stream and removes only this run's .incomplete."""

    def test_removes_incomplete_and_leaves_final_tgz(self, archiver_instance, tmp_path):
        incomplete = tmp_path / "bkps_2026.tgz.incomplete"
        final = tmp_path / "bkps_2026.tgz"
        incomplete.write_bytes(b"incomplete")
        final.write_bytes(b"final")
        archiver_instance._archiver.incomplete_file = str(incomplete)
        archiver_instance.discard_incomplete()
        assert not incomplete.exists()
        assert final.exists()

    def test_noop_when_nothing_on_disk(self, archiver_instance, tmp_path):
        archiver_instance._archiver.incomplete_file = str(tmp_path / "absent.tgz.incomplete")
        archiver_instance.discard_incomplete()  # no raise

    def test_aborts_stream_before_unlink(self, archiver_instance, tmp_path):
        # The archiver_instance fixture injects a MagicMock node archiver,
        # so assert the ORDERING contract on the mock:
        # abort_archive must run while the .incomplete is still on disk.
        incomplete = tmp_path / "bkps_2026.tgz.incomplete"
        incomplete.write_bytes(b"stream")
        archiver_instance._archiver.incomplete_file = str(incomplete)
        order = []
        archiver_instance._archiver.abort_archive.side_effect = (
            lambda: order.append(("abort", incomplete.exists())))
        archiver_instance.discard_incomplete()
        assert order == [("abort", True)]
        assert not incomplete.exists()


class TestSweepOrphans:
    def test_removes_prior_tar_and_incomplete_orphans(self, archiver_instance, tmp_path):
        archiver_instance.config.base_dir_name = str(tmp_path / "bkps")
        archiver_instance._archiver.file_extension_map = _FILE_EXTENSION_MAP
        orphan_tar = tmp_path / "bkps_2026-01-01.tar"
        orphan_incomplete = tmp_path / "bkps_2026-01-01.tgz.incomplete"
        keep_tgz = tmp_path / "bkps_2026-01-01.tgz"
        for f in (orphan_tar, orphan_incomplete, keep_tgz):
            f.write_bytes(b"x")

        archiver_instance.sweep_orphans()

        assert not orphan_tar.exists()
        assert not orphan_incomplete.exists()
        assert keep_tgz.exists()  # finished archives are not swept

    def test_sweeps_orphans_across_export_levels(self, mock_config, mock_http_client,
                                                 tmp_path):
        """Orphan intermediates are always junk, so the sweep clears incompletes left by
        prior runs at OTHER export levels, not just its own level's base."""
        mock_config.base_dir_name = str(tmp_path / "bkps")
        mock_config.user_inputs.export_level = "books"
        archiver = Archiver(mock_config, mock_http_client, node_archiver=MagicMock())
        archiver._archiver.file_extension_map = _FILE_EXTENSION_MAP
        pages_incomplete = tmp_path / "bkps_2026-01-01.tgz.incomplete"
        books_incomplete = tmp_path / "bkps_books_2026-01-01.tgz.incomplete"
        chapters_incomplete = tmp_path / "bkps_chapters_2026-01-01.tgz.incomplete"
        keep_tgz = tmp_path / "bkps_2026-01-01.tgz"
        for f in (pages_incomplete, books_incomplete, chapters_incomplete, keep_tgz):
            f.write_bytes(b"x")

        archiver.sweep_orphans()

        assert not pages_incomplete.exists()
        assert not books_incomplete.exists()
        assert not chapters_incomplete.exists()
        assert keep_tgz.exists()  # finished archives are never swept


class TestHasExportedContent:
    """has_exported_content reflects whether the streaming .incomplete exists on disk."""

    def test_false_when_no_incomplete(self, archiver_instance, tmp_path):
        archiver_instance._archiver.incomplete_file = str(tmp_path / "absent.tgz.incomplete")
        assert archiver_instance.has_exported_content is False

    def test_true_when_incomplete_exists(self, archiver_instance, tmp_path):
        incomplete = tmp_path / "bkps_2026.tgz.incomplete"
        incomplete.write_bytes(b"stream")
        archiver_instance._archiver.incomplete_file = str(incomplete)
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
    fake_now = MagicMock(return_value=fixed_dt)
    monkeypatch.setattr(
        "bookstack_file_exporter.archiver.archiver.datetime",
        type("_FakeDT", (), {"now": staticmethod(fake_now)})(),
    )
    result = Archiver._generate_root_folder(base_name)
    expected = f"{base_name}_2024-03-15_10-30-45"
    assert result == expected
    fake_now.assert_called_once_with(timezone.utc)


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
    # filenames embed the run timestamp, chronological order == basename sort order
    return [
        "bkps_2024-01-01_00-00-00.tgz",
        "bkps_2024-01-02_00-00-00.tgz",
        "bkps_2024-01-03_00-00-00.tgz",
        "bkps_2024-01-04_00-00-00.tgz",
        "bkps_2024-01-05_00-00-00.tgz",
    ]


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
    expected_oldest = five_files[:3]
    mock_config.user_inputs.keep_last = keep_last
    # ctimes are deliberately reversed (newest-first): a chmod/chown -R or volume
    # restore can reset ctime, so prune order must follow the filename timestamp,
    # not stat times. If _filter_archives ever regresses to sorting by ctime,
    # this assertion flips to the wrong 3 files and fails.
    fake_ctimes = dict(zip(five_files, [500, 400, 300, 200, 100]))
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
    file_list = [f"{EXPORT_BASENAME}_a.tgz", f"{EXPORT_BASENAME}_b.tgz", f"{EXPORT_BASENAME}_c.tgz"]
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
    file_list = [f"{EXPORT_BASENAME}_a.tgz", f"{EXPORT_BASENAME}_b.tgz", f"{EXPORT_BASENAME}_c.tgz"]
    patch_scan_archives(file_list)
    fake_ctimes = dict(zip(file_list, [100, 200, 300]))
    monkeypatch.setattr(os, "stat", _make_stat_patcher(fake_ctimes))
    result = archiver_instance._get_stale_archives()
    # to_delete = 3 - 0 = 3, so all 3 are returned
    assert result == file_list


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
    file_list = [f"{EXPORT_BASENAME}_a.tgz", f"{EXPORT_BASENAME}_b.tgz",
                 f"{EXPORT_BASENAME}_c.tgz", f"{EXPORT_BASENAME}_d.tgz"]
    patch_scan_archives(file_list)
    fake_ctimes = dict(zip(file_list, [100, 200, 300, 400]))
    monkeypatch.setattr(os, "stat", _make_stat_patcher(fake_ctimes))
    result = archiver_instance._get_stale_archives()
    assert result == [f"{EXPORT_BASENAME}_a.tgz", f"{EXPORT_BASENAME}_b.tgz"]


def test_get_stale_archives_empty_list(
    monkeypatch, archiver_instance, mock_config, patch_scan_archives
):
    """No archive files found → returns []."""
    mock_config.user_inputs.keep_last = 3
    patch_scan_archives([])
    result = archiver_instance._get_stale_archives()
    assert not result


def _name(level_token: str, ts: str, partial: bool = False) -> str:
    """Build a production-shaped archive path for retention tests."""
    infix = f"{level_token}_" if level_token else ""
    suffix = "_partial" if partial else ""
    return f"/data/{EXPORT_BASENAME}_{infix}{ts}{suffix}.tgz"


def test_get_stale_archives_splits_full_and_partial_independently(
    archiver_instance, mock_config, patch_scan_archives
):
    """keep_last=1 pages run: keep newest full + newest partial, prune the rest of
    each group; the two groups never evict each other."""
    mock_config.user_inputs.keep_last = 1
    mock_config.user_inputs.export_level = "pages"
    # file_extension_map must resolve to a real ".tgz" so the production code's
    # partial-suffix check (built from this map) can actually match filenames;
    # the bare MagicMock default returns an unconfigured mock instead of ".tgz".
    archiver_instance._archiver.file_extension_map = {"tgz": ".tgz"}
    fulls = [_name("", "2026-01-01_00-00-00"), _name("", "2026-01-02_00-00-00")]
    partials = [_name("", "2026-01-01_00-00-00", partial=True),
                _name("", "2026-01-02_00-00-00", partial=True)]
    patch_scan_archives(fulls + partials)

    stale = sorted(archiver_instance._get_stale_archives())

    # oldest of each group pruned, newest of each kept
    assert stale == sorted([fulls[0], partials[0]])


def test_get_stale_archives_partial_run_never_evicts_full(
    archiver_instance, mock_config, patch_scan_archives
):
    """N fulls already at cap + a fresh partial: fulls untouched (nothing added a
    full), only surplus partials (none here) pruned."""
    mock_config.user_inputs.keep_last = 2
    mock_config.user_inputs.export_level = "pages"
    archiver_instance._archiver.file_extension_map = {"tgz": ".tgz"}
    fulls = [_name("", "2026-01-01_00-00-00"), _name("", "2026-01-02_00-00-00")]
    partials = [_name("", "2026-01-03_00-00-00", partial=True)]
    patch_scan_archives(fulls + partials)

    assert archiver_instance._get_stale_archives() == []


def test_get_stale_archives_is_level_scoped(
    archiver_instance, mock_config, patch_scan_archives
):
    """A pages run must not consider books/chapters archives (pages-superset bug)."""
    mock_config.user_inputs.keep_last = 1
    mock_config.user_inputs.export_level = "pages"
    pages = [_name("", "2026-01-01_00-00-00"), _name("", "2026-01-02_00-00-00")]
    others = [_name("books", "2026-01-01_00-00-00"),
              _name("chapters", "2026-01-01_00-00-00")]
    patch_scan_archives(pages + others)

    stale = archiver_instance._get_stale_archives()

    assert stale == [pages[0]]          # only the oldest pages full
    assert all(o not in stale for o in others)


def test_get_stale_archives_books_run_only_books(
    archiver_instance, mock_config, patch_scan_archives
):
    mock_config.user_inputs.keep_last = 1
    mock_config.user_inputs.export_level = "books"
    books = [_name("books", "2026-01-01_00-00-00"), _name("books", "2026-01-02_00-00-00")]
    pages = [_name("", "2026-01-01_00-00-00")]
    patch_scan_archives(books + pages)

    assert archiver_instance._get_stale_archives() == [books[0]]


def test_get_stale_archives_keep_last_negative_wipes_only_current_level(
    archiver_instance, mock_config, patch_scan_archives
):
    """keep_last<0 wipes this level's archives (both groups) but leaves other levels."""
    mock_config.user_inputs.keep_last = -1
    mock_config.user_inputs.export_level = "pages"
    pages = [_name("", "2026-01-01_00-00-00"),
             _name("", "2026-01-02_00-00-00", partial=True)]
    others = [_name("books", "2026-01-01_00-00-00")]
    patch_scan_archives(pages + others)

    stale = sorted(archiver_instance._get_stale_archives())

    assert stale == sorted(pages)
    assert others[0] not in stale


# ---------------------------------------------------------------------------
# create_export_dir
# ---------------------------------------------------------------------------

def test_create_export_dir_empty_path_skips_create_dir(
    monkeypatch, archiver_instance, mock_config
):
    """output_dir='' → util.create_dir NOT called."""
    mock_config.output_dir = ""
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
    """output_dir='x/y' → util.create_dir called with that path."""
    mock_config.output_dir = "x/y"
    calls: List[str] = []
    monkeypatch.setattr(
        "bookstack_file_exporter.archiver.archiver.util.create_dir",
        calls.append,
    )
    archiver_instance.create_export_dir()
    assert calls == ["x/y"]


def test_create_export_dir_permission_error_fails_fast(
    monkeypatch, archiver_instance, mock_config, caplog
):
    """util.create_dir raises PermissionError → pointed error logged, exception propagates."""
    mock_config.output_dir = "some/path"

    def _raise_perm(path):
        raise PermissionError("access denied")

    monkeypatch.setattr(
        "bookstack_file_exporter.archiver.archiver.util.create_dir",
        _raise_perm,
    )
    caplog.set_level(logging.ERROR, logger="bookstack_file_exporter.archiver.archiver")
    with pytest.raises(PermissionError):
        archiver_instance.create_export_dir()
    error_messages = [r.message for r in caplog.records if r.levelno == logging.ERROR]
    assert any("Cannot create export directory" in msg for msg in error_messages)


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
    """All targets upload; outcome order matches config order regardless of which
    upload finishes first (results are keyed by target, not by call order)."""
    mock_config.object_storage_config = [
        _provider_entry("minio/b"), _provider_entry("s3/aws")]
    dests = {"minio/b": "minio-b/a.tgz", "s3/aws": "s3-aws/a.tgz"}

    def make_instance(provider_config):
        inst = MagicMock()
        inst.upload_backup.return_value = dests[provider_config.name]
        return inst

    archiver_instance._s3_archiver_cls = MagicMock(side_effect=make_instance)
    archiver_instance._archiver.archive_file = "/local/archive.tgz"
    archiver_instance._archiver.file_extension_map = {"tgz": ".tgz"}

    outcomes = archiver_instance.archive_remote()

    assert [(o.label, o.dest, o.error) for o in outcomes] == [
        ("minio/b", "minio-b/a.tgz", None), ("s3/aws", "s3-aws/a.tgz", None)]


def test_archive_remote_one_fails_others_still_attempted(archiver_instance, mock_config):
    """A failing target does not abort the batch; its outcome records the error."""
    mock_config.object_storage_config = [
        _provider_entry("minio/b"), _provider_entry("s3/dr")]

    def make_instance(provider_config):
        inst = MagicMock()
        if provider_config.name == "s3/dr":
            inst.upload_backup.side_effect = RuntimeError("connection refused")
        else:
            inst.upload_backup.return_value = "minio-b/a.tgz"
        return inst

    archiver_instance._s3_archiver_cls = MagicMock(side_effect=make_instance)
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


def test_archive_remote_uploads_run_concurrently(archiver_instance, mock_config):
    """Both uploads must be in flight at once: each upload blocks on a 2-party
    barrier, so a serial implementation deadlocks the first upload until the
    5s barrier timeout turns it into an error outcome and fails the assert."""
    barrier = threading.Barrier(2, timeout=5)
    mock_config.object_storage_config = [
        _provider_entry("minio/b"), _provider_entry("s3/aws")]

    def make_instance(provider_config):
        inst = MagicMock()

        def upload(_path):
            barrier.wait()
            return f"{provider_config.name}/a.tgz"

        inst.upload_backup.side_effect = upload
        return inst

    archiver_instance._s3_archiver_cls = MagicMock(side_effect=make_instance)
    archiver_instance._archiver.archive_file = "/local/archive.tgz"
    archiver_instance._archiver.file_extension_map = {"tgz": ".tgz"}

    outcomes = archiver_instance.archive_remote()

    assert [o.dest for o in outcomes] == ["minio/b/a.tgz", "s3/aws/a.tgz"]
    assert [o.error for o in outcomes] == [None, None]


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
    mock_config.user_inputs.keep_last = -1   # no lasting local copy, all uploads fail = total loss
    with pytest.raises(AggregateUploadError, match="a, b") as excinfo:
        archiver_instance.resolve_remote_status([_fail("a"), _fail("b")])
    msg = str(excinfo.value)
    assert "all upload targets failed" in msg
    assert "only the local copy remains" in msg


def test_resolve_status_empty_is_success(archiver_instance):
    assert archiver_instance.resolve_remote_status([]) is ExportStatus.SUCCESS


def test_archive_remote_records_pruned_count(archiver_instance, mock_config):
    """Remote retention deletions are carried on the outcome for notifications."""
    mock_config.object_storage_config = [_provider_entry("s3/aws")]
    inst = MagicMock()
    inst.upload_backup.return_value = "s3-aws/a.tgz"
    inst.clean_up.return_value = 3
    archiver_instance._s3_archiver_cls = MagicMock(return_value=inst)
    archiver_instance._archiver.archive_file = "/local/archive.tgz"
    archiver_instance._archiver.file_extension_map = {"tgz": ".tgz"}

    outcomes = archiver_instance.archive_remote()

    assert outcomes[0].dest == "s3-aws/a.tgz"
    assert outcomes[0].pruned == 3


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


def test_remote_prune_skipped_when_degraded(archiver_instance, mock_config):
    """A degraded run (content loss) still uploads to remote targets but must not
    trigger remote retention -- mirrors clean_up's local prune_allowed gate."""
    mock_config.object_storage_config = [_provider_entry("s3/aws")]
    inst = MagicMock()
    inst.upload_backup.return_value = "s3-aws/a.tgz"
    archiver_instance._s3_archiver_cls = MagicMock(return_value=inst)
    archiver_instance._archiver.archive_file = "/local/archive.tgz"
    archiver_instance._archiver.file_extension_map = {"tgz": ".tgz"}
    archiver_instance._archiver.failed_node_exports = ["books/x"]
    archiver_instance._archiver.failed_asset_downloads = []

    outcomes = archiver_instance.archive_remote()

    assert outcomes[0].dest == "s3-aws/a.tgz"
    assert outcomes[0].pruned == 0
    inst.clean_up.assert_not_called()


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
    file_list = [f"/data/{EXPORT_BASENAME}_current.tgz", f"/data/{EXPORT_BASENAME}_old.tgz",
                 f"/data/{EXPORT_BASENAME}_older.tgz"]
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
    # Three archives, filenames carry the run timestamp; keep_last=1 -> the 2
    # oldest by filename should be deleted, newest kept.
    file_list = [
        f"{EXPORT_BASENAME}_2024-01-01_00-00-00.tgz",
        f"{EXPORT_BASENAME}_2024-01-02_00-00-00.tgz",
        f"{EXPORT_BASENAME}_2024-01-03_00-00-00.tgz",
    ]
    patch_scan_archives(file_list)
    # ctimes are deliberately reversed to prove prune order follows the filename
    # timestamp, not stat times (which chmod/chown -R or a volume restore can reset).
    fake_ctimes = dict(zip(file_list, [300, 200, 100]))
    monkeypatch.setattr(os, "stat", _make_stat_patcher(fake_ctimes))
    archiver_instance._delete_files = MagicMock()
    result = archiver_instance.clean_up()
    assert result == file_list[:2]
    assert file_list[2] not in result


# ---------------------------------------------------------------------------
# prune_allowed / retention_configured (Task 5)
# ---------------------------------------------------------------------------

def test_clean_up_skipped_when_content_degraded(
    archiver_instance, mock_config, patch_scan_archives
):
    """A partial run (failed node export) skips pruning even though keep_last > 0
    and stale archives exist -- degraded backups must never evict complete ones."""
    mock_config.user_inputs.keep_last = 2
    archiver_instance._archiver.failed_node_exports = ["books/x"]
    archiver_instance._archiver.failed_asset_downloads = []
    patch_scan_archives(["old1.tgz", "old2.tgz"])
    archiver_instance._delete_files = MagicMock()

    assert archiver_instance.prune_allowed is False
    result = archiver_instance.clean_up()

    assert result == []
    archiver_instance._delete_files.assert_not_called()


def test_clean_up_runs_when_degraded_but_prune_on_partial(
    archiver_instance, mock_config, patch_scan_archives
):
    """prune_on_partial: true restores v2 unconditional-prune behavior even on a
    degraded (partial) run."""
    mock_config.user_inputs.keep_last = 2
    mock_config.user_inputs.prune_on_partial = True
    archiver_instance._archiver.failed_node_exports = ["books/x"]
    archiver_instance._archiver.failed_asset_downloads = []
    stale = ["old1.tgz", "old2.tgz"]
    archiver_instance._get_stale_archives = MagicMock(return_value=stale)
    archiver_instance._delete_files = MagicMock()

    assert archiver_instance.prune_allowed is True
    result = archiver_instance.clean_up()

    assert result == stale
    archiver_instance._delete_files.assert_called_once_with(stale)


def test_prune_allowed_true_on_clean_run(archiver_instance, mock_config):
    """No failed nodes/assets -> pruning is allowed regardless of prune_on_partial."""
    archiver_instance._archiver.failed_node_exports = []
    archiver_instance._archiver.failed_asset_downloads = []

    assert archiver_instance.prune_allowed is True


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


class TestFailedContentProperties:
    def test_properties_delegate_to_node_archiver(self, mock_config, mock_http_client):
        node_archiver = MagicMock()
        node_archiver.failed_node_exports = ["my-book/secret.md"]
        node_archiver.failed_asset_downloads = ["images/gallery/broken.png"]
        archiver = Archiver(mock_config, mock_http_client, node_archiver=node_archiver)
        assert archiver.failed_nodes == ["my-book/secret.md"]
        assert archiver.failed_assets == ["images/gallery/broken.png"]
