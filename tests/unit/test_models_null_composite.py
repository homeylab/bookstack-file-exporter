# pylint: disable=missing-function-docstring,missing-module-docstring
"""S4: an explicit YAML null on a composite key ('credentials:' with children
commented out, etc.) must coerce to the field's default model instance, not
None -- downstream code unconditionally dereferences .credentials.token_id,
.http_config.additional_headers, and assets fields."""
from bookstack_file_exporter.config_helper.models import (
    Assets,
    BookstackAccess,
    HttpConfig,
    UserInput,
)

_BASE = {"host": "https://wiki.example", "formats": ["markdown"]}


def test_null_credentials_becomes_default_instance():
    cfg = UserInput(**_BASE, credentials=None)
    assert cfg.credentials == BookstackAccess()
    assert cfg.credentials.token_id == ""
    assert cfg.credentials.token_secret == ""


def test_null_assets_becomes_default_instance():
    cfg = UserInput(**_BASE, assets=None)
    assert cfg.assets == Assets()
    assert cfg.assets.export_images is False


def test_null_http_config_becomes_default_instance():
    cfg = UserInput(**_BASE, http_config=None)
    assert cfg.http_config == HttpConfig()
    assert cfg.http_config.additional_headers == {}


def test_omitted_composite_keys_still_default_as_before():
    """Regression guard: the before-validator must not change behavior when the
    keys are simply absent (existing default-instance construction path)."""
    cfg = UserInput(**_BASE)
    assert cfg.credentials == BookstackAccess()
    assert cfg.assets == Assets()
    assert cfg.http_config == HttpConfig()


def test_explicit_composite_values_still_pass_through():
    cfg = UserInput(**_BASE, credentials={"token_id": "a", "token_secret": "b"})
    assert cfg.credentials.token_id == "a"
    assert cfg.credentials.token_secret == "b"
