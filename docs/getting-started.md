# Getting Started

[← Back to README](../README.md#documentation)

- [Using This Application](#using-this-application)
- [Run via Pip](#run-via-pip)
  - [Python Version](#python-version)
  - [Examples](#examples)
- [Run via Docker](#run-via-docker)
  - [Tags](#tags)
  - [Examples](#examples-1)
  - [Docker Compose](#docker-compose)
- [Run via Helm](#run-via-helm)
- [Options](#options)
- [Environment Variables](#environment-variables)
- [Authentication and Permissions](#authentication-and-permissions)
  - [Permissions](#permissions)
  - [Token Authentication](#token-authentication)
- [Operations](#operations)

## Using This Application
Ensure a valid configuration is provided when running this application. See [Configuration](configuration.md#configuration) section for more details.

Simple example configuration:
```yaml
# config.yml
host: "https://bookstack.yourdomain.com"
credentials:
  token_id: ""
  token_secret: ""
formats: # md only example
- markdown
# - html
# - pdf
# - plaintext
# - zip
output_path: "bkps/"
assets:
  export_images: false
  export_attachments: false
  modify_links: false
  export_meta: false
```

## Run via Pip
The exporter can be installed via pip (or [uv](https://docs.astral.sh/uv/)) and run directly.

### Python Version
_Note: This application is tested and developed on Python version `3.14.5`. The min required version is >= `3.11` but is recommended to install (or set up a venv) a `3.14.5` version._

### Examples
```bash
python -m pip install bookstack-file-exporter

# or with uv:
uv pip install bookstack-file-exporter

# if you prefer a specific version, example:
python -m pip install bookstack-file-exporter==X.X.X

# using pip
python -m bookstack_file_exporter -c <path_to_config_file>

# if you already have python bin directory in your path
bookstack-file-exporter -c <path_to_config_file>
```

## Run via Docker
Docker images are provided for `linux/amd64` and `linux/arm64` variants only at the moment. If another variant is required, please request it via Github Issue.

### Tags
Users will generally want to use the `latest` tag or a specific version tag. The `main` tag is also provided but is not guaranteed to be stable.

| tag | description |
| --- | ----------- |
| `latest` | Latest stable release and is updated with each new stable release. |
| `X.X.X`  | Semantic versioned releases are also provided if preferred for stability or other reasons. |
| `main` | This tag reflects the `main` branch of this repository and may not be stable |

### Examples
```bash
# --user flag to override the uid/gid for created files. Set this to your uid/gid
docker run \
    --user ${USER_ID}:${USER_GID} \
    -v $(pwd)/config.yml:/export/config/config.yml:ro \
    -v $(pwd)/bkps:/export/dump \
    homeylab/bookstack-file-exporter:latest
```

Minimal example with object storage upload. A temporary filesystem will be used so archive will not be persistent locally.

```bash
docker run \
    -v $(pwd)/config.yml:/export/config/config.yml:ro \
    homeylab/bookstack-file-exporter:latest
```

### Docker Compose
When using `run_interval` or `run_schedule`, a docker compose set up could be used to run the exporter as an always running application. The exporter will wait for the next interval or scheduled time before subsequent runs.

An example is shown in `examples/docker-compose.yaml`

#### Bind Mounts
| purpose | static docker path | description | example |
| ------- | ------------------ | ----------- | ------- |
| `config` | `/export/config/config.yml` | A valid configuration file |`-v /local/yourpath/config.yml:/export/config/config.yml:ro`|
| `dump` | `/export/dump` | Directory to place exports. **This is optional when using remote storage option(s)**. Omit if you don't need a local copy. | `-v /local/yourpath/bkps:/export/dump` |

## Run via Helm
A helm chart can be used to run the exporter as a CronJob or Deployment resource. See [here](https://github.com/homeylab/helm-charts/tree/main/charts/bookstack-file-exporter) for more information on using the helm chart.

## Options
Command line options:
| option | env var | required | description |
| ------ | ------- | -------- | ----------- |
|`-c`, `--config-file`|—|True|Relative or Absolute path to a valid configuration file. This configuration file is checked against a schema for validation.|
|`-o`, `--output-dir` |—|False|Optional output directory for exports. Takes precedence over `output_path` in the config file if both are set.|
|`-v`, `--log-level` |`LOG_LEVEL`|False, default: info|Provide a valid log level: info, debug, warning, error. CLI overrides the `LOG_LEVEL` env var.|
|`--log-format` |`LOG_FORMAT`|False, default: text|Log output format. `text` (default) or `json` for JSON Lines. CLI overrides the `LOG_FORMAT` env var.|
|`--run-once` |—|False|Force a single run and exit, ignoring `run_interval` and `run_schedule` in the config. Useful for a manual or CI-triggered run against a config that is otherwise set up for application (scheduled) mode.|

## Environment Variables
See [Valid Environment Variables](configuration.md#valid-environment-variables) for more options.

Example:
```bash
export LOG_FORMAT=text
export BOOKSTACK_TOKEN_ID=XXXX
export BOOKSTACK_TOKEN_SECRET=YYYY

# using pip
python -m bookstack_file_exporter -c <path_to_config_file>

# using docker
docker run \
    -e LOG_FORMAT='text' \
    -e BOOKSTACK_TOKEN_ID='xyz' \
    -e BOOKSTACK_TOKEN_SECRET='xyz' \
    --user 1000:1000 \
    -v $(pwd)/config.yml:/export/config/config.yml:ro \
    -v $(pwd)/bkps:/export/dump \
    homeylab/bookstack-file-exporter:latest
```

## Authentication and Permissions
### Permissions
**Note visibility of pages is based on user**, so use a user that has read access to pages and content you want to back up. *The role assigned to the user* should have the additional permissions for target pages and their content:
- `read` for all images and attachments
  - For most users this may already be set - may be required to be set depending on storage option used
- `Export Content` (This can be found in `Edit Role --> System Permissions`)
  - For most users this may already set - may be required to be set if using custom roles
  - If not set, you may see page contents showing as a HTML login page, as reported in this [issue](https://github.com/homeylab/bookstack-file-exporter/issues/35)

### Token Authentication
Ref: [https://demo.bookstackapp.com/api/docs#authentication](https://demo.bookstackapp.com/api/docs#authentication)

Provide a tokenId and a tokenSecret as environment variables or directly in the configuration file.
- `BOOKSTACK_TOKEN_ID`
- `BOOKSTACK_TOKEN_SECRET`

Env variables for credentials will take precedence over configuration file options if both are set.

**For object storage authentication**, see [Object Storage Upload](remote-storage.md#object-storage-upload).

## Operations
Once configured, run modes (one-shot vs scheduled), scheduling strategies, run outcomes and exit codes, graceful shutdown and grace periods, and the `/healthz` health endpoint are all covered in [Operations](operations.md).
