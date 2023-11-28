from typing import Union, List, Dict
import re
# pylint: disable=import-error
from requests import Response

from bookstack_file_exporter.exporter.node import Node
from bookstack_file_exporter.archiver import util as archiver_util
from bookstack_file_exporter.config_helper.config_helper import ConfigNode
from bookstack_file_exporter.common import util as common_util

_META_FILE_SUFFIX = "_meta.json"
_TAR_SUFFIX = ".tar"
_TAR_GZ_SUFFIX = ".tgz"

_EXPORT_API_PATH = "export"

_FILE_EXTENSION_MAP = {
    "markdown": ".md",
    "html": ".html",
    "pdf": ".pdf",
    "plaintext": ".txt",
    "meta": _META_FILE_SUFFIX,
    "tar": _TAR_SUFFIX,
    "tgz": _TAR_GZ_SUFFIX
}

_IMAGE_DIR_NAME = "images"
_MARKDOWN_STR_CHECK = "markdown"

class ImageNode:
    """
    ImageNode provides metadata and convenience for Bookstack images.

    Args:
        :img_meta_data: <Dict[str, Union[int, str]> = image meta data

    Returns:
        :ImageNode: instance with attributes to help handle images.
    """
    def __init__(self, img_meta_data: Dict[str, Union[int, str]]):
        self.id: int = img_meta_data['id']
        self.page_id:  int = img_meta_data['uploaded_to']
        self.url: str = img_meta_data['url']
        self.name: str = self._get_image_name()
        self._markdown_str = ""
        self._relative_path_prefix: str = f"./{_IMAGE_DIR_NAME}"

    def _get_image_name(self) -> str:
        return self.url.split('/')[-1]

    def get_image_relative_path(self, page_name: str) -> str:
        """return image path local to page directory"""
        return f"{self._relative_path_prefix}/{page_name}/{self.name}"

    @property
    def markdown_str(self):
        """return markdown url str to replace"""
        return self._markdown_str

    def set_markdown_content(self, img_details: Dict[str, Union[int, str]]):
        """provide image metadata to set markdown properties"""
        self._markdown_str = self._get_md_url_str(img_details)

    @staticmethod
    def _get_md_url_str(img_data: Dict[str, Union[int, str]]) -> str:
        url_str = ""
        if 'content' in img_data:
            if _MARKDOWN_STR_CHECK in img_data['content']:
                url_str = img_data['content'][_MARKDOWN_STR_CHECK]
        # check to see if empty before doing find
        if not url_str:
            return ""
        return url_str[url_str.find("(")+1:url_str.find(")")]

# pylint: disable=too-many-instance-attributes
class PageArchiver:
    """
    PageArchiver handles all data extraction and modifications 
    to Bookstack page contents including images.

    Args:
        :archive_dir: <str> = directory where data will be put into.

        :config: <ConfigNode> = Configuration with user inputs and general options.

    Returns:
        :PageArchiver: instance with methods to help collect page content from a Bookstack instance.
    """
    def __init__(self, archive_dir: str, config: ConfigNode) -> None:
        self.asset_config = config.user_inputs.assets
        self.export_formats = config.user_inputs.formats
        self.api_urls = config.urls
        self._headers = config.headers
        # full path, bookstack-<timestamp>, and .tgz extension
        self.archive_file = f"{archive_dir}{_FILE_EXTENSION_MAP['tgz']}"
        # name of intermediate tar file before gzip
        self.tar_file = f"{archive_dir}{_FILE_EXTENSION_MAP['tar']}"
        # name of the base folder to use within the tgz archive (internal tar layout)
        self.archive_base_path = archive_dir.split("/")[-1]
        self.modify_md: bool = self._check_md_modify()

    def _check_md_modify(self) -> bool:
        # check to ensure they have asset_config defined, could be None
        if _MARKDOWN_STR_CHECK in self.export_formats:
            return self.asset_config.modify_markdown and self.export_images
        return False

    def archive_page(self, page: Node,
                      image_urls: List[str] = None):
        """export page content"""
        for export_format in self.export_formats:
            page_data = self._get_page_data(page.id_, export_format)
            self._archive_page(page, export_format,
                               page_data, image_urls)
        if self.asset_config.export_meta:
            self._archive_page_meta(page.file_path, page.meta)

    def _archive_page(self, page: Node, export_format: str, data: bytes,
                      image_nodes: List[ImageNode] = None):
        page_file_name = f"{self.archive_base_path}/" \
            f"{page.file_path}{_FILE_EXTENSION_MAP[export_format]}"
        if self.modify_md and export_format == _MARKDOWN_STR_CHECK and image_nodes:
            data = self._update_image_links(page.name, data, image_nodes)
        self.write_data(page_file_name, data)

    def _get_page_data(self, page_id: int, export_format: str):
        url = f"{self.api_urls['pages']}/{page_id}/{_EXPORT_API_PATH}/{export_format}"
        return archiver_util.get_byte_response(url=url, headers=self._headers,
                                               verify_ssl=self.verify_ssl)

    def _archive_page_meta(self, page_path: str, meta_data: Dict[str, Union[str, int]]):
        meta_file_name = f"{self.archive_base_path}/{page_path}{_FILE_EXTENSION_MAP['meta']}"
        bytes_meta = archiver_util.get_json_bytes(meta_data)
        self.write_data(file_path=meta_file_name, data=bytes_meta)

    def get_image_meta(self) -> Dict[int, List[ImageNode]]:
        """Get all image metadata into a {page_number: [image_url]} format"""
        img_meta_response: Response = common_util.http_get_request(
            self.api_urls['images'],
            self._headers,
            self.verify_ssl)
        img_meta_json = img_meta_response.json()['data']
        return self._create_image_map(img_meta_json)

    def archive_page_images(self, parent_path: str, page_name: str,
                            image_nodes: List[ImageNode]):
        """pull images locally into a directory based on page"""
        image_base_path = f"{self.archive_base_path}/{parent_path}/{_IMAGE_DIR_NAME}"
        for img_node in image_nodes:
            img_data: bytes = archiver_util.get_byte_response(img_node.url, self._headers,
                                                              self.verify_ssl)
            image_path = f"{image_base_path}/{page_name}/{img_node.name}"
            self.write_data(image_path, img_data)

    def write_data(self, file_path: str, data: bytes):
        """write data to a tar file
        Args:
            :file_path: <str> path of file relative to tar file inner directory

            :data: <bytes> data to write to that file_path within the tar
        """
        archiver_util.write_tar(self.tar_file, file_path, data)

    def gzip_archive(self):
        """provide the tar to gzip and the name of the gzip output file"""
        archiver_util.create_gzip(self.tar_file, self.archive_file)

    def _update_image_links(self, page_name: str, page_data: bytes,
                            image_nodes: List[ImageNode]) -> bytes:
        """regex replace links to local created directories"""
        for img_node in image_nodes:
            img_meta_url = f"{self.api_urls['images']}/{img_node.id}"
            img_details = common_util.http_get_request(img_meta_url,
                                                         self._headers, self.verify_ssl)
            img_node.set_markdown_content(img_details.json())
            if not img_node.markdown_str:
                continue
            # 1 - what to replace, 2 - replace with, 3 is the data to replace
            page_data = re.sub(img_node.markdown_str.encode(),
                               img_node.get_image_relative_path(page_name).encode(), page_data)
        return page_data

    @property
    def file_extension_map(self) -> Dict[str, str]:
        """file extension metadata"""
        return _FILE_EXTENSION_MAP

    @property
    def export_images(self) -> bool:
        """return whether or not to export images"""
        return self.asset_config.export_images

    @property
    def verify_ssl(self) -> bool:
        """return whether or not to verify ssl for http requests"""
        return self.asset_config.verify_ssl

    # @staticmethod
    # def _get_regex_expr(url: str) -> bytes:
    #     # regex_str = fr"\[\!\[^$|.*\]\({url}\)\]"
    #     return re.compile(regex_str.encode())

    @staticmethod
    def _create_image_map(json_data: List[Dict[str, Union[str,int]]]) -> Dict[int, List[ImageNode]]:
        image_page_map = {}
        for img_meta in json_data:
            img_node = ImageNode(img_meta)
            if img_node.page_id in image_page_map:
                image_page_map[img_node.page_id].append(img_node)
            else:
                image_page_map[img_node.page_id] = [img_node]
        return image_page_map
