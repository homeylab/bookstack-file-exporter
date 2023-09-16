import os
import json
import argparse
import yaml
import logging
from typing import Dict, Literal, List, Optional
from pydantic import BaseModel

log = logging.getLogger(__name__)

class UserInput(BaseModel):
    host: str
    additional_headers: Optional[Dict[str, str]] = None
    formats: List[Literal["markdown", "html", "pdf", "plaintext"]]
    outputs: List[Literal["local", "minio"]]
    output_path: Optional[str] = None
    export_meta: Optional[bool] = True # set a default

DEFAULT_HEADERS = {
    'Content-Type': 'application/json; charset=utf-8'
}

API_PATHS = {
    "shelves": "api/shelves",
    "books": "api/books",
    "chapters": "api/chapters",
    "pages": "api/pages"
}

UNASSIGNED_BOOKS_DIR = "unassigned/"

BASE_DIR_NAME = "bookstack_export"

## Normalize config from cli or from config file
class ConfigNode:
    """
    Get Run Configuration from CLI or file and normalize the data in an accessible object

    Args:
        Arg parse from user input

    Returns:
        ConfigNode object with attributes that are accessible for use for further downstream processes

    Raises:
        YAMLError: if provided configuration file is not valid YAML

        ValueError: if improper arguments are given from user
    """
    def __init__(self, args: argparse.Namespace):
        self.user_inputs = {}
        self.unassigned_book_dir = UNASSIGNED_BOOKS_DIR
        self._base_dir_name = ""
        self._headers = {}
        self._urls = {}
        self._token_secret = ""
        self._token_id = ""
        self._initialize(args)

    
    def _initialize(self, args: argparse.Namespace):
        # Check to see if config_file is provided
        if args.config_file:
            self._validate_config(args.config_file)
        # generate headers
        self._default_headers()
        # generate url for requests
        self._generate_urls()
        # set base dir for exports
        self._set_base_dir()

    def _validate_config(self, config_file: str):
        if not os.path.isfile(config_file):
            raise FileNotFoundError(config_file)
        with open(config_file, "r") as yaml_stream:
            try:
                yaml_input = yaml.safe_load(yaml_stream)
            except Exception as load_err:
                # log here to make it easier to identify the issue
                log.error("Failed to load yaml configuration file")
                raise load_err
        try:
            self.user_inputs = UserInput(**yaml_input)
        except Exception as err:
            # log here to make it easier to identify the issue
            log.error("Yaml configuration failed schema validation")
            raise err

    def _default_headers(self):
        # add default headers
        for key, value in DEFAULT_HEADERS.items():
            if key not in self.user_inputs.additional_headers:
                self._headers[key] = value
        
        # add additional_headers provided by user
        if self.user_inputs.additional_headers:
            for key, value in self.user_inputs.additional_headers.items():
                self._headers[key] = value

    def _generate_urls(self):
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
        for key, value in API_PATHS.items():
            self._urls[key] = url_prefix + self.user_inputs.host + '/' + value

    # used to add/update token key
    def _add_auth_header(self):
        # do not override user provided one
        if 'Authorization' not in self._headers:
            self._headers['Authorization'] = f"Token {self._token_id}:{self._token_secret}"

    def _set_base_dir(self):
        # strip slash if present
        output_dir = self.user_inputs.output_path
        if output_dir[-1] == '/':
            output_dir = output_dir[:-1]
        print(output_dir)
        self._base_dir_name = output_dir +  "/" + BASE_DIR_NAME
        

    @property
    def token_secret(self) -> str:
        return self._token_secret
    
    @token_secret.setter
    def token_secret(self, value: str):
        # just a check to ensure it has some value
        if not value:
            raise ValueError("BOOKSTACK_TOKEN_SECRET is not specified in env")
        self._token_secret = value
        # # update auth in header
        # self._add_auth_header()

    @property
    def token_id(self) -> str:
        return self._token_id
    
    @token_id.setter
    def token_id(self, value: str):
        # just a check to ensure it has some value
        if not value:
            raise ValueError("BOOKSTACK_TOKEN_ID is not specified in env")
        self._token_id = value
    
    @property
    def headers(self) -> Dict[str, str]:
        self._add_auth_header()
        return self._headers

    @property
    def urls(self) -> Dict[str, str]:
        return self._urls
    
    @property
    def base_dir_name(self) -> str:
        return self._base_dir_name