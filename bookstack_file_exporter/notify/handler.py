import logging
from typing import Union

from bookstack_file_exporter.config_helper import models, notifications
from bookstack_file_exporter.notify import notifiers


log = logging.getLogger(__name__)

# pylint: disable=too-few-public-methods
class NotifyHandler:
    """
    NotifyHandler helps push out notifications for failed export runs

    Args:
        :config: <models.Notifications> = User input configuration for notification handlers
    
    Returns:
        NotifyHandler instance to help handle notification integrations.
    """
    def __init__(self, config: models.Notifications):
        self.targets = self._get_targets(config)
        self._supported_notifiers={
            "apprise": self._handle_apprise
        }

    def _get_targets(self, config: models.Notifications):
        targets = {}

        if config.apprise:
            targets["apprise"] = config.apprise

        return targets

    def do_notify(self, excep: Union[None, Exception] = None) -> None:
        """handle notification sending for all configured targets"""
        if len(self.targets) == 0:
            log.debug("No notification targets found")
            return
        for target, config in self.targets.items():
            log.debug("Starting notification handling for: %s", target)
            self._supported_notifiers[target](config, excep)

    def _handle_apprise(self, config: models.AppRiseNotifyConfig, excep: Exception):
        a_config = notifications.AppRiseNotifyConfig(config)
        a_config.validate()
        apprise = notifiers.AppRiseNotify(a_config)
        # only send notification if on_success or on_failure is set
        if (not excep and a_config.on_success) or (excep and a_config.on_failure):
            log.info("Sending notification for run status")
            apprise.notify(excep)
