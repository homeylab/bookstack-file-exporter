import os
import argparse
from typing import Dict, Tuple
import logging
# pylint: disable=import-error
import yaml

from bookstack_file_exporter.config_helper import models
from bookstack_file_exporter.config_helper.remote import StorageProviderConfig

log = logging.getLogger(__name__)

_DEFAULT_HEADERS = {
    'Content-Type': 'application/json; charset=utf-8'
}

_API_PATHS = {
    "shelves": "api/shelves",
    "books": "api/books",
    "chapters": "api/chapters",
    "pages": "api/pages",
    "images": "api/image-gallery",
    "attachments": "api/attachments"
}

_UNASSIGNED_BOOKS_DIR = "unassigned/"

_BASE_DIR_NAME = "bookstack_export"

_BOOKSTACK_TOKEN_FIELD ='BOOKSTACK_TOKEN_ID'
_BOOKSTACK_TOKEN_SECRET_FIELD='BOOKSTACK_TOKEN_SECRET'
_MINIO_ACCESS_KEY_FIELD='MINIO_ACCESS_KEY'
_MINIO_SECRET_KEY_FIELD='MINIO_SECRET_KEY'

# pylint: disable=too-many-instance-attributes
## Normalize config from cli or from config file
class ConfigNode:
    """
    Get Run Configuration from YAML file and normalize the data in an accessible object

    Args:
        Arg parse from user input

    Returns:
        ConfigNode object with attributes that are 
        accessible for use for further downstream processes

    Raises:
        YAMLError: if provided configuration file is not valid YAML

        ValueError: if improper arguments are given from user
    """
    def __init__(self, args: argparse.Namespace):
        self.unassigned_book_dir = _UNASSIGNED_BOOKS_DIR
        self.user_inputs = self._generate_config(args.config_file)
        self._base_dir_name = self._set_base_dir(args.output_dir)
        self._token_id, self._token_secret = self._generate_credentials()
        self._headers = self._generate_headers()
        self._urls = self._generate_urls()
        self._object_storage_config = self._generate_remote_config()

    def _generate_config(self, config_file: str) -> models.UserInput:
        if not os.path.isfile(config_file):
            raise FileNotFoundError(config_file)
        with open(config_file, "r", encoding="utf-8") as yaml_stream:
            try:
                yaml_input = yaml.safe_load(yaml_stream)
            except Exception as load_err:
                # log here to make it easier to identify the issue
                log.error("Failed to load yaml configuration file")
                raise load_err
        try:
            user_inputs = models.UserInput(**yaml_input)
        except Exception as err:
            # log here to make it easier to identify the issue
            log.error("Yaml configuration failed schema validation")
            raise err
        return user_inputs

    def _generate_credentials(self) -> Tuple[str, str]:
        # if user provided credentials in config file, load them
        token_id = self.user_inputs.credentials.token_id
        token_secret = self.user_inputs.credentials.token_secret

        # check to see if env var is specified, if so, it takes precedence
        token_id = self._check_var(_BOOKSTACK_TOKEN_FIELD, token_id)
        token_secret = self._check_var(_BOOKSTACK_TOKEN_SECRET_FIELD, token_secret)
        return token_id, token_secret

    def _generate_remote_config(self) -> Dict[str, StorageProviderConfig]:
        object_config = {}
        # check for optional minio credentials if configuration is set in yaml configuration file
        if self.user_inputs.minio:
            minio_access_key = self._check_var(_MINIO_ACCESS_KEY_FIELD,
                                               self.user_inputs.minio.access_key)
            minio_secret_key = self._check_var(_MINIO_SECRET_KEY_FIELD,
                                               self.user_inputs.minio.secret_key)

            object_config["minio"] = StorageProviderConfig(minio_access_key,
                                     minio_secret_key, self.user_inputs.minio)
        for platform, config in object_config.items():
            if not config.is_valid(platform):
                error_str = "provided " + platform + " configuration is invalid"
                raise ValueError(error_str)
        return object_config

    def _generate_headers(self) -> Dict[str, str]:
        headers = {}
        # add additional_headers provided by user
        if self.user_inputs.http_config.additional_headers:
            for key, value in self.user_inputs.http_config.additional_headers.items():
                headers[key] = value

        # add default headers
        for key, value in _DEFAULT_HEADERS.items():
            # do not override if user added one already with same key
            if key not in headers:
                headers[key] = value

        # do not override user provided one
        if 'Authorization' not in headers:
            headers['Authorization'] = f"Token {self._token_id}:{self._token_secret}"
        return headers

    def _generate_urls(self) -> Dict[str, str]:
        urls = {}
        # remove trailing slash
        host = self.user_inputs.host
        if host[-1] == '/':
            host = host[:-1]
        # check to see if http protocol is defined
        if "http" not in self.user_inputs.host:
            # use https by default
            url_prefix = "https://"
        else:
            url_prefix = ""
        for key, value in _API_PATHS.items():
            urls[key] = f"{url_prefix}{self.user_inputs.host}/{value}"
        log.debug("api urls: %s", urls)
        return urls

    def _set_base_dir(self, cmd_output_dir: str) -> str:
        output_dir = self.user_inputs.output_path
        # override if command line specified
        if cmd_output_dir:
            log.debug("Output directory overwritten by command line option")
            output_dir = cmd_output_dir
        # check if user provided an output path
        if output_dir:
            # detect trailing slash
            # normalize to no trailing slash for later consistency
            if output_dir[-1] == '/':
                base_dir = f"{output_dir}{_BASE_DIR_NAME}"
            else:
                base_dir = f"{output_dir}/{_BASE_DIR_NAME}"
        else:
            base_dir = _BASE_DIR_NAME
        return base_dir

    @property
    def headers(self) -> Dict[str, str]:
        """get generated headers"""
        return self._headers

    @property
    def urls(self) -> Dict[str, str]:
        """get generated urls"""
        return self._urls

    @property
    def base_dir_name(self) -> str:
        """get base dir of output target"""
        return self._base_dir_name

    @property
    def object_storage_config(self) -> Dict[str, StorageProviderConfig]:
        """return remote storage configuration"""
        return self._object_storage_config

    @staticmethod
    def _check_var(env_key: str, default_val: str) -> str:
        """
        :param: env_key = the environment variable to check
        :param: default_val = the default value if any to set if env variable not set
        
        :return: env_key if present or default_val if not
        :throws: ValueError if both parameters are empty.
        """
        env_value = os.environ.get(env_key, "")
        # env value takes precedence
        if env_value:
            log.debug("""env key: %s specified.
                       Will override configuration file value if set.""", env_key)
            return env_value
        # check for optional inputs, if env and input is missing
        if not env_value and not default_val:
            raise ValueError(f"""{env_key} is not specified in env and is
                              missing from configuration - at least one should be set""")
        # fall back to configuration file value if present
        return default_val
