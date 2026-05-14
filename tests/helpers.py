"""Shared test helpers (non-fixture)."""
from unittest.mock import MagicMock


def make_response(payload):
    """Build a MagicMock that mimics requests.Response for given json payload."""
    resp = MagicMock()
    resp.json.return_value = payload
    return resp
