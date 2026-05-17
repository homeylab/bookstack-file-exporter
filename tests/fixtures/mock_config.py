# pylint: disable=missing-class-docstring,missing-function-docstring
"""Shared MagicMock factory for AssetArchiver/PageArchiver config tests."""
from unittest.mock import MagicMock


def make_mock_config(*, formats=None, export_images=False, export_attachments=False,
                     export_meta=False, modify_links=False) -> MagicMock:
    config = MagicMock()
    config.urls = {
        "pages": "https://wiki.test.example/api/pages",
        "images": "https://wiki.test.example/api/image-gallery",
        "attachments": "https://wiki.test.example/api/attachments",
    }
    config.user_inputs.formats = formats or ["markdown"]
    config.user_inputs.assets.export_images = export_images
    config.user_inputs.assets.export_attachments = export_attachments
    config.user_inputs.assets.export_meta = export_meta
    config.user_inputs.assets.modify_links = modify_links
    return config
