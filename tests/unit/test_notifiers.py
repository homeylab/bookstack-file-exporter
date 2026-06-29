# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name
# pylint: disable=protected-access
"""Unit tests for AppRiseNotify._get_message_text success-branch formatting."""
import os
from unittest.mock import MagicMock

from bookstack_file_exporter.notify import notifiers
from bookstack_file_exporter.notify.models import ExportStatus, NotifyResult, UploadOutcome
from bookstack_file_exporter.notify.notifiers import AppRiseNotify


def _make_notifier():
    """Build AppRiseNotify bypassing Apprise client init."""
    instance = AppRiseNotify.__new__(AppRiseNotify)
    config = MagicMock()
    config.custom_title = None
    config.storage_path = None
    config.plugin_paths = None
    config.config_path = None
    config.service_urls = []
    config.custom_attachment = None
    instance.config = config
    instance._client = MagicMock()
    return instance


class TestGetMessageTextSuccessBranch:
    def test_none_result_produces_generic_success_body(self):
        notifier = _make_notifier()
        body = notifier._get_message_text(None, result=None)
        assert "completed successfully" in body
        assert "Archive:" not in body
        assert "Uploaded to:" not in body
        assert "Pruned" not in body

    def test_result_local_none_produces_generic_success_body(self):
        notifier = _make_notifier()
        result = NotifyResult(local=None, uploads=[], removed=[])
        body = notifier._get_message_text(None, result=result)
        assert "completed successfully" in body
        assert "Archive:" not in body

    def test_local_only_shows_archive_line_no_suffix_no_remote_no_pruned(self):
        notifier = _make_notifier()
        result = NotifyResult(local="/data/export.tgz", uploads=[], removed=[])
        body = notifier._get_message_text(None, result=result)
        assert "Archive: /data/export.tgz" in body
        assert "(removed locally after upload)" not in body
        assert "Uploaded to:" not in body
        assert "Pruned" not in body

    def test_local_in_removed_shows_suffix(self):
        notifier = _make_notifier()
        local = "/data/export.tgz"
        result = NotifyResult(local=local, uploads=[], removed=[local])
        body = notifier._get_message_text(None, result=result)
        assert "Archive: /data/export.tgz (removed locally after upload)" in body

    def test_remote_nonempty_shows_uploaded_to_line(self):
        notifier = _make_notifier()
        result = NotifyResult(
            local="/data/export.tgz",
            uploads=[UploadOutcome("t1", "bucket1/backups/export.tgz"),
                     UploadOutcome("t2", "bucket2/export.tgz")],
            removed=[],
        )
        body = notifier._get_message_text(None, result=result)
        assert "Uploaded to: bucket1/backups/export.tgz, bucket2/export.tgz" in body

    def test_removed_has_old_files_shows_pruned_count(self):
        notifier = _make_notifier()
        local = "/data/new.tgz"
        removed = ["/data/old1.tgz", "/data/old2.tgz", local]
        result = NotifyResult(local=local, uploads=[], removed=removed)
        body = notifier._get_message_text(None, result=result)
        # local is in removed (suffix present) + 2 old archives pruned
        assert "(removed locally after upload)" in body
        assert "Pruned 2 old local archive(s)" in body

    def test_old_files_only_no_local_in_removed(self):
        notifier = _make_notifier()
        local = "/data/new.tgz"
        removed = ["/data/old1.tgz", "/data/old2.tgz"]
        result = NotifyResult(local=local, uploads=[], removed=removed)
        body = notifier._get_message_text(None, result=result)
        assert "(removed locally after upload)" not in body
        assert "Pruned 2 old local archive(s)" in body

    def test_abspath_normalization_relative_vs_absolute(self):
        """Relative and absolute path forms of the same file are treated as the same."""
        notifier = _make_notifier()
        # Use a known absolute path and a relative form that resolves to the same place
        cwd = os.getcwd()
        local_abs = os.path.join(cwd, "export.tgz")
        local_rel = "export.tgz"
        # Pass abs as local, relative form in removed — should still match
        result = NotifyResult(local=local_abs, uploads=[], removed=[local_rel])
        body = notifier._get_message_text(None, result=result)
        assert "(removed locally after upload)" in body

    def test_abspath_normalization_relative_local_absolute_removed(self):
        """Reverse form: relative local vs absolute removed entry still match (suffix)."""
        notifier = _make_notifier()
        local_rel = "export.tgz"
        removed_abs = os.path.join(os.getcwd(), "export.tgz")
        result = NotifyResult(local=local_rel, uploads=[], removed=[removed_abs])
        body = notifier._get_message_text(None, result=result)
        assert "(removed locally after upload)" in body

    def test_pruned_count_excludes_current_under_mixed_path_forms(self):
        """The current archive must not inflate the prune count even when its path
        form differs between local and the removed list (abspath-normalized)."""
        notifier = _make_notifier()
        local_rel = "new.tgz"
        removed = [os.path.join(os.getcwd(), "new.tgz"), "/data/old1.tgz", "/data/old2.tgz"]
        result = NotifyResult(local=local_rel, uploads=[], removed=removed)
        body = notifier._get_message_text(None, result=result)
        # current archive (mixed form) → suffix, NOT counted among pruned old archives
        assert "(removed locally after upload)" in body
        assert "Pruned 2 old local archive(s)" in body

    def test_failure_branch_unchanged_no_archive_lines(self):
        notifier = _make_notifier()
        err = ValueError("something broke")
        result = NotifyResult(
            local="/data/export.tgz", uploads=[UploadOutcome("t", "bucket/x")], removed=[]
        )
        body = notifier._get_message_text(err, result=result)
        assert "unrecoverable error" in body
        assert "something broke" in body
        assert "Archive:" not in body
        assert "Uploaded to:" not in body
        assert "Pruned" not in body


# ---------------------------------------------------------------------------
# New tests for 3-state title and partial body rendering (Task 3)
# ---------------------------------------------------------------------------

def _notifier():
    inst = notifiers.AppRiseNotify.__new__(notifiers.AppRiseNotify)
    inst.config = MagicMock(custom_title=None)
    return inst


def test_title_partial():
    inst = _notifier()
    result = NotifyResult(status=ExportStatus.PARTIAL, local="/a/b.tgz")
    assert inst._get_title(None, result).endswith("Partial")


def test_title_success():
    inst = _notifier()
    result = NotifyResult(status=ExportStatus.SUCCESS, local="/a/b.tgz")
    assert inst._get_title(None, result).endswith("Success")


def test_title_failed_on_exception():
    assert _notifier()._get_title(ValueError("x"), None).endswith("Failed")


def test_body_lists_ok_and_failed_targets():
    inst = _notifier()
    result = NotifyResult(
        status=ExportStatus.PARTIAL, local="/a/b.tgz",
        uploads=[UploadOutcome("minio/b", "minio-b/a.tgz", None),
                 UploadOutcome("s3/dr", None, "connection refused")])
    body = inst._get_message_text(None, result)
    assert "Uploaded to: minio-b/a.tgz" in body      # ok target -> dest
    assert "Failed: s3/dr - connection refused" in body  # failed target -> label + error


def test_body_lists_retention_warning():
    inst = _notifier()
    result = NotifyResult(
        status=ExportStatus.PARTIAL, local="/a/b.tgz",
        uploads=[UploadOutcome("s3/aws", "s3-aws/a.tgz", None, "delete denied")])
    body = inst._get_message_text(None, result)
    assert "Uploaded to: s3-aws/a.tgz" in body
    assert "Warning: s3/aws - delete denied" in body
