"""Tests for StorageProviderConfig validation dispatch."""
from bookstack_file_exporter.config_helper.models import ObjectStorageConfig
from bookstack_file_exporter.config_helper.remote import StorageProviderConfig


def _config(**overrides):
    base = {"bucket": "b", "region": "us-east-1", "host": "minio.local"}
    base.update(overrides)
    return ObjectStorageConfig(**base)


def test_is_valid_true_when_host_present():
    """is_valid returns True when the minio host is set."""
    cfg = StorageProviderConfig("ak", "sk", _config(host="minio.local"))
    assert cfg.is_valid("minio") is True


def test_is_valid_false_when_host_missing():
    """is_valid returns False when the minio host is empty."""
    cfg = StorageProviderConfig("ak", "sk", _config(host=""))
    assert cfg.is_valid("minio") is False
