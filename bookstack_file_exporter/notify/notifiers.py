import os
from datetime import datetime
from apprise import Apprise, AppriseAsset, AppriseConfig

from bookstack_file_exporter.config_helper import notifications
from bookstack_file_exporter.notify.models import NotifyResult, ExportStatus

_DEFAULT_TITLE_PREFIX = "Bookstack File Exporter "

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
        if result is not None and result.local is not None:
            local_abs = os.path.abspath(result.local)
            removed_abs = {os.path.abspath(p) for p in result.removed}
            archive_line = f"Archive: {result.local}"
            if local_abs in removed_abs:
                archive_line += " (removed locally after upload)"
            lines.append(archive_line)
            # Preserve the concise "Uploaded to:" success line for targets that succeeded;
            # list any failures explicitly below it (partial runs).
            ok_dests = [o.dest for o in result.uploads if o.dest]
            if ok_dests:
                lines.append(f"Uploaded to: {', '.join(ok_dests)}")
            for outcome in result.uploads:
                if not outcome.dest:
                    lines.append(f"Failed: {outcome.label} - {outcome.error}")
                elif outcome.warning:
                    lines.append(f"Warning: {outcome.label} - {outcome.warning}")
            pruned_count = len(removed_abs - {local_abs})
            if pruned_count > 0:
                lines.append(f"Pruned {pruned_count} old local archive(s)")
        return "\n".join(lines)

    def notify(self, excep: Exception | None = None, result: NotifyResult | None = None):
        """send notification with exception message"""
        custom_body = self._get_message_text(excep, result)
        title_ = self._get_title(excep, result)
        if self.config.custom_attachment:
            self._client.notify(
                title=title_,
                body=custom_body,
                attach=self.config.custom_attachment
            )
        else:
            self._client.notify(
                title=title_,
                body=custom_body
            )
