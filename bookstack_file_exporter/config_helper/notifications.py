from bookstack_file_exporter.config_helper import models
from bookstack_file_exporter.common.util import resolve_env_json

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
        # env (JSON array string) wins over the config-file list; resolved +
        # validated once here. `or []` keeps the []-not-None guarantee.
        self.service_urls = resolve_env_json(_APPRISE_FIELDS["urls"], list[str],
                                             config.service_urls or [])
        self.config_path = config.config_path
        self.plugin_paths = config.plugin_paths
        self.storage_path = config.storage_path
        self.custom_title = config.custom_title
        self.custom_attachment = config.custom_attachment_path
        self.on_success = config.on_success
        self.on_failure = config.on_failure

    def validate(self) -> None:
        """Validate apprise configuration (pure predicate over resolved state)."""
        if not self.config_path and not self.service_urls:
            raise ValueError("""apprise config_path and service_urls are
                              missing from configuration - at least one should be set""")
