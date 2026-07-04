# pylint: disable=missing-function-docstring
"""Unit tests asserting explicit YAML null is rejected for config fields whose
`| None` annotation was dropped: the field's default already covers "key
omitted", so `| None` only ever let an explicit YAML `null` (e.g. `timeout:
null`) validate straight to None and flow downstream unchecked. Composite
fields (credentials/assets/http_config) are covered separately in
test_models_null_composite.py -- they still accept null via a before-validator
that coerces it to the field's default instance."""
import pytest
from pydantic import ValidationError

from bookstack_file_exporter.config_helper.models import (
    BookstackAccess,
    HttpConfig,
    UserInput,
)

_USER_BASE = {"host": "https://wiki.example", "formats": ["markdown"]}


@pytest.mark.parametrize("field", [
    "verify_ssl", "timeout", "backoff_factor", "retry_codes", "retry_count",
    "additional_headers", "ca_bundle",
])
def test_http_config_rejects_explicit_null(field):
    with pytest.raises(ValidationError):
        HttpConfig(**{field: None})


def test_http_config_omitted_keys_still_default():
    cfg = HttpConfig()
    assert cfg.verify_ssl is True  # secure-by-default: verify the BookStack TLS cert
    assert cfg.timeout == 30
    assert cfg.retry_codes == [413, 429, 500, 502, 503, 504]
    assert cfg.ca_bundle == ""


def test_http_config_ca_bundle_with_verify_off_rejected():
    with pytest.raises(ValidationError, match="mutually exclusive"):
        HttpConfig(verify_ssl=False, ca_bundle="/certs/ca.pem")


@pytest.mark.parametrize("field", ["token_id", "token_secret"])
def test_bookstack_access_rejects_explicit_null(field):
    with pytest.raises(ValidationError):
        BookstackAccess(**{field: None})


def test_user_input_rejects_null_keep_last():
    with pytest.raises(ValidationError):
        UserInput(**_USER_BASE, keep_last=None)


def test_user_input_rejects_null_output_path():
    with pytest.raises(ValidationError):
        UserInput(**_USER_BASE, output_path=None)


def test_user_input_omitted_keys_still_default():
    cfg = UserInput(**_USER_BASE)
    assert cfg.keep_last == 0
    assert cfg.output_path == ""
