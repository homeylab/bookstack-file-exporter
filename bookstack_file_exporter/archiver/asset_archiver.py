from typing import Union, List, Dict
# pylint: disable=import-error
from requests import Response
from re import sub as re_sub
import logging
import base64

from bookstack_file_exporter.common import util as common_util

log = logging.getLogger(__name__)

_IMAGE_DIR_NAME = "images"
_ATTACHMENT_DIR_NAME = "attachments"


class AssetNode:
    def __init__(self, meta_data: Dict[str, int | str | bool]):
        self.id: int = meta_data['id']
        self.page_id: int = meta_data['uploaded_to']
        # self.page_name: str = page_name
        self.url: str = meta_data['url']
        self.name: str = self.url.split('/')[-1]
        self._markdown_str = ""
        self._relative_path_prefix: str = ""

    def get_relative_path(self, page_name: str) -> str:
        """image path local to page directory"""
        return f"{self._relative_path_prefix}/{page_name}/{self.name}"

    @property
    def markdown_str(self):
        """return markdown url str to replace"""
        return self._markdown_str

    def set_markdown_content(self, asset_data: Dict[str, int | str | bool]) -> None:
        self._markdown_str = self._get_md_url_str(asset_data)

    @staticmethod
    def _get_md_url_str(asset_data: Dict[str, Union[int, str]]) -> str:
        url_str = ""
        if 'content' in asset_data:
            if 'markdown' in asset_data['content']:
                url_str = asset_data['content']['markdown']
        # check to see if empty before doing find
        if not url_str:
            return ""
        # find the link between two parenthesis
        # - markdown format
        return url_str[url_str.find("(")+1:url_str.find(")")]

class ImageNode(AssetNode):
    def __init__(self, meta_data: Dict[str, Union[int, str]]):
        super().__init__(meta_data)
        log.debug(self.url)
        self._relative_path_prefix = f"{_IMAGE_DIR_NAME}"

class AttachmentNode(AssetNode):
    def __init__(self, meta_data: Dict[str, Union[int, str, bool]],
                 base_url: str):
        self.id: int = meta_data['id']
        self.page_id: int = meta_data['uploaded_to']
        self.url: str = f"{base_url}/{self.id}"
        log.debug(self.url)
        self.name = meta_data['name']
        self._markdown_str = ""
        self._relative_path_prefix = f"{_ATTACHMENT_DIR_NAME}"

    @staticmethod
    def _get_md_url_str(asset_data: Dict[str, int | str | dict]) -> str:
        url_str = ""
        if 'links' in asset_data:
            if 'markdown' in asset_data['links']:
                url_str = asset_data['links']['markdown']
        # check to see if empty before doing find
        if not url_str:
            return ""
        # find the link between two parenthesis
        # - markdown format
        return url_str[url_str.find("(")+1:url_str.find(")")]

class AssetArchiver:
    def __init__(self, urls: Dict[str, str], headers: Dict[str, str],
                 verify_ssl: bool):
        self.api_urls = urls
        self.verify_ssl = verify_ssl
        self._headers = headers
        self._asset_map = {
            'images': self._create_image_map,
            'attachments': self._create_attachment_map
        }

    def get_asset_nodes(self, asset_type: str) -> Dict[str, ImageNode | AttachmentNode]:
        """Get image or attachment helpers for a page"""
        asset_response: Response = common_util.http_get_request(
            self.api_urls[asset_type],
            self._headers,
            self.verify_ssl)
        asset_json = asset_response.json()['data']
        return self._asset_map[asset_type](asset_json)

    def get_asset_data(self, asset_type: str,
            meta_data: Union[AttachmentNode, ImageNode]) -> Dict[str, str | bool | int | dict]:
        """Get asset data based on type"""
        data_url = f"{self.api_urls[asset_type]}/{meta_data.id}"
        asset_data_response: Response = common_util.http_get_request(
            data_url,
            self._headers,
            self.verify_ssl)
        return asset_data_response.json()

    def get_asset_bytes(self, asset_type: str, url: str) -> bytes:
        """Get raw asset data"""
        asset_response: Response = common_util.http_get_request(
            url,
            self._headers,
            self.verify_ssl)
        match asset_type:
            case "images":
                asset_data = asset_response.content
            case "attachments":
                asset_data = self.decode_attachment_data(asset_response.json()['content'])
        return asset_data

    def update_asset_links(self, asset_type, page_name: str, page_data: bytes,
            asset_nodes: List[ImageNode | AttachmentNode]) -> bytes:
        """update markdown links in page data"""
        for asset_node in asset_nodes:
            asset_data = self.get_asset_data(asset_type, asset_node)
            asset_node.set_markdown_content(asset_data)
            if not asset_node.markdown_str:
                continue
            page_data = re_sub(asset_node.markdown_str.encode(),
                               asset_node.get_relative_path(page_name).encode(), page_data)
        return page_data

    @staticmethod
    def _create_image_map(json_data: Dict[str,
            List[Dict[str, str | int | bool | dict]]]) -> Dict[int, List[ImageNode]]:
        image_page_map = {}
        for img_meta in json_data:
            img_node = ImageNode(img_meta)
            if img_node.page_id in image_page_map:
                image_page_map[img_node.page_id].append(img_node)
            else:
                image_page_map[img_node.page_id] = [img_node]
        return image_page_map

    def _create_attachment_map(self,
            json_data: Dict[str, List[Dict[str, str | int | bool | dict]]]) -> List[AssetNode]:
        asset_nodes = {}
        for asset_meta in json_data:
            asset_node = None
            if asset_meta['external']:
                continue # skip external link, only get attachments
            asset_node = AttachmentNode(asset_meta, self.api_urls['attachments'])
            if asset_node.page_id in asset_nodes:
                asset_nodes[asset_node.page_id].append(asset_node)
            else:
                asset_nodes[asset_node.page_id] = [asset_node]
        return asset_nodes
    
    @staticmethod
    def decode_attachment_data(b64encoded_data: str) -> bytes:
        """decode base64 encoded data"""
        asset_data = b64encoded_data.encode()
        return base64.b64decode(asset_data)
