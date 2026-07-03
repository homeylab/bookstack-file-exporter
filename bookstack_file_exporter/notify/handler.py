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
        self.apprise_config = config.apprise

    def do_notify(self, excep: None | Exception = None, result: NotifyResult | None = None) -> None:
        """handle notification sending for all configured targets"""
        if not self.apprise_config:
            log.debug("No notification targets found")
            return
        log.debug("Starting notification handling for: apprise")
        self._handle_apprise(self.apprise_config, excep, result)

    def _handle_apprise(self, config: models.AppRiseNotifyConfig,
                        excep: None | Exception = None,
                        result: NotifyResult | None = None):
        a_config = notifications.ResolvedAppriseConfig(config)
        a_config.validate()
        apprise = notifiers.AppRiseNotify(a_config)
        # PARTIAL is a degraded run: treat it like a failure for gating so on_failure
        # subscribers are alerted (a copy survived, but a target did not receive it).
        # EMPTY is success-toned (nothing to archive is not a degradation) and falls
        # through to the on_success branch below like SUCCESS.
        is_partial = result is not None and result.status is ExportStatus.PARTIAL
        fire_failure = excep is not None or is_partial
        if (not fire_failure and a_config.on_success) or (fire_failure and a_config.on_failure):
            log.info("Sending notification for run status")
            apprise.notify(excep, result)
