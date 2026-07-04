"""Shared factories for building minimal valid S3 config objects.

Fixture factories (not plain helpers) so each test names exactly the fields it
overrides and schema changes are absorbed in one place.
"""
from unittest.mock import MagicMock

import pytest

from bookstack_file_exporter.archiver.node_archiver import PageArchiver
from bookstack_file_exporter.config_helper.models import S3StorageConfig
from bookstack_file_exporter.config_helper.remote import S3ProviderConfig
from tests.fixtures.mock_config import make_mock_config as _make_config


@pytest.fixture
def page_archiver(tmp_path):
    """Construct a PageArchiver with all external collaborators mocked."""
    config = _make_config()
    http_client = MagicMock()
    archive_dir = str(tmp_path / "bookstack-20260514")
    return PageArchiver(archive_dir, config, http_client, asset_archiver=MagicMock())


@pytest.fixture
def make_storage_entry():
    """Factory for a minimal valid custom-store S3StorageConfig; kwargs override."""
    def _make(**overrides):
        base = {"name": "t", "bucket": "b", "endpoint": "minio.local:9000",
                "access_key": "a", "secret_key": "s"}
        base.update(overrides)
        return S3StorageConfig(**base)
    return _make


@pytest.fixture
def make_provider(make_storage_entry):  # pylint: disable=redefined-outer-name
    """Factory for a resolved S3ProviderConfig; kwargs are entry overrides."""
    def _make(**overrides):
        return S3ProviderConfig(make_storage_entry(**overrides))
    return _make
