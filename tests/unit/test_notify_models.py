# pylint: disable=missing-function-docstring,use-implicit-booleaness-not-comparison
"""Unit tests for ExportStatus / UploadOutcome / NotifyResult."""
from bookstack_file_exporter.notify.models import (
    ExportStatus, UploadOutcome, NotifyResult,
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
