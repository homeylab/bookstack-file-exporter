import os
import argparse
import logging
# pylint: disable=import-error
import yaml
from minio.credentials import (
    Provider, StaticProvider, ChainedProvider,
    EnvAWSProvider, IamAwsProvider, EnvMinioProvider,
)

from bookstack_file_exporter.common.util import check_var
from bookstack_file_exporter.config_helper import models
from bookstack_file_exporter.config_helper.remote import (
    StorageProviderConfig,
    aws_endpoint_from_region,
)

log = logging.getLogger(__name__)


def load_yaml_config(path: str) -> dict:
    """File I/O + safe_load. Raises FileNotFoundError / yaml.YAMLError."""
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    with open(path, encoding="utf-8") as yaml_stream:
        try:
            data = yaml.safe_load(yaml_stream)
        except yaml.YAMLError:
            log.error("Failed to load yaml configuration file")
            raise
    if data is None:                       # empty / whitespace-only file
        raise ValueError(f"Config file is empty or has no YAML content: {path}")
    return data


def build_user_input(raw: dict) -> models.UserInput:
    """Pydantic validation. Deprecated/removed-key handling lives in the models
    (Assets/UserInput before-validators). Returns models.UserInput."""
    try:
        return models.UserInput(**raw)
    except Exception:
        log.error("Yaml configuration failed schema validation")
        raise


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


def _resolve_credentials(entry: models.BaseStorageConfig) -> Provider:
    """Resolve one entry's credentials to a minio-py Provider (first match wins):

    1. per-entry env NAMES (access_key_env/secret_key_env) -> StaticProvider. Only scheme
       that supports two same-type targets with distinct out-of-file creds.
    2. standard env vars (MINIO_ACCESS_KEY/MINIO_SECRET_KEY for minio; AWS_ACCESS_KEY_ID/
       AWS_SECRET_ACCESS_KEY for s3) — checked before inline config-file keys.
    3. inline access_key/secret_key (config-file fallback).
    4. type s3 only — IMDS / EC2-ECS IAM role (no secrets in config/env/files).
    """
    if entry.access_key_env and entry.secret_key_env:
        access = os.environ.get(entry.access_key_env)
        secret = os.environ.get(entry.secret_key_env)
        if not access or not secret:
            raise ValueError(
                f"credential env vars {entry.access_key_env}/{entry.secret_key_env} "
                "are referenced but not set or empty")
        return StaticProvider(access, secret)

    # inline keys, when present, sit BELOW the standard env vars (env > config file)
    inline = (StaticProvider(entry.access_key, entry.secret_key)
              if entry.access_key and entry.secret_key else None)

    if entry.type == "s3":
        # env > inline > IMDS (EC2/ECS IAM role). No ~/.aws file tier and no static
        # creds required: a role can supply them at runtime.
        if inline:
            return ChainedProvider([EnvAWSProvider(), inline, IamAwsProvider()])
        return ChainedProvider([EnvAWSProvider(), IamAwsProvider()])

    # minio: env > inline (no file tier; minio has no IMDS equivalent)
    if inline:
        return ChainedProvider([EnvMinioProvider(), inline])
    return EnvMinioProvider()


def _resolve_endpoint(entry: models.BaseStorageConfig) -> str:
    """Connection host for an entry: explicit host wins; else s3 defaults from region."""
    if entry.host:
        return entry.host
    if entry.type == "s3" and entry.region:
        return aws_endpoint_from_region(entry.region)
    return ""


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
        return build_user_input(load_yaml_config(config_file))

    def _generate_credentials(self) -> tuple[str, str]:
        # if user provided credentials in config file, load them
        token_id = self.user_inputs.credentials.token_id
        token_secret = self.user_inputs.credentials.token_secret

        # check to see if env var is specified, if so, it takes precedence
        token_id = check_var(_BOOKSTACK_TOKEN_FIELD, token_id)
        token_secret = check_var(_BOOKSTACK_TOKEN_SECRET_FIELD, token_secret)
        return token_id, token_secret

    def _generate_remote_config(self) -> list[StorageProviderConfig]:
        configs: list[StorageProviderConfig] = []
        if not self.user_inputs.object_storage:
            return configs
        for entry in self.user_inputs.object_storage:
            provider_config = StorageProviderConfig(
                storage_type=entry.type,
                endpoint=_resolve_endpoint(entry),
                secure=entry.secure,
                credentials=_resolve_credentials(entry),
                config=entry,
            )
            if not provider_config.is_valid():
                raise ValueError(f"provided {entry.type} configuration is invalid")
            configs.append(provider_config)
        return configs

    def _generate_headers(self) -> dict[str, str]:
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

    def _generate_urls(self) -> dict[str, str]:
        urls = {}
        # remove trailing slash
        host = self.user_inputs.host.rstrip('/')
        # check to see if http protocol is defined (scheme prefix, not substring:
        # a host like 'myhttphost.local' must still get the https:// default)
        if not host.startswith(("http://", "https://")):
            # use https by default
            url_prefix = "https://"
        else:
            url_prefix = ""
        for key, value in _API_PATHS.items():
            urls[key] = f"{url_prefix}{host}/{value}"
        log.debug("api urls: %s", urls)
        return urls

    def _set_base_dir(self, cmd_output_dir: str) -> str:
        output_dir = cmd_output_dir or self.user_inputs.output_path
        if cmd_output_dir:
            log.debug("Output directory overwritten by command line option")
        if not output_dir:
            return _BASE_DIR_NAME
        return f"{output_dir.rstrip('/')}/{_BASE_DIR_NAME}"

    @property
    def headers(self) -> dict[str, str]:
        """get generated headers"""
        return self._headers

    @property
    def urls(self) -> dict[str, str]:
        """get generated urls"""
        return self._urls

    @property
    def base_dir_name(self) -> str:
        """get base dir of output target"""
        return self._base_dir_name

    @property
    def object_storage_config(self) -> list[StorageProviderConfig]:
        """return list of resolved remote storage targets"""
        return self._object_storage_config
