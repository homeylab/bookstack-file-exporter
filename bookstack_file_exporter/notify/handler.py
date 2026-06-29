import logging

from bookstack_file_exporter.config_helper import models, notifications
from bookstack_file_exporter.notify import notifiers
from bookstack_file_exporter.notify.models import ExportStatus, NotifyResult


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

    def do_notify(self, excep: None | Exception = None, result: NotifyResult | None = None) -> None:
        """handle notification sending for all configured targets"""
        if len(self.targets) == 0:
            log.debug("No notification targets found")
            return
        for target, config in self.targets.items():
            log.debug("Starting notification handling for: %s", target)
            self._supported_notifiers[target](config, excep, result)

    def _handle_apprise(self, config: models.AppRiseNotifyConfig,
                        excep: None | Exception = None,
                        result: NotifyResult | None = None):
        a_config = notifications.AppRiseNotifyConfig(config)
        a_config.validate()
        apprise = notifiers.AppRiseNotify(a_config)
        # PARTIAL is a degraded run: treat it like a failure for gating so on_failure
        # subscribers are alerted (a copy survived, but a target did not receive it).
        is_partial = result is not None and result.status is ExportStatus.PARTIAL
        fire_failure = excep is not None or is_partial
        if (not fire_failure and a_config.on_success) or (fire_failure and a_config.on_failure):
            log.info("Sending notification for run status")
            apprise.notify(excep, result)
