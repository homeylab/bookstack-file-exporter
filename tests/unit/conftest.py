"""Shared factories for building minimal valid S3 config objects.

Fixture factories (not plain helpers) so each test names exactly the fields it
overrides and schema changes are absorbed in one place.
"""
import pytest

from bookstack_file_exporter.config_helper.models import S3StorageConfig
from bookstack_file_exporter.config_helper.remote import S3ProviderConfig


@pytest.fixture
def make_storage_entry():
    """Factory for a minimal valid custom-store S3StorageConfig; kwargs override."""
    def _make(**overrides):
        base = dict(name="t", bucket="b", endpoint="minio.local:9000",
                    access_key="a", secret_key="s")
        base.update(overrides)
        return S3StorageConfig(**base)
    return _make


@pytest.fixture
def make_provider(make_storage_entry):
    """Factory for a resolved S3ProviderConfig; kwargs are entry overrides."""
    def _make(**overrides):
        return S3ProviderConfig(make_storage_entry(**overrides))
    return _make
