import argparse
import logging

LOG_LEVEL = {
    'debug': logging.DEBUG,
    'info': logging.INFO,
    'warning': logging.WARNING,
    'error': logging.ERROR
}

def get_log_level(log_level:str) -> int:
    """return log level int"""
    return LOG_LEVEL.get(log_level)

def get_args() -> argparse.Namespace:
    """return user cmd line options"""
    parser = argparse.ArgumentParser(description='BookStack File Exporter')
    parser.add_argument('-c',
                    '--config-file',
                    type=str,
                    default="data/config.yml",
                    help='''Provide a configuration file (full or relative path).
                     See README for more details''')
    parser.add_argument('-o',
                    '--output-dir',
                    type=str,
                    default="",
                    help='''Optional, specify an output directory.
                     This can also be specified in the config.yml file''')
    parser.add_argument('-v',
                    '--log-level',
                    type=str.lower,
                    default='info',
                    help='Set verbosity level for logging.',
                    choices=LOG_LEVEL.keys())
    return parser.parse_args()
