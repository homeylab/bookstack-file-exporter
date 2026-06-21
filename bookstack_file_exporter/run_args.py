import argparse
import logging
import os

log = logging.getLogger(__name__)

LOG_LEVEL = {
    'debug': logging.DEBUG,
    'info': logging.INFO,
    'warning': logging.WARNING,
    'error': logging.ERROR
}

LOG_FORMAT = ("text", "json")
_LOG_FORMAT_ENV = "LOG_FORMAT"


def get_log_level(log_level:str) -> int:
    """return log level int"""
    return LOG_LEVEL[log_level]

def get_args(argv=None) -> argparse.Namespace:
    """return user cmd line options (argv=None -> sys.argv)"""
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
    parser.add_argument('--run-once',
                    action='store_true',
                    default=False,
                    help=('Force a single run and exit regardless of'
                          ' run_interval/run_schedule in config.'))
    parser.add_argument('--log-format',
                    type=str.lower,
                    default=None,
                    help=('Log output format. CLI overrides the LOG_FORMAT'
                          ' env var; default text.'),
                    choices=LOG_FORMAT)
    return parser.parse_args(argv)


def resolve_log_format(args: argparse.Namespace) -> str:
    """Resolve log format: CLI flag, else LOG_FORMAT env, else text.

    An invalid env value falls back to text (does not crash a container).
    """
    if args.log_format is not None:
        return args.log_format  # argparse `choices` already validated this
    env_val = os.environ.get(_LOG_FORMAT_ENV)
    if env_val is None:
        return "text"
    env_val = env_val.lower()
    if env_val in LOG_FORMAT:
        return env_val
    log.warning("Invalid %s '%s'; supported: text (default), json. Using text.",
                _LOG_FORMAT_ENV, env_val)
    return "text"
