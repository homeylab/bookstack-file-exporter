import json
import logging
import os

from bookstack_file_exporter.config_helper import models
from bookstack_file_exporter.common.util import check_var

log = logging.getLogger(__name__)

_APPRISE_FIELDS = {
    "urls": "APPRISE_URLS",
}

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
        self.service_urls: str | list = check_var(_APPRISE_FIELDS["urls"],
                                  config.service_urls, required=False)
        self.config_path = config.config_path
        self.plugin_paths = config.plugin_paths
        self.storage_path = config.storage_path
        self.custom_title = config.custom_title
        self.custom_attachment = config.custom_attachment_path
        self.on_success = config.on_success
        self.on_failure = config.on_failure
        self._resolve_service_urls()

    def _resolve_service_urls(self) -> None:
        """Resolve env-sourced service_urls once at construction.

        APPRISE_URLS arrives from the environment as a JSON string, so parse it
        into a list when that env var is set and no config_path is used. Doing
        this here (not in validate()) keeps validate() a pure predicate over
        already-resolved state. The truthy guard mirrors validate()'s missing
        check: an empty/None service_urls falls through to validate(), which
        raises ValueError — so a parse never runs on an empty value.
        """
        if (not self.config_path and self.service_urls
                and os.environ.get(_APPRISE_FIELDS["urls"]) is not None):
            try:
                self.service_urls = json.loads(self.service_urls)
            # json errors can be hard to debug, add helpful log message
            except json.decoder.JSONDecodeError as url_err:
                log.error("Failed to parse env var for apprise urls. \
                        Ensure proper json string format")
                raise url_err

    def validate(self) -> None:
        """Validate apprise configuration (pure predicate over resolved state)."""
        if not self.config_path and not self.service_urls:
            raise ValueError("""apprise config_path and service_urls are
                              missing from configuration - at least one should be set""")
