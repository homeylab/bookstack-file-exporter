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
- [Run Modes](#run-modes)
- [Graceful Shutdown And Grace Periods](#graceful-shutdown-and-grace-periods)
- [Health Endpoint](#health-endpoint)

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
|`-v`, `--log-level` |—|False, default: info|Provide a valid log level: info, debug, warning, error.|
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

## Run Modes
The exporter runs in one of two modes, selected automatically from your config:

- **One-shot** (default): `run_interval` unset or `0`, and `run_schedule` unset → runs once and exits. Returns exit code `0` on success, `1` on failure (clean error message; pass `-v debug` for the full traceback), and `130` on `Ctrl-C`. Pairs well with an external scheduler (Kubernetes `CronJob`, `cron`, `systemd` timer), which owns restart, backoff, and run history.
- **Application / scheduled** (long-running): `run_interval` or `run_schedule` set → runs repeatedly, then waits for the next trigger. For a single-container `docker compose` deployment with no external scheduler. A failed cycle is logged (and notifies, if configured) and waits for the next trigger rather than crashing. Shuts down gracefully on `SIGTERM` (`docker stop`) and `SIGINT` (`Ctrl-C`), exiting `0`.

Two scheduling strategies are available for application mode (mutually exclusive — setting both is a config error):

- **`run_interval`** (seconds): sleeps a fixed number of seconds between cycles. Simple but drifts over time — the effective period is `run_interval` + cycle runtime.
- **`run_schedule`** (cron expression): fires at wall-clock times. Standard 5-field cron syntax (e.g. `"0 2 * * *"` = 2 am daily). croniter also accepts 6/7-field extended forms. Cron is evaluated in container-local time — set the `TZ` environment variable to control the timezone (default: `UTC`). Note: if a cycle runs past its scheduled tick, the missed tick is skipped (no catch-up). During a DST spring-forward, a scheduled time that falls inside the skipped hour will not fire that day.

Pass `--run-once` to force a single run regardless of `run_interval` or `run_schedule`.

## Graceful Shutdown And Grace Periods

In scheduled mode `SIGTERM`/`SIGINT` shuts down gracefully: the exporter stops at the
next asset/format/node boundary, discards any partial archive, and exits `0`. A second
signal force-kills immediately (`130` for SIGINT, `143` for SIGTERM). Exit `0` means a
clean shutdown, **not** that the last cycle succeeded — alert on notifications or
`/healthz`, not on the exit code.

One-shot mode (`--run-once`, or no `run_interval`/`run_schedule`) aborts the current run
on a signal rather than draining, but still discards any partial archive and exits
`130`/`143`.

A single in-flight export call (e.g. a large-book PDF render) cannot be interrupted
mid-request, so give the container time to drain:

- Docker: `docker stop -t 60 <container>` (default is 10s).
- Compose: set `stop_grace_period: 60s` (raise for large instances).
- Kubernetes: set `terminationGracePeriodSeconds: 60`.

If the grace window elapses the orchestrator sends an uncatchable SIGKILL, which can
strand a partial archive. The next run sweeps leftover `.tar`/`.tgz.partial` files (at
any export level) before it writes anything; a finished `.tgz` is never touched.

## Health Endpoint

In scheduled mode (`run_interval` or `run_schedule`), set `health_port` to expose an
opt-in `GET /healthz` endpoint. No server is started unless `health_port` is set, and
it is ignored in one-shot mode.

```yaml
health_port: 8080          # opt-in; no server unless set
health_host: "0.0.0.0"     # optional bind address (default 0.0.0.0)
```

`GET /healthz` returns `200` with a JSON body while the daemon is alive:

```json
{
  "status": "healthy",
  "last_run": {
    "status": "success",
    "started_at": "2026-06-21T02:00:00Z",
    "finished_at": "2026-06-21T02:03:11Z",
    "duration_seconds": 191,
    "archive_file": "bookstack_export_2026-06-21.tgz",
    "error": null
  },
  "next_run": "2026-06-22T02:00:00Z",
  "run_count": 5,
  "failure_count": 0
}
```

This is a **liveness** signal: it stays `200` even after a failed export cycle
(the scheduled loop logs and continues), so probes do not flap on transient
BookStack outages. Use `last_run.status` (`never` → `running` → `success` |
`degraded` | `failed`) and `failure_count` for scrape-based alerting. Any path
other than `/healthz` returns `404`.

`degraded` is a **partial success**: a local/remote copy survived but at least
one remote target failed. It counts as a completed run and does **not** increment
`failure_count`, so alert on `last_run.status == "degraded"` separately — watching
`failure_count` alone will miss partial upload failures.

Kubernetes liveness probe:

```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 30
```

Docker healthcheck:

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz').status==200 else 1)"
```
