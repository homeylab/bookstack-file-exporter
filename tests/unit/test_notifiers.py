# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name
# pylint: disable=protected-access
"""Unit tests for AppRiseNotify._get_message_text success-branch formatting."""
import os
import re
from unittest.mock import MagicMock, patch

from apprise import AppriseConfig, NotifyFormat

from bookstack_file_exporter.config_helper import models as config_models
from bookstack_file_exporter.config_helper import notifications
from bookstack_file_exporter.notify import notifiers
from bookstack_file_exporter.notify.models import ExportStatus, NotifyResult, UploadOutcome
from bookstack_file_exporter.notify.notifiers import AppRiseNotify


def _make_notifier(body_format="text"):
    """Build AppRiseNotify bypassing Apprise client init."""
    instance = AppRiseNotify.__new__(AppRiseNotify)
    config = MagicMock()
    config.custom_title = None
    config.storage_path = None
    config.plugin_paths = None
    config.config_path = None
    config.service_urls = []
    config.custom_attachment = None
    config.body_format = body_format
    instance.config = config
    instance._client = MagicMock()
    return instance


def _apprise_notify_config(**overrides):
    """Build a real notifications.ResolvedAppriseConfig via the pydantic model,
    so _create_client() runs against production config wiring."""
    base = {"service_urls": ["json://localhost"]}
    base.update(overrides)
    return notifications.ResolvedAppriseConfig(config_models.AppRiseNotifyConfig(**base))


class TestCreateClientAssetWiring:
    """B1 regression: AppriseAsset fields are constructor-only / read-only
    properties on apprise>=1.10.0, and Apprise.add() bakes the asset into
    plugin instances at add-time, so the asset must be built with kwargs and
    passed to Apprise(asset=...) up front (never assigned after add())."""

    def test_storage_path_and_plugin_paths_none_no_exception(self):
        config = _apprise_notify_config()
        notifier = AppRiseNotify(config)
        assert notifier._client.asset.storage_path is None
        assert not notifier._client.asset.plugin_paths

    def test_storage_path_propagates_to_client_asset(self, tmp_path):
        config = _apprise_notify_config(storage_path=str(tmp_path))
        notifier = AppRiseNotify(config)
        assert notifier._client.asset.storage_path == str(tmp_path)
        # plugin-level assert: notify() uses the asset baked into each plugin
        # at add()-time, not the client-level attribute
        assert notifier._client[0].asset.storage_path == str(tmp_path)

    def test_plugin_paths_propagates_to_client_asset(self, tmp_path):
        plugin_dir = str(tmp_path)
        config = _apprise_notify_config(plugin_paths=[plugin_dir])
        notifier = AppRiseNotify(config)
        assert notifier._client.asset.plugin_paths == [plugin_dir]
        assert notifier._client[0].asset.plugin_paths == [plugin_dir]

    def test_config_path_branch_constructs_appriseconfig_with_asset(self, tmp_path):
        # AppriseConfig carries its own default AppriseAsset -- the asset built
        # above (storage_path/plugin_paths) must be threaded into it explicitly,
        # or config-file-loaded plugins silently get apprise's stock asset.
        config = _apprise_notify_config(
            config_path=str(tmp_path / "missing.yml"), storage_path=str(tmp_path))
        with patch("bookstack_file_exporter.notify.notifiers.AppriseConfig",
                   wraps=AppriseConfig) as spy:
            AppRiseNotify(config)
        assert spy.call_args.kwargs["asset"].storage_path == str(tmp_path)


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
        assert ("\n\nUploaded to:\n- t1: bucket1/backups/export.tgz\n"
                "- t2: bucket2/export.tgz" in body)

    def test_removed_has_old_files_shows_pruned_count(self):
        notifier = _make_notifier()
        local = "/data/new.tgz"
        removed = ["/data/old1.tgz", "/data/old2.tgz", local]
        result = NotifyResult(local=local, uploads=[], removed=removed)
        body = notifier._get_message_text(None, result=result)
        # local is in removed (suffix present) + 2 old archives pruned
        assert "(removed locally after upload)" in body
        assert "\n\nPruned:\n- local: 2 archive(s)" in body

    def test_old_files_only_no_local_in_removed(self):
        notifier = _make_notifier()
        local = "/data/new.tgz"
        removed = ["/data/old1.tgz", "/data/old2.tgz"]
        result = NotifyResult(local=local, uploads=[], removed=removed)
        body = notifier._get_message_text(None, result=result)
        assert "(removed locally after upload)" not in body
        assert "Pruned:\n- local: 2 archive(s)" in body

    def test_cleanup_error_shows_warning_line(self):
        notifier = _make_notifier()
        result = NotifyResult(status=ExportStatus.PARTIAL, local="/data/export.tgz",
                              uploads=[], removed=[], cleanup_error="permission denied")
        body = notifier._get_message_text(None, result=result)
        assert "Warnings:\n- local cleanup failed: permission denied" in body
        assert "completed with errors" in body

    def test_no_cleanup_error_no_warning_line(self):
        notifier = _make_notifier()
        result = NotifyResult(local="/data/export.tgz", uploads=[], removed=[])
        body = notifier._get_message_text(None, result=result)
        assert "local cleanup failed" not in body

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
        assert "Pruned:\n- local: 2 archive(s)" in body

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
    assert "Uploaded to:\n- minio/b: minio-b/a.tgz" in body  # ok target -> labeled bullet
    assert "Failed:\n- s3/dr: connection refused" in body  # failed target -> bullet under header


def test_body_lists_retention_warning():
    inst = _notifier()
    result = NotifyResult(
        status=ExportStatus.PARTIAL, local="/a/b.tgz",
        uploads=[UploadOutcome("s3/aws", "s3-aws/a.tgz", None, "delete denied")])
    body = inst._get_message_text(None, result)
    assert "Uploaded to:\n- s3/aws: s3-aws/a.tgz" in body
    assert "Warnings:\n- s3/aws: delete denied" in body


def test_body_groups_failures_and_warnings_as_bullet_lists():
    """All failure bullets sit under one Failed: header; per-target retention
    warnings and the local cleanup error share one Warnings: header."""
    inst = _notifier()
    result = NotifyResult(
        status=ExportStatus.PARTIAL, local="/a/b.tgz",
        uploads=[UploadOutcome("minio/b", None, "connection refused"),
                 UploadOutcome("s3/dr", None, "Forbidden"),
                 UploadOutcome("s3/aws", "s3-aws/a.tgz", None, "delete denied")],
        cleanup_error="permission denied")
    body = inst._get_message_text(None, result)
    assert "Failed:\n- minio/b: connection refused\n- s3/dr: Forbidden" in body
    assert ("Warnings:\n- s3/aws: delete denied\n"
            "- local cleanup failed: permission denied") in body
    assert body.count("Failed:") == 1
    assert body.count("Warnings:") == 1


def test_body_pruned_group_lists_local_and_remote_targets():
    """Local prune count and per-target remote retention counts share one
    Pruned: group, local bullet first, zero-count targets omitted."""
    inst = _notifier()
    result = NotifyResult(
        local="/a/b.tgz",
        uploads=[UploadOutcome("minio/b", "minio-b/a.tgz", pruned=2),
                 UploadOutcome("s3/aws", "s3-aws/a.tgz", pruned=0)],
        removed=["/a/old.tgz"])
    body = inst._get_message_text(None, result)
    assert "\n\nPruned:\n- local: 1 archive(s)\n- minio/b: 2 archive(s)" in body
    assert "s3/aws: 0" not in body


def test_body_pruned_group_remote_only():
    inst = _notifier()
    result = NotifyResult(
        local="/a/b.tgz",
        uploads=[UploadOutcome("s3/aws", "s3-aws/a.tgz", pruned=4)],
        removed=[])
    body = inst._get_message_text(None, result)
    assert "\n\nPruned:\n- s3/aws: 4 archive(s)" in body
    assert "- local:" not in body


def test_body_separates_groups_with_blank_line():
    """A blank line precedes each group header so sections don't run together."""
    inst = _notifier()
    result = NotifyResult(
        status=ExportStatus.PARTIAL, local="/a/b.tgz",
        uploads=[UploadOutcome("s3/dr", None, "Forbidden")],
        cleanup_error="permission denied")
    body = inst._get_message_text(None, result)
    assert "\n\nFailed:\n- s3/dr: Forbidden" in body
    assert "\n\nWarnings:\n- local cleanup failed: permission denied" in body


class TestMdCode:
    def test_plain_string_single_backticks(self):
        assert notifiers._md_code("connection refused") == "`connection refused`"

    def test_string_with_backtick_uses_double_delimiters_and_padding(self):
        # double-backtick delimiters + space padding per CommonMark so an inner
        # backtick cannot terminate the span
        assert notifiers._md_code("a `tick` inside") == "`` a `tick` inside ``"

    def test_angle_brackets_survive_inside_span(self):
        # the whole point: code spans neutralize raw HTML for MARKDOWN->HTML targets
        out = notifiers._md_code("Forbidden <edge & chars>")
        assert out == "`Forbidden <edge & chars>`"


class TestMarkdownBody:
    def _partial_result(self):
        return NotifyResult(
            status=ExportStatus.PARTIAL, local="/data/export.tgz",
            uploads=[UploadOutcome("minio/b", "minio-b/a.tgz", None),
                     UploadOutcome("s3/dr", None, "Forbidden <edge>")],
            removed=[], cleanup_error="permission denied")

    def test_markdown_body_structure(self):
        notifier = _make_notifier(body_format="markdown")
        body = notifier._get_message_text(None, result=self._partial_result())
        assert "**Bookstack File Exporter completed with errors.**" in body
        assert "Archive: `/data/export.tgz`" in body
        assert "**Uploaded to:**\n\n- `minio/b`: `minio-b/a.tgz`" in body
        # blank line between header and bullets => real <ul> after conversion
        assert "**Failed:**\n\n- `s3/dr`: `Forbidden <edge>`" in body
        assert "**Warnings:**\n\n- local cleanup failed: `permission denied`" in body

    def test_markdown_group_headers_separated_from_preceding_lines(self):
        """A blank line must precede each group header too: CommonMark lazy
        continuation otherwise absorbs **Warnings:** into the last Failed bullet
        (one merged <ul> after apprise's MARKDOWN->HTML conversion)."""
        notifier = _make_notifier(body_format="markdown")
        body = notifier._get_message_text(None, result=self._partial_result())
        assert "\n\n**Failed:**\n\n" in body
        assert "\n\n**Warnings:**\n\n" in body

    def test_markdown_error_strings_are_code_wrapped(self):
        notifier = _make_notifier(body_format="markdown")
        body = notifier._get_message_text(None, result=self._partial_result())
        assert "`Forbidden <edge>`" in body          # wrapped
        assert ": Forbidden <edge>" not in body      # never raw

    def test_markdown_pruned_group_wraps_target_labels(self):
        notifier = _make_notifier(body_format="markdown")
        result = NotifyResult(
            local="/a/b.tgz",
            uploads=[UploadOutcome("s3/aws", "s3-aws/a.tgz", pruned=2)],
            removed=["/a/old.tgz"])
        body = notifier._get_message_text(None, result=result)
        assert "\n\n**Pruned:**\n\n- local: 1 archive(s)\n- `s3/aws`: 2 archive(s)" in body

    def test_markdown_unrecoverable_error_bolded_and_code_wrapped(self):
        notifier = _make_notifier(body_format="markdown")
        body = notifier._get_message_text(RuntimeError("boom <tag> & `tick`"))
        assert "**Bookstack File Exporter encountered an unrecoverable error.**" in body
        assert "Error message: `` boom <tag> & `tick` ``" in body

    def test_markdown_warning_pruned_and_removed_suffix(self):
        result = NotifyResult(
            status=ExportStatus.PARTIAL, local="/data/export.tgz",
            uploads=[UploadOutcome("s3/main", "b/a.tgz", warning="retention failed <x>")],
            removed=["/data/export.tgz", "/data/old.tgz"])
        notifier = _make_notifier(body_format="markdown")
        body = notifier._get_message_text(None, result=result)
        assert "Archive: `/data/export.tgz` (removed locally after upload)" in body
        # blank line after the upload bullets: a plain line straight after a list
        # would be lazily absorbed into the last bullet in MARKDOWN->HTML
        assert "- `s3/main`: `b/a.tgz`\n\n**Pruned:**\n\n- local: 1 archive(s)" in body
        assert "**Warnings:**\n\n- `s3/main`: `retention failed <x>`" in body

    def test_text_mode_output_unchanged(self):
        """Default mode must render the exact current text body."""
        notifier = _make_notifier()  # body_format defaults to text
        body = notifier._get_message_text(None, result=self._partial_result())
        assert "Failed:\n- s3/dr: Forbidden <edge>" in body
        assert "**" not in body and "`" not in body


class TestNotifyBodyFormat:
    def test_notify_declares_text_body_format_by_default(self):
        notifier = _make_notifier()
        notifier.notify(result=NotifyResult(local=None, uploads=[], removed=[]))
        kwargs = notifier._client.notify.call_args.kwargs
        assert kwargs["body_format"] == NotifyFormat.TEXT

    def test_notify_declares_markdown_body_format_when_opted_in(self):
        notifier = _make_notifier(body_format="markdown")
        notifier.notify(result=NotifyResult(local=None, uploads=[], removed=[]))
        kwargs = notifier._client.notify.call_args.kwargs
        assert kwargs["body_format"] == NotifyFormat.MARKDOWN

    def test_notify_declares_body_format_with_attachment(self):
        notifier = _make_notifier(body_format="markdown")
        notifier.config.custom_attachment = "/tmp/export.tgz"
        notifier.notify(result=NotifyResult(local=None, uploads=[], removed=[]))
        kwargs = notifier._client.notify.call_args.kwargs
        assert kwargs["body_format"] == NotifyFormat.MARKDOWN


class TestEmptyStatusBody:
    """EMPTY (nothing to archive) renders an archive-less body in both formats."""

    def test_text_body_says_nothing_to_archive_no_sections(self):
        notifier = _make_notifier()
        result = NotifyResult(status=ExportStatus.EMPTY, export_level="pages")
        body = notifier._text_body(None, result)
        assert "nothing to archive" in body
        assert "Completed At:" in body
        assert re.search(r"Completed At: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC", body)
        assert "No pages content was found to export." in body
        assert "Archive:" not in body
        assert "Uploaded to:" not in body
        assert "Pruned" not in body
        assert "Failed:" not in body

    def test_text_body_names_the_export_level(self):
        notifier = _make_notifier()
        result = NotifyResult(status=ExportStatus.EMPTY, export_level="books")
        body = notifier._text_body(None, result)
        assert "No books content was found to export." in body

    def test_markdown_body_says_nothing_to_archive_no_sections(self):
        notifier = _make_notifier(body_format="markdown")
        result = NotifyResult(status=ExportStatus.EMPTY, export_level="pages")
        body = notifier._markdown_body(None, result)
        assert "**Bookstack File Exporter completed - nothing to archive.**" in body
        assert "Completed At:" in body
        assert re.search(r"Completed At: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC", body)
        assert "No pages content was found to export." in body
        assert "Archive:" not in body
        assert "Uploaded to:" not in body
        assert "Pruned" not in body
        assert "Failed:" not in body

    def test_get_message_text_dispatches_empty_to_markdown(self):
        notifier = _make_notifier(body_format="markdown")
        result = NotifyResult(status=ExportStatus.EMPTY, export_level="pages")
        body = notifier._get_message_text(None, result)
        assert "**Bookstack File Exporter completed - nothing to archive.**" in body

    def test_title_stays_success_for_empty(self):
        inst = _notifier()
        result = NotifyResult(status=ExportStatus.EMPTY, export_level="pages")
        assert inst._get_title(None, result).endswith("Success")


class TestContentFailureBullets:
    """Content-loss ledger renders as count-only Failed: bullets."""

    def test_text_body_counts_failed_nodes_and_assets(self):
        notifier = _make_notifier()
        result = NotifyResult(status=ExportStatus.PARTIAL, local="/bkps/export.tgz",
                              failed_nodes=["my-book/secret.md"],
                              failed_assets=["images/gallery/a.png",
                                             "images/gallery/b.png"],
                              export_level="pages")
        body = notifier._text_body(None, result)
        assert "Failed:" in body
        assert "- content: 1 page export(s) failed" in body
        assert "- assets: 2 asset download(s) failed" in body
        assert "completed with errors" in body
        # counts only: paths stay in logs, never in the notification body
        assert "my-book/secret.md" not in body
        assert "images/gallery/a.png" not in body

    def test_content_bullet_names_the_export_level(self):
        notifier = _make_notifier()
        result = NotifyResult(status=ExportStatus.PARTIAL, local="/bkps/export.tgz",
                              failed_nodes=["shelf/infra.pdf"],
                              export_level="books")
        body = notifier._text_body(None, result)
        assert "- content: 1 book export(s) failed" in body

    def test_unknown_export_level_falls_back_to_node(self):
        notifier = _make_notifier()
        result = NotifyResult(status=ExportStatus.PARTIAL, local="/bkps/export.tgz",
                              failed_nodes=["x.md"], export_level="weird")
        body = notifier._text_body(None, result)
        assert "- content: 1 node export(s) failed" in body

    def test_no_bullets_when_ledger_empty(self):
        notifier = _make_notifier()
        result = NotifyResult(status=ExportStatus.SUCCESS, local="/bkps/export.tgz")
        body = notifier._text_body(None, result)
        assert "export(s) failed" not in body
        assert "download(s) failed" not in body

    def test_markdown_body_same_bullets(self):
        notifier = _make_notifier()
        result = NotifyResult(status=ExportStatus.PARTIAL, local="/bkps/export.tgz",
                              failed_nodes=["my-book/secret.md"],
                              failed_assets=["images/gallery/a.png"],
                              export_level="pages")
        body = notifier._markdown_body(None, result)
        assert "**Failed:**" in body
        assert "- content: 1 page export(s) failed" in body
        assert "- assets: 1 asset download(s) failed" in body

    def test_partial_without_archive_renders(self):
        """Total content loss: local=None, ledger populated -- body must still
        carry the error headline and the Failed: group."""
        notifier = _make_notifier()
        result = NotifyResult(status=ExportStatus.PARTIAL, local=None,
                              failed_nodes=["my-book/secret.md"],
                              export_level="pages")
        body = notifier._text_body(None, result)
        assert "completed with errors" in body
        assert "- content: 1 page export(s) failed" in body
        md_body = notifier._markdown_body(None, result)
        assert "**Failed:**" in md_body
