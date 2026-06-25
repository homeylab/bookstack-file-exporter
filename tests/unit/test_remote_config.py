# pylint: disable=missing-function-docstring
"""Tests for StorageProviderConfig validation dispatch and AWS endpoint helper."""
from unittest.mock import MagicMock

from bookstack_file_exporter.config_helper.models import BaseStorageConfig
from bookstack_file_exporter.config_helper.remote import (
    StorageProviderConfig,
    aws_endpoint_from_region,
)


def _provider(entry: BaseStorageConfig) -> StorageProviderConfig:
    # credentials Provider is opaque here; a MagicMock stands in.
    return StorageProviderConfig(
        storage_type=entry.type,
        endpoint=entry.host or "",
        secure=entry.secure,
        credentials=MagicMock(),
        config=entry,
    )


def test_minio_valid_when_host_present():
    entry = BaseStorageConfig(type="minio", bucket="b", host="minio.local")
    assert _provider(entry).is_valid("minio") is True


def test_minio_invalid_when_host_missing():
    entry = BaseStorageConfig(type="minio", bucket="b", host="")
    assert _provider(entry).is_valid("minio") is False


def test_s3_valid_when_region_present():
    entry = BaseStorageConfig(type="s3", bucket="b", region="us-east-1")
    assert _provider(entry).is_valid("s3") is True


def test_s3_invalid_when_region_missing():
    entry = BaseStorageConfig(type="s3", bucket="b", region=None)
    assert _provider(entry).is_valid("s3") is False


def test_aws_endpoint_from_region():
    assert aws_endpoint_from_region("us-east-1") == "s3.us-east-1.amazonaws.com"
    assert aws_endpoint_from_region("eu-west-2") == "s3.eu-west-2.amazonaws.com"
