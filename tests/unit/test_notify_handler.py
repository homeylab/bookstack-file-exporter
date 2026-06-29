# pylint: disable=missing-function-docstring,protected-access
from unittest.mock import MagicMock, patch

from bookstack_file_exporter.notify.handler import NotifyHandler
from bookstack_file_exporter.notify.models import ExportStatus, NotifyResult


def _handler():
    return NotifyHandler.__new__(NotifyHandler)


def _run_gate(excep, result, on_success, on_failure):
    """Drive _handle_apprise and report whether a notification was sent."""
    h = _handler()
    a_config = MagicMock(on_success=on_success, on_failure=on_failure)
    with patch("bookstack_file_exporter.notify.handler.notifications") as notif_mod, \
         patch("bookstack_file_exporter.notify.handler.notifiers") as notif_pkg:
        notif_mod.AppRiseNotifyConfig.return_value = a_config
        sender = MagicMock()
        notif_pkg.AppRiseNotify.return_value = sender
        h._handle_apprise(MagicMock(), excep, result)
        return sender.notify.called


def test_partial_fires_on_failure():
    result = NotifyResult(status=ExportStatus.PARTIAL, local="/a/b.tgz")
    assert _run_gate(None, result, on_success=False, on_failure=True) is True


def test_partial_suppressed_when_on_failure_false():
    result = NotifyResult(status=ExportStatus.PARTIAL, local="/a/b.tgz")
    assert _run_gate(None, result, on_success=True, on_failure=False) is False


def test_success_fires_on_success():
    result = NotifyResult(status=ExportStatus.SUCCESS, local="/a/b.tgz")
    assert _run_gate(None, result, on_success=True, on_failure=False) is True
