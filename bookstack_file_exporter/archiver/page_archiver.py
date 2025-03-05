from typing import Union, List, Dict
import logging
# pylint: disable=import-error
from requests.exceptions import HTTPError
from bookstack_file_exporter.exporter.node import Node
from bookstack_file_exporter.archiver import util as archiver_util
from bookstack_file_exporter.archiver.asset_archiver import AssetArchiver, ImageNode, AttachmentNode
from bookstack_file_exporter.config_helper.config_helper import ConfigNode
from bookstack_file_exporter.common.util import HttpHelper

log = logging.getLogger(__name__)

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

# pylint: disable=too-many-instance-attributes
class PageArchiver:
    """
    PageArchiver handles all data extraction and modifications 
    to Bookstack page contents including assets like images or attachments.

    Args:
        :archive_dir: <str> = directory where data will be put into.
        :config: <ConfigNode> = Configuration with user inputs and general options.
        :http_client: <HttpHelper> = http helper functions with config from user inputs

    Returns:
        :PageArchiver: instance with methods to help collect page content from a Bookstack instance.
    """
    def __init__(self, archive_dir: str, config: ConfigNode, http_client: HttpHelper) -> None:
        self.asset_config = config.user_inputs.assets
        self.export_formats = config.user_inputs.formats
        self.api_urls = config.urls
        # full path, bookstack-<timestamp>, and .tgz extension
        self.archive_file = f"{archive_dir}{_FILE_EXTENSION_MAP['tgz']}"
        # name of intermediate tar file before gzip
        self.tar_file = f"{archive_dir}{_FILE_EXTENSION_MAP['tar']}"
        # name of the base folder to use within the tgz archive (internal tar layout)
        self.archive_base_path = archive_dir.split("/")[-1]
        self.modify_md: bool = self._check_md_modify()
        self.asset_archiver = AssetArchiver(self.api_urls,
                                            http_client)
        self.http_client = http_client

    def _check_md_modify(self) -> bool:
        # check to ensure they have asset_config defined, could be None
        if 'markdown' in self.export_formats:
            return self.asset_config.modify_markdown and \
                ( self.export_images or self.export_attachments)
        return False

    def archive_pages(self, page_nodes: Dict[int, Node]):
        """export page contents and their images/attachments"""
        # get assets first if requested
        # this is because we may want to manipulate page data with modify_markdown flag
        image_nodes = self._get_image_meta()
        attachment_nodes = self._get_attachment_meta()
        for _, page in page_nodes.items():
            page_images = []
            page_attachments = []
            if page.id_ in image_nodes:
                page_images = image_nodes[page.id_]
            if page.id_ in attachment_nodes:
                page_attachments = attachment_nodes[page.id_]
            failed_images = self.archive_page_assets("images", page.parent.file_path,
                                     page.name, page_images)
            failed_attach = self.archive_page_assets("attachments", page.parent.file_path,
                                     page.name, page_attachments)
            # exclude from page_images
            # so it doesn't attempt to get modified in markdown file
            if failed_images:
                page_images = [img for img in page_images if img.id_ not in failed_images]
            # exclude from page_attachments
            # so it doesn't attempt to get modified in markdown file
            if failed_attach:
                page_attachments = [attach for attach in page_attachments
                                    if attach.id_ not in failed_attach]
            for export_format in self.export_formats:
                page_data = self._get_page_data(page.id_, export_format)
                if page_images and export_format == 'markdown':
                    page_data = self._modify_markdown("images", page.name,
                                                      page_data, page_images)
                if page_attachments and export_format == 'markdown':
                    page_data = self._modify_markdown("attachments", page.name,
                                                      page_data, page_attachments)
                self._archive_page(page, export_format,
                                    page_data)
            if self.asset_config.export_meta:
                self._archive_page_meta(page.file_path, page.meta)

    def _archive_page(self, page: Node, export_format: str, data: bytes):
        page_file_name = f"{self.archive_base_path}/" \
            f"{page.file_path}{_FILE_EXTENSION_MAP[export_format]}"
        self.write_data(page_file_name, data)

    def _get_page_data(self, page_id: int, export_format: str) -> bytes:
        url = f"{self.api_urls['pages']}/{page_id}/{_EXPORT_API_PATH}/{export_format}"
        return archiver_util.get_byte_response(url=url,
                                               http_client=self.http_client)

    def _archive_page_meta(self, page_path: str, meta_data: Dict[str, Union[str, int]]):
        meta_file_name = f"{self.archive_base_path}/{page_path}{_FILE_EXTENSION_MAP['meta']}"
        bytes_meta = archiver_util.get_json_bytes(meta_data)
        self.write_data(file_path=meta_file_name, data=bytes_meta)

    def _get_image_meta(self) -> Dict[int, List[ImageNode]]:
        """Get all image metadata into a {page_number: [image_url]} format"""
        if not self.asset_config.export_images:
            return {}
        return self.asset_archiver.get_asset_nodes('images')

    def _get_attachment_meta(self) -> Dict[int, List[AttachmentNode]]:
        """Get all attachment metadata into a {page_number: [attachment_url]} format"""
        if not self.asset_config.export_attachments:
            return {}
        return self.asset_archiver.get_asset_nodes('attachments')

    def _modify_markdown(self, asset_type: str,
                         page_name: str, page_data: bytes,
                         asset_nodes: List[ImageNode | AttachmentNode]) -> bytes:
        if not self.modify_md:
            return page_data
        return self.asset_archiver.update_asset_links(asset_type, page_name, page_data,
                                        asset_nodes)

    def archive_page_assets(self, asset_type: str, parent_path: str, page_name: str,
                            asset_nodes: List[ImageNode | AttachmentNode]) -> Dict[int, int]:
        """pull images locally into a directory based on page"""
        if not asset_nodes:
            return {}
        # use a map for faster lookup
        failed_assets = {}
        node_base_path = f"{self.archive_base_path}/{parent_path}"
        for asset_node in asset_nodes:
            try:
                asset_data = self.asset_archiver.get_asset_bytes(asset_type, asset_node.url)
            except HTTPError:
                # probably unnecessary, but just in case
                if asset_node.id_ not in failed_assets:
                    failed_assets[asset_node.id_] = 0
                # a 404 or other error occurred
                # skip this asset
                log.error("Failed to get image or attachment data " \
                          "for asset located at: %s - skipping", asset_node.url)
                continue
            asset_path = f"{node_base_path}/{asset_node.get_relative_path(page_name)}"
            self.write_data(asset_path, asset_data)
        return failed_assets

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

    @property
    def file_extension_map(self) -> Dict[str, str]:
        """file extension metadata"""
        return _FILE_EXTENSION_MAP

    @property
    def export_images(self) -> bool:
        """return whether or not to export images"""
        return self.asset_config.export_images

    @property
    def export_attachments(self) -> bool:
        """return whether or not to export attachments"""
        return self.asset_config.export_attachments

    @property
    def verify_ssl(self) -> bool:
        """return whether or not to verify ssl for http requests"""
        return self.asset_config.verify_ssl
