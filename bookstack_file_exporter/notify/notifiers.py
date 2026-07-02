import os
from datetime import datetime
from apprise import Apprise, AppriseAsset, AppriseConfig, NotifyFormat

from bookstack_file_exporter.config_helper import notifications
from bookstack_file_exporter.notify.models import NotifyResult, ExportStatus

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

# pylint: disable=too-few-public-methods
class AppRiseNotify:
    """
    AppRiseNotify helps send notifications via apprise for failed export runs

    Args:
        :config: <notifications.AppRiseNotifyConfig> = Configuration with user inputs and
                                                       general options

    Returns:
        AppRiseNotify instance to help handle apprise notification integration.
    """
    def __init__(self, config: notifications.AppRiseNotifyConfig):
        self.config = config
        self._client = self._create_client()

    def _create_client(self):
        client = Apprise()
        asset = AppriseAsset()

        if self.config.storage_path:
            asset.storage_path=self.config.storage_path

        if self.config.plugin_paths:
            asset.plugin_paths = self.config.plugin_paths

        if self.config.config_path:
            app_config = AppriseConfig()
            app_config.add(self.config.config_path)
            client.add(app_config)
        else:
            client.add(self.config.service_urls)

        client.asset=asset
        return client

    def _get_title(self, excep: None | Exception,
                   result: NotifyResult | None = None) -> str:
        if self.config.custom_title:
            return self.config.custom_title
        if excep:
            return _DEFAULT_TITLE_PREFIX + "Failed"
        if result is not None and result.status is ExportStatus.PARTIAL:
            return _DEFAULT_TITLE_PREFIX + "Partial"
        return _DEFAULT_TITLE_PREFIX + "Success"

    def _get_message_text(self, error_msg: None | Exception,
                          result: NotifyResult | None = None) -> str:
        if self.config.body_format == "markdown":
            return self._markdown_body(error_msg, result)
        return self._text_body(error_msg, result)

    def _text_body(self, error_msg: None | Exception,
                   result: NotifyResult | None = None) -> str:
        timestamp = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
        if error_msg:
            return "\n".join([
                "",
                "Bookstack File Exporter encountered an unrecoverable error.",
                "",
                f"Occurred At: {timestamp}",
                "",
                f"Error message: {str(error_msg)}",
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
        failed: list[str] = []
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
            # Pruned: group covers local retention plus per-target remote retention,
            # local bullet first, zero-count targets omitted.
            pruned_local = len(removed_abs - {local_abs})
            pruned = [f"- local: {pruned_local} archive(s)"] if pruned_local > 0 else []
            pruned.extend(f"- {o.label}: {o.pruned} archive(s)"
                          for o in result.uploads if o.pruned > 0)
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
        timestamp = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
        if error_msg:
            return "\n".join([
                "",
                "**Bookstack File Exporter encountered an unrecoverable error.**",
                "",
                f"Occurred At: {timestamp}",
                "",
                f"Error message: {_md_code(str(error_msg))}",
            ])
        partial = result is not None and result.status is ExportStatus.PARTIAL
        headline = ("**Bookstack File Exporter completed with errors.**"
                    if partial else
                    "**Bookstack File Exporter completed successfully.**")
        lines = ["", headline, "", f"Completed At: {timestamp}"]
        failed: list[str] = []
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
            pruned_local = len(removed_abs - {local_abs})
            pruned = [f"- local: {pruned_local} archive(s)"] if pruned_local > 0 else []
            pruned.extend(f"- {_md_code(o.label)}: {o.pruned} archive(s)"
                          for o in result.uploads if o.pruned > 0)
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
