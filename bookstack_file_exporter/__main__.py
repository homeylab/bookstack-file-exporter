import argparse
import logging
import sys

from bookstack_file_exporter import run
from bookstack_file_exporter import run_args
from bookstack_file_exporter.common import logging as bfe_logging


def main() -> int:
    """run entrypoint"""
    args: argparse.Namespace = run_args.get_args()
    logging.basicConfig(
        level=run_args.get_log_level(args.log_level),
        handlers=[bfe_logging.build_handler(run_args.resolve_log_format(args))])
    return run.entrypoint(args)


if __name__ == '__main__':
    sys.exit(main())
