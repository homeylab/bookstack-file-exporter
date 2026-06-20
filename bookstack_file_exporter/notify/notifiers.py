import os
from datetime import datetime
from apprise import Apprise, AppriseAsset, AppriseConfig

from bookstack_file_exporter.config_helper import notifications
from bookstack_file_exporter.notify.models import NotifyResult

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

    def _get_title(self, excep: None | Exception) -> str:
        if self.config.custom_title:
            return self.config.custom_title
        if excep:
            return _DEFAULT_TITLE_PREFIX + "Failed"
        return _DEFAULT_TITLE_PREFIX + "Success"

    def _get_message_text(self, error_msg: None | Exception,
                          result: NotifyResult | None = None) -> str:
        timestamp = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
        if error_msg:
            error_str = str(error_msg)
            lines = [
                "",
                "Bookstack File Exporter encountered an unrecoverable error.",
                "",
                f"Occurred At: {timestamp}",
                "",
                f"Error message: {error_str}",
            ]
        else:
            lines = [
                "",
                "Bookstack File Exporter completed successfully.",
                "",
                f"Completed At: {timestamp}",
            ]
            if result is not None and result.local is not None:
                local_abs = os.path.abspath(result.local)
                removed_abs = {os.path.abspath(p) for p in result.removed}
                was_removed = local_abs in removed_abs

                archive_line = f"Archive: {result.local}"
                if was_removed:
                    archive_line += " (removed locally after upload)"
                lines.append(archive_line)

                if result.remote:
                    lines.append(f"Uploaded to: {', '.join(result.remote)}")

                pruned_count = len(removed_abs - {local_abs})
                if pruned_count > 0:
                    lines.append(f"Pruned {pruned_count} old local archive(s)")
        return "\n".join(lines)

    def notify(self, excep: Exception | None = None, result: NotifyResult | None = None):
        """send notification with exception message"""
        custom_body = self._get_message_text(excep, result)
        title_ = self._get_title(excep)
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
