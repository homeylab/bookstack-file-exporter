# pylint: disable=missing-function-docstring,use-implicit-booleaness-not-comparison
"""Unit tests for ExportStatus / UploadOutcome / NotifyResult."""
from bookstack_file_exporter.notify.models import (
    ExportStatus, UploadOutcome, NotifyResult, STATUS_EFFECTS, format_run_summary,
)


def test_export_status_members():
    assert ExportStatus.SUCCESS != ExportStatus.PARTIAL


def test_upload_outcome_success_and_failure():
    ok = UploadOutcome(label="minio/b", dest="b/x.tgz", error=None)
    bad = UploadOutcome(label="s3/dr", dest=None, error="boom")
    assert ok.dest == "b/x.tgz" and ok.error is None
    assert bad.dest is None and bad.error == "boom"


def test_notify_result_defaults():
    r = NotifyResult(status=ExportStatus.SUCCESS, local="/a/b.tgz")
    assert r.status is ExportStatus.SUCCESS
    assert r.local == "/a/b.tgz"
    assert r.uploads == []
    assert r.removed == []


def test_notify_result_carries_uploads():
    out = [UploadOutcome("minio/b", "b/x.tgz", None)]
    r = NotifyResult(status=ExportStatus.PARTIAL, local="/a/b.tgz", uploads=out)
    assert r.uploads[0].label == "minio/b"


def test_upload_outcome_warning_defaults_none_and_settable():
    assert UploadOutcome(label="x").warning is None
    assert UploadOutcome(label="x", dest="d", warning="w").warning == "w"


class TestStatusEffects:
    """One table drives exit code, health mark, and notification title."""

    def test_success_effects(self):
        effects = STATUS_EFFECTS[ExportStatus.SUCCESS]
        assert effects.exit_code == 0
        assert effects.health_degraded is False
        assert effects.title_suffix == "Success"

    def test_partial_effects(self):
        effects = STATUS_EFFECTS[ExportStatus.PARTIAL]
        assert effects.exit_code == 3
        assert effects.health_degraded is True
        assert effects.title_suffix == "Partial"

    def test_empty_effects(self):
        effects = STATUS_EFFECTS[ExportStatus.EMPTY]
        assert effects.exit_code == 0
        assert effects.health_degraded is False
        assert effects.title_suffix == "Success"

    def test_every_status_has_effects(self):
        """Adding an ExportStatus without an effects row must fail loudly here,
        not KeyError at exit time."""
        for status in ExportStatus:
            assert status in STATUS_EFFECTS

    def test_notify_result_failed_content_defaults_empty(self):
        result = NotifyResult()
        assert result.failed_nodes == []
        assert result.failed_assets == []
        assert result.export_level == "pages"


class TestFormatRunSummary:
    """format_run_summary() -- one-line plaintext outcome roll-up for logs."""

    def test_summary_partial_mixed(self):
        r = NotifyResult(status=ExportStatus.PARTIAL, local="/data/bkps.tgz",
                         export_level="pages",
                         uploads=[UploadOutcome("minio/b", "minio-b/a.tgz"),
                                  UploadOutcome("s3/dr", None, "boom")],
                         failed_nodes=["p1", "p2"], failed_assets=["img1"],
                         removed=["old.tgz"])
        assert format_run_summary(r) == ("level=pages archive=/data/bkps.tgz uploads_ok=1/2 "
                                         "(failed: s3/dr) pages_failed=2 assets_failed=1 removed=1")

    def test_summary_success_pruned(self):
        r = NotifyResult(status=ExportStatus.SUCCESS, local="/data/bkps.tgz",
                         export_level="books",
                         uploads=[UploadOutcome("minio/b", "minio-b/a.tgz", pruned=3)])
        assert format_run_summary(r) == "level=books archive=/data/bkps.tgz uploads_ok=1/1 pruned=3"

    def test_summary_content_loss_uses_plural_level_key(self):
        # failed-document count is keyed by the (already plural) export_level,
        # matching the key=value shape of the rest of the line.
        r = NotifyResult(status=ExportStatus.PARTIAL, export_level="books",
                         failed_nodes=["shelf/infra.pdf"], failed_assets=["img1", "img2"])
        assert "books_failed=1 assets_failed=2" in format_run_summary(r)

    def test_summary_content_loss_reports_both_keys_when_only_assets_fail(self):
        # assets-only loss still shows the zero document count, so the two
        # failure axes are always both visible.
        r = NotifyResult(status=ExportStatus.PARTIAL, export_level="pages",
                         failed_assets=["img1"])
        assert "pages_failed=0 assets_failed=1" in format_run_summary(r)

    def test_summary_empty(self):
        r = NotifyResult(status=ExportStatus.EMPTY, export_level="pages")
        assert format_run_summary(r) == "level=pages"

    def test_summary_retention_warned(self):
        r = NotifyResult(status=ExportStatus.PARTIAL, local="/data/bkps.tgz",
                         export_level="pages",
                         uploads=[UploadOutcome("minio/b", "minio-b/a.tgz",
                                                warning="cleanup slow")])
        assert format_run_summary(r) == ("level=pages archive=/data/bkps.tgz uploads_ok=1/1 "
                                         "(retention-warned: minio/b)")

    def test_summary_flattens_newline_in_cleanup_error(self):
        # cleanup_error is a str(exception); a line break must not split the
        # one-line summary operators grep for.
        r = NotifyResult(status=ExportStatus.PARTIAL, export_level="pages",
                         cleanup_error="permission denied\n/data/old.tgz")
        summary = format_run_summary(r)
        assert "\n" not in summary
        assert summary == "level=pages cleanup_error=permission denied /data/old.tgz"
