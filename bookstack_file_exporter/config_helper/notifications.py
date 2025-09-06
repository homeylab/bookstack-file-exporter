import json
import logging
import os
from typing import Union

from bookstack_file_exporter.config_helper import models
from bookstack_file_exporter.common.util import check_var

log = logging.getLogger(__name__)

_APPRISE_FIELDS = {
    "urls": "APPRISE_URLS",
    # "config_path": "APPRISE_CONFIG_PATH",
    # "plugin_paths": "APPRISE_PLUGIN_PATHS",
    # "storage_path": "APPRISE_STORAGE_PATH"
}

_DEFAULT_TITLE = "Bookstack File Exporter Failed"

# pylint: disable=too-few-public-methods, too-many-instance-attributes
class AppRiseNotifyConfig:
    """
    Convenience class to hold apprise notification configuration
    
    Args:
        :config: <models.AppRiseNotifyConfig> = user input configuration
    
    Returns:
        AppRiseNotifyConfig instance for holding configuration
    """
    def __init__(self, config: models.AppRiseNotifyConfig):
        self.service_urls: Union[str, list] = check_var(_APPRISE_FIELDS["urls"],
                                  config.service_urls, can_error=True)
        self.config_path = config.config_path
        self.plugin_paths = config.plugin_paths
        self.storage_path = config.storage_path
        self.custom_title = config.custom_title
        self.custom_attachment = config.custom_attachment_path
        self.on_success = config.on_success
        self.on_failure = config.on_failure

    def validate(self) -> None:
        """validate apprise configuration"""
        if not self.config_path and not self.service_urls:
            raise ValueError("""apprise config_path and service_urls are
                              missing from configuration - at least one should be set""")

        # if not config path/file given, then we use service_urls
        if not self.config_path:
            # if not config path style, we try service_urls
            # if service_urls defined in env, override main config file value
            if os.environ.get(_APPRISE_FIELDS["urls"]) is not None:
                try:
                    new_urls = json.loads(self.service_urls)
                    self.service_urls = new_urls
                # json errors can be hard to debug, add helpful log message
                except json.decoder.JSONDecodeError as url_err:
                    log.Error("Failed to parse env var for apprise urls. \
                            Ensure proper json string format")
                    raise url_err

        # set default custom_title if not provided
        if not self.custom_title:
            self.custom_title = _DEFAULT_TITLE
