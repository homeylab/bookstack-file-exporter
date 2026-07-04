import os
from datetime import datetime, timezone
from apprise import Apprise, AppriseAsset, AppriseConfig, NotifyFormat

from bookstack_file_exporter.config_helper import notifications
from bookstack_file_exporter.notify.models import NotifyResult, ExportStatus, STATUS_EFFECTS

_DEFAULT_TITLE_PREFIX = "Bookstack File Exporter "

def _md_code(text: str) -> str:
    """Wrap untrusted interpolated text in a markdown code span.

    Code spans are the sanitizer for the markdown body: python-markdown escapes
    <>& inside them, so error strings containing raw HTML cannot be swallowed by
    HTML-native targets (apprise's MARKDOWN->HTML conversion does NOT escape,
    verified against apprise 1.10.0). Double-backtick delimiters with space
    padding tolerate single backticks inside the text (CommonMark)."""
    if "`" in text:
        return f"`` {text} ``"
    return f"`{text}`"

def _pruned_bullets(result: NotifyResult, local_abs: str, removed_abs: set[str],
                    wrap_labels: bool = False) -> list[str]:
    """Bullets for the Pruned: group, shared by both renderers: local retention
    count first, then one bullet per remote target that deleted objects
    (zero-count targets omitted). wrap_labels=True runs the untrusted target
    labels through _md_code (markdown mode)."""
    pruned_local = len(removed_abs - {local_abs})
    bullets = [f"- local: {pruned_local} archive(s)"] if pruned_local > 0 else []
    for outcome in result.uploads:
        if outcome.pruned > 0:
            label = _md_code(outcome.label) if wrap_labels else outcome.label
            bullets.append(f"- {label}: {outcome.pruned} archive(s)")
    return bullets

# export_level -> singular noun for the content-failure bullet. Explicit map
# (not level[:-1]) so an unexpected value degrades to a readable fallback.
_LEVEL_SINGULAR = {"pages": "page", "books": "book", "chapters": "chapter"}


def _content_failure_bullets(result: NotifyResult | None) -> list[str]:
    """Count-only bullets for content dropped from the archive, shared by both
    renderers. These seed the Failed: group FIRST: missing content outranks a
    failed upload. Counts only -- the per-path detail is already in the run logs
    and in the NotifyResult fields; nothing untrusted is interpolated here, so
    the markdown renderer needs no _md_code wrapping."""
    if result is None:
        return []
    bullets = []
    if result.failed_nodes:
        label = _LEVEL_SINGULAR.get(result.export_level, "node")
        bullets.append(
            f"- content: {len(result.failed_nodes)} {label} export(s) failed")
    if result.failed_assets:
        bullets.append(
            f"- assets: {len(result.failed_assets)} asset download(s) failed")
    return bullets

# pylint: disable=too-few-public-methods
class AppRiseNotify:
    """
    AppRiseNotify helps send notifications via apprise for failed export runs

    Args:
        :config: <notifications.ResolvedAppriseConfig> = Configuration with user inputs and
                                                       general options

    Returns:
        AppRiseNotify instance to help handle apprise notification integration.
    """
    def __init__(self, config: notifications.ResolvedAppriseConfig):
        self.config = config
        self._client = self._create_client()

    def _create_client(self):
        # apprise >=1.10.0: AppriseAsset fields are read-only properties,
        # settable only via constructor kwargs; and Apprise.add() bakes the
        # asset into each plugin at add-time, so the asset must be passed at
        # Apprise(asset=...) construction -- never assigned after add().
        asset_kwargs = {}
        if self.config.storage_path:
            asset_kwargs["storage_path"] = self.config.storage_path
        if self.config.plugin_paths:
            asset_kwargs["plugin_paths"] = self.config.plugin_paths
        asset = AppriseAsset(**asset_kwargs)

        client = Apprise(asset=asset)

        if self.config.config_path:
            # same asset must be threaded into AppriseConfig too -- otherwise
            # config-file-loaded plugins get AppriseConfig's own default asset
            # instead of the storage_path/plugin_paths built above.
            app_config = AppriseConfig(asset=asset)
            app_config.add(self.config.config_path)
            client.add(app_config)
        else:
            client.add(self.config.service_urls)

        return client

    def _get_title(self, excep: None | Exception,
                   result: NotifyResult | None = None) -> str:
        if self.config.custom_title:
            return self.config.custom_title
        if excep:
            # hard failure is a raised exception, never an ExportStatus value,
            # so it sits outside the STATUS_EFFECTS table by design
            return _DEFAULT_TITLE_PREFIX + "Failed"
        if result is not None:
            return _DEFAULT_TITLE_PREFIX + STATUS_EFFECTS[result.status].title_suffix
        return _DEFAULT_TITLE_PREFIX + "Success"

    def _get_message_text(self, error_msg: None | Exception,
                          result: NotifyResult | None = None) -> str:
        if self.config.body_format == "markdown":
            return self._markdown_body(error_msg, result)
        return self._text_body(error_msg, result)

    def _text_body(self, error_msg: None | Exception,
                   result: NotifyResult | None = None) -> str:
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        if error_msg:
            return "\n".join([
                "",
                "Bookstack File Exporter encountered an unrecoverable error.",
                "",
                f"Occurred At: {timestamp}",
                "",
                f"Error message: {str(error_msg)}",
            ])
        if result is not None and result.status is ExportStatus.EMPTY:
            # Archive-less run: no Archive/Uploaded/Pruned/Failed sections make
            # sense when nothing was ever written.
            return "\n".join([
                "",
                "Bookstack File Exporter completed - nothing to archive.",
                "",
                f"Completed At: {timestamp}",
                "",
                f"No {result.export_level} content was found to export.",
            ])
        partial = result is not None and result.status is ExportStatus.PARTIAL
        headline = ("Bookstack File Exporter completed with errors."
                    if partial else
                    "Bookstack File Exporter completed successfully.")
        lines = ["", headline, "", f"Completed At: {timestamp}"]
        # Grouped trailers: every failed upload becomes a bullet under one "Failed:"
        # header; per-target retention warnings and a local cleanup failure share one
        # "Warnings:" header (one visual language for "non-fatal"). Plain "- " bullets
        # render sensibly in both text and markdown notification targets.
        failed: list[str] = _content_failure_bullets(result)
        warnings: list[str] = []
        if result is not None and result.local is not None:
            local_abs = os.path.abspath(result.local)
            removed_abs = {os.path.abspath(p) for p in result.removed}
            archive_line = f"Archive: {result.local}"
            if local_abs in removed_abs:
                archive_line += " (removed locally after upload)"
            lines.append(archive_line)
            # Successful targets get labeled bullets under one "Uploaded to:" header,
            # the same visual language as the Failed:/Warnings: groups below.
            ok_uploads = [o for o in result.uploads if o.dest]
            if ok_uploads:
                lines.extend(["", "Uploaded to:"])
                lines.extend(f"- {o.label}: {o.dest}" for o in ok_uploads)
            for outcome in result.uploads:
                if not outcome.dest:
                    failed.append(f"- {outcome.label}: {outcome.error}")
                elif outcome.warning:
                    warnings.append(f"- {outcome.label}: {outcome.warning}")
            pruned = _pruned_bullets(result, local_abs, removed_abs)
            if pruned:
                lines.extend(["", "Pruned:"])
                lines.extend(pruned)
        if result is not None and result.cleanup_error:
            warnings.append(f"- local cleanup failed: {result.cleanup_error}")
        if failed:
            lines.extend(["", "Failed:"])
            lines.extend(failed)
        if warnings:
            lines.extend(["", "Warnings:"])
            lines.extend(warnings)
        return "\n".join(lines)

    def _markdown_body(self, error_msg: None | Exception,
                       result: NotifyResult | None = None) -> str:
        # Mirrors _text_body's structure exactly (same content, same order) with
        # markdown emphasis on headline/group headers and every interpolated
        # untrusted value wrapped in _md_code(). See _md_code for why the wrapping
        # is mandatory (apprise's MARKDOWN->HTML conversion does not escape HTML).
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        if error_msg:
            return "\n".join([
                "",
                "**Bookstack File Exporter encountered an unrecoverable error.**",
                "",
                f"Occurred At: {timestamp}",
                "",
                f"Error message: {_md_code(str(error_msg))}",
            ])
        if result is not None and result.status is ExportStatus.EMPTY:
            return "\n".join([
                "",
                "**Bookstack File Exporter completed - nothing to archive.**",
                "",
                f"Completed At: {timestamp}",
                "",
                f"No {result.export_level} content was found to export.",
            ])
        partial = result is not None and result.status is ExportStatus.PARTIAL
        headline = ("**Bookstack File Exporter completed with errors.**"
                    if partial else
                    "**Bookstack File Exporter completed successfully.**")
        lines = ["", headline, "", f"Completed At: {timestamp}"]
        failed: list[str] = _content_failure_bullets(result)
        warnings: list[str] = []
        if result is not None and result.local is not None:
            local_abs = os.path.abspath(result.local)
            removed_abs = {os.path.abspath(p) for p in result.removed}
            archive_line = f"Archive: {_md_code(result.local)}"
            if local_abs in removed_abs:
                archive_line += " (removed locally after upload)"
            lines.append(archive_line)
            ok_uploads = [o for o in result.uploads if o.dest]
            if ok_uploads:
                lines.extend(["", "**Uploaded to:**", ""])
                lines.extend(f"- {_md_code(o.label)}: {_md_code(o.dest)}" for o in ok_uploads)
            for outcome in result.uploads:
                if not outcome.dest:
                    failed.append(f"- {_md_code(outcome.label)}: {_md_code(outcome.error)}")
                elif outcome.warning:
                    warnings.append(f"- {_md_code(outcome.label)}: {_md_code(outcome.warning)}")
            pruned = _pruned_bullets(result, local_abs, removed_abs, wrap_labels=True)
            if pruned:
                lines.extend(["", "**Pruned:**", ""])
                lines.extend(pruned)
        if result is not None and result.cleanup_error:
            warnings.append(f"- local cleanup failed: {_md_code(result.cleanup_error)}")
        # Blank line before AND after each group header: without the leading one,
        # CommonMark lazy continuation absorbs the header into the preceding bullet
        # list; without the trailing one, the bullets never become a <ul>.
        if failed:
            lines.extend(["", "**Failed:**", ""])
            lines.extend(failed)
        if warnings:
            lines.extend(["", "**Warnings:**", ""])
            lines.extend(warnings)
        return "\n".join(lines)

    def notify(self, excep: Exception | None = None, result: NotifyResult | None = None):
        """send notification with exception message"""
        custom_body = self._get_message_text(excep, result)
        title_ = self._get_title(excep, result)
        body_format_ = (NotifyFormat.MARKDOWN
                         if self.config.body_format == "markdown"
                         else NotifyFormat.TEXT)
        if self.config.custom_attachment:
            self._client.notify(
                title=title_,
                body=custom_body,
                attach=self.config.custom_attachment,
                body_format=body_format_
            )
        else:
            self._client.notify(
                title=title_,
                body=custom_body,
                body_format=body_format_
            )
