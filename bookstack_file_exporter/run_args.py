import argparse
from typing import Dict, List
import logging

LOG_LEVEL = {
    'debug': logging.DEBUG,
    'info': logging.INFO,
    'warning': logging.WARNING,
    'error': logging.ERROR
}

# Characters in filenames to be replaced with "_"

class InvalidArgument(Exception):
    """ Use this when an argument is not valid """
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


def get_log_level(log_level:str) -> int:
    return LOG_LEVEL.get(log_level)

def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='BookStack File Exporter')
    parser.add_argument('-c',
                    '--config-file',
                    type=str,
                    default="",
                    help='Provide a configuration file (full or relative path). See README for more details')
    parser.add_argument('-v',
                    '--log-level',
                    type=str.lower,
                    default='info',
                    help='Set verbosity level for logging.',
                    choices=LOG_LEVEL.keys())
    return parser.parse_args()