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
# _MARKDOWN_IMAGE_REGEX= re.compile(r"\[\!\[^$|.*\].*\]")
_MARKDOWN_STR_CHECK = "markdown"

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
        # parent export directory, bookstack-<timestamp>, and .tgz extension
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
            self._archive_page_meta(page.name, page.file_path, page.meta)

    def _archive_page(self, page: Node, export_format: str, data: bytes,
                      image_urls: List[str] = None):
        page_file_name = f"{self.archive_base_path}/" \
            f"{page.file_path}/{page.name}{_FILE_EXTENSION_MAP[export_format]}"

        if export_format == _MARKDOWN_STR_CHECK and image_urls and self.modify_md:
            data = self._update_image_links(data, image_urls)
        self.write_data(page_file_name, data)

    def _get_page_data(self, page_id: int, export_format: str):
        url = f"{self.api_urls['pages']}/{page_id}/{_EXPORT_API_PATH}/{export_format}"
        return archiver_util.get_byte_response(url=url, headers=self._headers,
                                               verify_ssl=self.verify_ssl)

    def _archive_page_meta(self, page_name: str, page_path: str,
                           meta_data: Dict[str, Union[str, int]]):
        meta_file_name = f"{self.archive_base_path}/{page_path}/" \
            f"{page_name}{_FILE_EXTENSION_MAP['meta']}"
        bytes_meta = archiver_util.get_json_bytes(meta_data)
        self.write_data(file_path=meta_file_name, data=bytes_meta)

    def get_image_meta(self) -> Dict[int, List[str]]:
        """Get all image metadata into a {page_number: [image_url]} format"""
        img_meta_response: Response = common_util.http_get_request(
            self.api_urls['images'],
            self._headers,
            self.verify_ssl)
        img_meta_json = img_meta_response.json()['data']
        return self._create_image_map(img_meta_json)

    @staticmethod
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

    def archive_page_images(self, page_path: str, image_urls: List[str]):
        """pull images locally into a directory based on page"""
        # image_base_path = f"{self.archive_base_path}/{page_path}{_IMAGE_DIR_SUFFIX}"
        image_base_path = f"{self.archive_base_path}/{page_path}/{_IMAGE_DIR_NAME}"
        for image_url in image_urls:
            img_data: bytes = archiver_util.get_byte_response(image_url, self._headers,
                                                              self.verify_ssl)
            # seems safer to use this instead of image['name'] field
            img_file_name = image_url.split('/')[-1]
            image_path = f"{image_base_path}/{img_file_name}"
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

    def _update_image_links(self, page_data: bytes, urls: List[str]) -> bytes:
        """regex replace links to local created directories"""
        # 1 - what to replace, 2 - replace with, 3 is the data to replace
        # re.sub(b'pfsense', b'lol', x.content)

        # string to bytes
        # >>> k = 'lol'
        # >>> k.encode()
        pass

    def _valid_image_link(self):
        """should contain bookstack host"""
        pass

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

    @staticmethod
    def _get_regex_expr(url: str) -> re.Pattern:
        return re.compile(fr"\[\!\[^$|.*\].*{url}.*\]")
