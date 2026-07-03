#!/usr/bin/env bash

# LOG_LEVEL is not forwarded via -v: the app reads the env var itself and
# falls back gracefully on an invalid value, while argparse's `choices` would
# hard-exit (SystemExit 2) instead.
exec python -m bookstack_file_exporter -c "$DOCKER_CONFIG_DIR/config.yml" -o "$DOCKER_EXPORT_DIR"