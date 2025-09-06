from datetime import datetime
from typing import Union
from apprise import Apprise, AppriseAsset, AppriseConfig

from bookstack_file_exporter.config_helper import notifications

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

    def _get_message_body(self, error_msg: Union[None, Exception]) -> str:
        timestamp = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
        if error_msg:
            error_str = str(error_msg)
            body = f"""
            Bookstack File Exporter encountered an unrecoverable error.
            
            Occurred At: {timestamp}
            
            Error message: {error_str}
            """
        else:
            body = f"""
            Bookstack File Exporter completed successfully.
            
            Completed At: {timestamp}
            """
        return body

    def notify(self, excep: Exception):
        """send notification with exception message"""
        custom_body = self._get_message_body(excep)
        if self.config.custom_attachment:
            self._client.notify(
                title=self.config.custom_title,
                body=custom_body,
                attach=self.config.custom_attachment
            )
        else:
            self._client.notify(
                title=self.config.custom_title,
                body=custom_body
            )
