import argparse
import logging
from typing import Dict, List, Union

from bookstack_file_exporter import run
from bookstack_file_exporter import pre_check
from bookstack_file_exporter import run_args

# # (formatName, fileExtension)
# FORMATS: Dict['str', 'str'] = {
#     'markdown': 'md',
#     'plaintext': 'txt',
#     'pdf': 'pdf',
#     'html': 'html'
# }

# LOG_LEVEL: Dict = {
#     'debug': logging.DEBUG,
#     'info': logging.INFO,
#     'warning': logging.WARNING,
#     'error': logging.ERROR
# }

# # Characters in filenames to be replaced with "_"
# FORBIDDEN_CHARS: List[str] = ["/", "#"]

TOKEN_FIELD ='BOOKSTACK_TOKEN_ID'
TOKEN_KEY_FIELD='BOOKSTACK_TOKEN_KEY'

def main():
    # fail fast if credentials aren't there and exit quickly
    pre_check.ensure_credentials(TOKEN_FIELD, TOKEN_KEY_FIELD)

    args: argparse.Namespace = run_args.get_args()

    logging.basicConfig(format='%(asctime)s [%(levelname)s] %(message)s',
                    level=run_args.get_log_level(args.log_level), datefmt='%Y-%m-%d %H:%M:%S')
    
    run.test(args, TOKEN_FIELD, TOKEN_KEY_FIELD)


if __name__ == '__main__':
    main()