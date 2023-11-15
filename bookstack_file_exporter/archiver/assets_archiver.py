import re
from typing import Union, List, Dict

from bookstack_file_exporter.config_helper.models import Assets
from bookstack_file_exporter.common import util as common_util

_IMAGE_DIR_SUFFIX = "_images"
_MARKDOWN_IMAGE_REGEX= re.compile(r"\[\!\[^$|.*\].*\]")
_MARKDOWN_STR_CHECK = "markdown"

class AssetsArchiver:
    """
    Get Asset Configuration from YAML file and normalize the data in an accessible object

    Args:
        Arg parse from user input

    Returns:
        ConfigNode object with attributes that are 
        accessible for use for further downstream processes

    Raises:
        YAMLError: if provided configuration file is not valid YAML

        ValueError: if improper arguments are given from user
    """
    def __init__(self, asset_config: Union[Assets, None], export_formats: List[str]) -> None:
        self.asset_config = asset_config
        self.export_images: bool = self._image_check()
        self.modify_md: bool = self._check_md_modify(export_formats)
        self.capture_image_regex = _MARKDOWN_IMAGE_REGEX

    def _image_check(self) -> bool:
        if self.asset_config:
            return self.asset_config.export_images
        return False

    def _check_md_modify(self, export_formats: List[str]) -> bool:
        if self.asset_config:
            if _MARKDOWN_STR_CHECK in export_formats:
                return self.asset_config.modify_markdown and self.export_images
        return False

    def get_image_meta(self, headers: Dict[str, str], image_api_url: str) -> Dict[int, List[str]]:
        """Get all image metadata into a {page_number: [image_url]} format"""
        img_meta_response = common_util.http_get_request(image_api_url, headers)
        img_meta_json = img_meta_response.json()['data']
        return self._create_image_map(img_meta_json)
        
    def _create_image_map(json_data: List[Dict[str, Union[str,int]]]) -> Dict[int, List[str]]:
        image_page_map = {}
        for image_node in json_data:
            image_page_id = image_node['uploaded_to']
            image_url = image_node['url']
            if image_page_id in image_page_map:
                image_page_map[image_page_id].append(image_url)
            else:
                image_page_map[image_page_id] = [image_url]
        return image_page_map

    def archive_images(self, page_path: str):
        """pull images locally into a directory based on page"""
        pass

    def update_image_links(self):
        """regex replace links to local created directories"""
        pass

    def _valid_image_link(self):
        """should contain bookstack host"""
        pass
