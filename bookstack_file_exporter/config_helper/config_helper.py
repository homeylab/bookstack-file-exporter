import os
import json
import argparse
import yaml
import logging
from typing import Dict, Literal, List, Optional
from pydantic import BaseModel, ValidationError

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

# LEVELS = ['pages', 'chapters', 'books']

# FORBIDDEN_CHARS = ["/"]

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
        # user inputs
        # self._user_inputs: Dict[str, Union[List, str, bool]] = {}
        self.user_inputs = {}
        self._headers = {}
        self.url = ""

        self.fs_path = ""
        self.api_prefix = ""
        
        self._token_secret = ""
        self._token_id = ""
        self._token_auth = ""
        self._initialize(args)

    
    def _initialize(self, args: argparse.Namespace):
        ## Check to see if config_file is provided
        if args.config_file:
            self._validate_config(args.config_file)
        # generate headers
        self._default_headers()
        # generate url for requests

    # def _intake_file(self, config_file: str):
    #     ## To do add a schema check for yaml conf file
    #     with open(config_file, "r") as yaml_stream:
    #         try:
    #             yaml_input = yaml.safe_load(yaml_stream) # dict type
    #         except yaml.YAMLError as yaml_err:
    #             raise yaml_err
        

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
        
        # add additional_headers and let it override defaults
        if self.user_inputs.additional_headers:
            for key, value in self.user_inputs.additional_headers.items():
                self._headers[key] = value

    # used to add/update token key
    def _add_auth_header(self):
        # do not override user provided one
        if 'Authorization' not in self._headers:
            self._headers['Authorization'] = f"Token {self._token_auth}"

    @property
    def token_auth(self) -> str:
        return self._token_auth
    
    @token_auth.setter
    def token_auth(self, token_id: str, token_secret: str):
        # just a check to ensure it has some value
        if not token_id:
            raise ValueError("BOOKSTACK_TOKEN_ID is not specified in env")
        if not token_secret:
            raise ValueError("BOOKSTACK_TOKEN_SECRET is not specified in env")
        # update auth in header
        self._token_auth = f"{token_id}:{token_secret}"
        self._add_auth_header()

    @property
    def token_secret(self) -> str:
        return self._token_secret
    
    @token_secret.setter
    def token_secret(self, value: str):
        # just a check to ensure it has some value
        if not value:
            raise ValueError("BOOKSTACK_TOKEN_SECRET is not specified in env")
        # update auth in header
        self._add_auth_header(value)
        self._token_secret = value

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
        return self._headers