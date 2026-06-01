# pylint: disable=missing-class-docstring,missing-function-docstring
# pylint: disable=too-many-arguments,too-many-positional-arguments,duplicate-code
"""Shared MagicMock factory for AssetArchiver/PageArchiver config tests."""
from unittest.mock import MagicMock


def make_mock_config(*, formats=None, export_images=False, export_attachments=False,
                     export_meta=False, modify_links=False,
                     export_level="pages") -> MagicMock:
    config = MagicMock()
    config.urls = {
        "books": "https://wiki.test.example/api/books",
        "chapters": "https://wiki.test.example/api/chapters",
        "pages": "https://wiki.test.example/api/pages",
        "images": "https://wiki.test.example/api/image-gallery",
        "attachments": "https://wiki.test.example/api/attachments",
    }
    config.user_inputs.formats = formats or ["markdown"]
    config.user_inputs.assets.export_images = export_images
    config.user_inputs.assets.export_attachments = export_attachments
    config.user_inputs.assets.export_meta = export_meta
    config.user_inputs.assets.modify_links = modify_links
    config.user_inputs.export_level = export_level
    return config
