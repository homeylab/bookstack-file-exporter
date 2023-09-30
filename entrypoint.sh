#!/usr/bin/env bash

# set log level default
if [[ -z "${LOG_LEVEL}" ]]; then
    RUN_LOG_LEVEL="info"
else
    # if user supplied log level as env var, use that
    RUN_LOG_LEVEL=$LOG_LEVEL
fi

python -m bookstack_file_exporter -c $DOCKER_CONFIG_DIR/config.yml -o $DOCKER_EXPORT_DIR -v $RUN_LOG_LEVEL