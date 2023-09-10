import argparse
import os
import logging

from bookstack_file_exporter.config_helper.config_helper import ConfigNode

log = logging.getLogger(__name__)

def test(args: argparse.Namespace, token_id_env: str, token_key_env: str):
    config: ConfigNode = ConfigNode(args)
    config.token_id: str = os.environ.get(token_id_env, "")
    config.token_key: str = os.environ.get(token_key_env, "")

    log.info(config)
    log.info(config.user_inputs)
    log.info(config.headers)
