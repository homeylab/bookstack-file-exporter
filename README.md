# bookstack-file-exporter

> [!NOTE]
> This documentation tracks the `main` branch and may describe unreleased changes.
> For docs matching your installed version, use the branch/tag dropdown to switch to your release tag. See [Releases](https://github.com/homeylab/bookstack-file-exporter/releases) for the list of published versions.

Table of Contents
- [bookstack-file-exporter](#bookstack-file-exporter)
  - [Background](#background)
    - [Features](#features)
    - [Use Case](#use-case)
  - [Using This Application](#using-this-application)
    - [Run via Pip](#run-via-pip)
    - [Log Format](#log-format)
    - [Run via Docker](#run-via-docker)
    - [Run via Helm](#run-via-helm)
    - [Authentication and Permissions](#authentication-and-permissions)
    - [Configuration](#configuration)
  - [Export Level](#export-level)
  - [Parallel Export](#parallel-export)
  - [Filters](#filters)
  - [Backup Behavior](#backup-behavior)
    - [General](#general)
    - [Images](#images)
    - [Attachments](#attachments)
    - [Modify Links](#modify-links)
  - [Object Storage](#object-storage)
    - [Object Storage Upload (MinIO / S3)](#object-storage-upload-minio--s3)
  - [Notifications](#notifications)
    - [apprise](#apprise)
  - [Potential Breaking Upgrades](#potential-breaking-upgrades)
  - [Running Tests](#running-tests)
  - [Future Items](#future-items)

## Background
_If you encounter any issues, want to request an additional feature, or provide assistance, feel free to open a Github issue._

This tool provides a way to export [Bookstack](https://github.com/BookStackApp/BookStack) pages and their content (_text, images, attachments, metadata, etc._) into a relational parent-child layout locally with an option to push to remote object storage locations. See [Backup Behavior](#backup-behavior) section for more details on how pages are organized. Image and attachment links can also be modified in markdown and html exports to point to local exported paths.

This small project was mainly created to run as a cron job in k8s but works anywhere. This tool allows me to export my docs in markdown, or other formats like pdf. I use Bookstack's markdown editor as default instead of WYSIWYG editor and this makes my notes portable anywhere even if offline.

### Features
What it does:

- Discover and build relationships between Bookstack `Shelves/Books/Chapters/Pages` to create a relational parent-child layout
- Export Bookstack pages and their content to a `.tgz` archive
- Additional content for pages like their images, attachments, and metadata and can be exported
- The exporter can also [Modify Links](#modify-links) to replace image and/or attachment links with local exported paths for a more portable backup
- YAML configuration file for repeatable and easy runs
- Can be run via [Python](#run-via-pip) or [Docker](#run-via-docker)
- Can push archives to remote object storage like [MinIO](https://min.io/) or [AWS S3](https://aws.amazon.com/s3/)
- Basic housekeeping option (`keep_last`) to keep a tidy archive destination
- Can run in application mode (always running) using `run_interval` (interval-based) or `run_schedule` (cron-based) properties. Used for scheduling backups.

Supported backup targets are:

1. local
2. minio
3. s3

Supported backup formats are based on Bookstack API and shown [here](https://demo.bookstackapp.com/api/docs#pages-exportHtml) and below:

1. html
2. pdf
3. markdown
4. plaintext
5. zip

### Use Case
The main use case is to backup all docs in a relational directory-tree format to cover the scenarios:

1. Share docs with another person to keep locally.
2. Offline copy wanted.
3. Back up at a file level as an accessory or alternative to disk and volume backups.
4. Migrate all Bookstack page contents to Markdown documenting for simplicity.
5. Provide an easy way to do automated file backups locally, in docker, or [kubernetes](https://github.com/homeylab/helm-charts/tree/main/charts/bookstack#file-exporter-backup-your-pages) for Bookstack page contents.

## Using This Application
Ensure a valid configuration is provided when running this application. See [Configuration](#Configuration) section for more details.

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

### Run via Pip
The exporter can be installed via pip (or [uv](https://docs.astral.sh/uv/)) and run directly.

#### Python Version
_Note: This application is tested and developed on Python version `3.14.5`. The min required version is >= `3.11` but is recommended to install (or set up a venv) a `3.14.5` version._

#### Examples
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

#### Options
Command line options:
| option | required | description |
| ------ | -------- | ----------- |
|`-c`, `--config-file`|True|Relative or Absolute path to a valid configuration file. This configuration file is checked against a schema for validation.|
|`-v`, `--log-level` |False, default: info|Provide a valid log level: info, debug, warning, error.|
|`--log-format` |False, default: text|Log output format. `text` (default) or `json` for JSON Lines. CLI overrides the `LOG_FORMAT` env var.|
|`--run-once` |False|Force a single run and exit, ignoring `run_interval` and `run_schedule` in the config. Useful for a manual or CI-triggered run against a config that is otherwise set up for application (scheduled) mode.|

#### Environment Variables
See [Valid Environment Variables](#valid-environment-variables) for more options.

Example:
```bash
export LOG_LEVEL=debug

# using pip
python -m bookstack_file_exporter -c <path_to_config_file>
```

### Log Format

By default logs are human-readable text. Set JSON Lines output (one JSON object
per line) for log aggregators (Loki/ELK/CloudWatch):

- CLI: `--log-format json`
- Env (containers): `LOG_FORMAT=json`

The CLI flag overrides the env var; default is `text`. An unrecognized
`LOG_FORMAT` value falls back to `text` with a warning.

Sample JSON line:

```json
{"timestamp": "2026-06-21T05:03:59.123Z", "level": "INFO", "logger": "bookstack_file_exporter.run", "message": "Beginning run"}
```

### Run via Docker
Docker images are provided for `linux/amd64` and `linux/arm64` variants only at the moment. If another variant is required, please request it via Github Issue.

#### Tags
Users will generally want to use the `latest` tag or a specific version tag. The `main` tag is also provided but is not guaranteed to be stable.

| tag | description |
| --- | ----------- |
| `latest` | Latest stable release and is updated with each new stable release. |
| `X.X.X`  | Semantic versioned releases are also provided if preferred for stability or other reasons. |
| `main` | This tag reflects the `main` branch of this repository and may not be stable |

#### Examples
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

#### Run Modes
The exporter runs in one of two modes, selected automatically from your config:

- **One-shot** (default): `run_interval` unset or `0`, and `run_schedule` unset → runs once and exits. Returns exit code `0` on success, `1` on failure (clean error message; pass `-v debug` for the full traceback), and `130` on `Ctrl-C`. Pairs well with an external scheduler (Kubernetes `CronJob`, `cron`, `systemd` timer), which owns restart, backoff, and run history.
- **Application / scheduled** (long-running): `run_interval` or `run_schedule` set → runs repeatedly, then waits for the next trigger. For a single-container `docker compose` deployment with no external scheduler. A failed cycle is logged (and notifies, if configured) and waits for the next trigger rather than crashing. Shuts down gracefully on `SIGTERM` (`docker stop`) and `SIGINT` (`Ctrl-C`), exiting `0`.

Two scheduling strategies are available for application mode (mutually exclusive — setting both is a config error):

- **`run_interval`** (seconds): sleeps a fixed number of seconds between cycles. Simple but drifts over time — the effective period is `run_interval` + cycle runtime.
- **`run_schedule`** (cron expression): fires at wall-clock times. Standard 5-field cron syntax (e.g. `"0 2 * * *"` = 2 am daily). croniter also accepts 6/7-field extended forms. Cron is evaluated in container-local time — set the `TZ` environment variable to control the timezone (default: `UTC`). Note: if a cycle runs past its scheduled tick, the missed tick is skipped (no catch-up). During a DST spring-forward, a scheduled time that falls inside the skipped hour will not fire that day.

Pass `--run-once` to force a single run regardless of `run_interval` or `run_schedule`.

#### Graceful shutdown & grace periods

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

#### Health Endpoint

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
`failed`) and `failure_count` for scrape-based alerting. Any path other than
`/healthz` returns `404`.

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

#### Docker Compose
When using `run_interval` or `run_schedule`, a docker compose set up could be used to run the exporter as an always running application. The exporter will wait for the next interval or scheduled time before subsequent runs.

An example is shown in `examples/docker-compose.yaml`

#### Environment Variables
See [Valid Environment Variables](#valid-environment-variables) for more options.

Tokens and other options can be specified, example:

```bash
# '-e' flag for env vars
# --user flag to override the uid/gid for created files. Set this to your uid/gid
docker run \
    -e LOG_LEVEL='debug' \
    -e BOOKSTACK_TOKEN_ID='xyz' \
    -e BOOKSTACK_TOKEN_SECRET='xyz' \
    --user 1000:1000 \
    -v $(pwd)/config.yml:/export/config/config.yml:ro \
    -v $(pwd)/bkps:/export/dump \
    homeylab/bookstack-file-exporter:latest
```

#### Bind Mounts
| purpose | static docker path | description | example |
| ------- | ------------------ | ----------- | ------- |
| `config` | `/export/config/config.yml` | A valid configuration file |`-v /local/yourpath/config.yml:/export/config/config.yml:ro`|
| `dump` | `/export/dump` | Directory to place exports. **This is optional when using remote storage option(s)**. Omit if you don't need a local copy. | `-v /local/yourpath/bkps:/export/dump` |

### Run via Helm
A helm chart can be used to run the exporter as a CronJob or Deployment resource. See [here](https://github.com/homeylab/helm-charts/tree/main/charts/bookstack-file-exporter) for more information on using the helm chart.

### Authentication and Permissions
#### Permissions
**Note visibility of pages is based on user**, so use a user that has read access to pages and content you want to back up. *The role assigned to the user* should have the additional permissions for target pages and their content:
- `read` for all images and attachments
  - For most users this may already be set - may be required to be set depending on storage option used
- `Export Content` (This can be found in `Edit Role --> System Permissions`)
  - For most users this may already set - may be required to be set if using custom roles
  - If not set, you may see page contents showing as a HTML login page, as reported in this [issue](https://github.com/homeylab/bookstack-file-exporter/issues/35)

#### Token Authentication
Ref: [https://demo.bookstackapp.com/api/docs#authentication](https://demo.bookstackapp.com/api/docs#authentication)

Provide a tokenId and a tokenSecret as environment variables or directly in the configuration file.
- `BOOKSTACK_TOKEN_ID`
- `BOOKSTACK_TOKEN_SECRET`

Env variables for credentials will take precedence over configuration file options if both are set.

**For object storage authentication**, find the relevant sections further down in their respective sections.

### Configuration
_Ensure [Authentication](#authentication-and-permissions) has been set up beforehand for required credentials._ For a simple example to run quickly, refer to the one in the [Using This Application](#using-this-application) section.

A full example is also shown below. Optionally, look at `examples/` folder of the github repo for more examples with long descriptions.

For object storage configuration, find more information in the [Object Storage Upload](#object-storage-upload-minio--s3) section.

**Schema and values are checked so ensure proper settings are provided. As mentioned, credentials can be specified as environment variables instead if preferred.**

#### Full Example
Below is an example configuration that shows example values for all possible options.

```yaml
host: "https://bookstack.yourdomain.com"
credentials:
  token_id: ""
  token_secret: ""
formats:
  - markdown
  - html
  - pdf
  - plaintext
  - zip
http_config:
  verify_ssl: false
  timeout: 30
  backoff_factor: 2.5
  retry_codes: [413, 429, 500, 502, 503, 504]
  retry_count: 5
  additional_headers:
    User-Agent: "test-agent"
object_storage:
  - type: minio
    host: "minio.yourdomain.com"
    region: "us-east-1"
    bucket: "mybucket"
    path: "bookstack/file_backups"
    secure: false
    keep_last: 5
output_path: "bkps/"
assets:
  export_images: true
  export_attachments: true
  modify_links: false
  export_meta: false
keep_last: 5
run_interval: 0
notifications:
  apprise:
    service_urls:
      - "json://localhost:8080/notify"
    config_path: ""
    plugin_paths: []
    storage_path: ""
    custom_title: ""
    custom_attachment_path: ""
    on_success: false
    on_failure: true
filters:
  shelves:
    exclude: ["Archive"]
  books:
    include: ["eng-.*"]
    exclude: ["draft"]
  pages:
    exclude: ["secret", "scratch"]
```

#### Options and Descriptions
More descriptions can be found for each section below:

| Configuration Item | Type | Required | Description |
| ------------------ | ---- | -------- | ----------- |
|  `host` | `str` | `true` | If `http/https` not specified in the url, defaults to `https`. Use `http_config.verify_ssl` to disable certificate checking. |
| `credentials` | `object` | `false` | Optional section where Bookstack tokenId and tokenSecret can be specified. Env variable for credentials may be supplied instead. See [Authentication](#authentication) for more details. |
| `credentials.token_id` | `str`| `false` if specified through env var instead, otherwise `true` | A valid Bookstack tokenId. |
| `credentials.token_secret` | `str` | `false` if specified through env var instead, otherwise `true` | A valid Bookstack tokenSecret. |
| `formats` | `list<str>` | `true` | Which export formats to use for BookStack content. Valid options are: `["markdown", "html", "pdf", "plaintext", "zip"]`|
| `export_level` | `str` | `false` | Optional (default: `pages`). Export granularity. See [Export Level](#export-level) for details. Valid options: `pages`, `books`, `chapters`. |
| `export_workers` | `int` | `false` | Optional (default: `1`). Number of nodes (pages/books/chapters) fetched in parallel; `1` keeps the original serial behavior. Raising it speeds up large exports but increases concurrent API load. See [Parallel Export](#parallel-export) for tuning and rate-limit guidance. |
| `output_path` | `str` | `false` | Optional (default: `cwd`) which directory (relative or full path) to place exports. User who runs the command should have access to read/write to this directory. This directory and any parent directories will be attempted to be created if they do not exist. If not provided, will use current run directory by default. If using docker, this option can be omitted. |
| `assets` | `object` | `false` | Optional section to export additional assets from pages. |
| `assets.export_images` | `bool` | `false` | Optional (default: `false`), export all images to an `images` directory. Works at all export levels: per-page directory at `pages` level; per-book or per-chapter directory at `books`/`chapters` level. See [Backup Behavior](#backup-behavior) for more information on layout |
| `assets.export_attachments` | `bool` | `false` | Optional (default: `false`), export all attachments to an `attachments` directory. Works at all export levels: per-page directory at `pages` level; per-book or per-chapter directory at `books`/`chapters` level. See [Backup Behavior](#backup-behavior) for more information on layout |
| `assets.modify_links` | `bool` | `false` | Optional (default: `false`). Rewrites image and attachment URLs in markdown AND html exports to local relative paths. Requires `assets.export_images` and/or `assets.export_attachments` to be `true`. Controls link *rewriting* only — assets are downloaded whenever their export flag is set, regardless of `modify_links`. Only applies to `markdown` and `html` formats; pdf, plaintext, and zip are not eligible. Legacy key `modify_markdown` still accepted (deprecated); will be removed in a future version. See [Modify Links](#modify-links) for more information. |
| `assets.export_meta` | `bool` | `false` | Optional (default: `false`), export metadata about each archived page, book, or chapter in a json file. |
| `http_config` | `object` | `false` | Optional section to override default http configuration. |
| `http_config.verify_ssl` | `bool` | `false` | Optional (default: `false`), whether or not to verify ssl certificates if using https. |
| `http_config.timeout` | `int` | `false` | Optional (default: `30`), set the timeout, in seconds, for http requests. |
| `http_config.retry_count` | `int` | `false` | Optional (default: `5`), the number of http retries after initial failure. |
| `http_config.retry_codes` | `List[int]` | `false` | Optional (default: `[413, 429, 500, 502, 503, 504]`), which http response status codes trigger a retry. |
| `http_config.backoff_factor` | `float` | `false` | Optional (default: `2.5`), set the backoff_factor for http request retries. Default backoff_factor `2.5` means we wait 5, 10, 20, and then 40 seconds (with default `http_config.retry_count: 5`) before our last retry. This should allow for per minute rate limits to be refreshed. |
| `http_config.additional_headers` | `object` | `false` | Optional (default: `{}`), specify key/value pairs that will be added as additional headers to http requests. |
| `keep_last` | `int` | `false` | Optional (default: `0`), if exporter can delete older archives. valid values are:<br>- set to `-1` if you want to delete all archives after each run (useful if you only want to upload to object storage)<br>- set to `1+` if you want to retain a certain number of archives<br>- `0` will result in no action done. |
| `run_interval` | `int` | `false` | Optional (default: `0`). If specified, exporter will run as an application and pause for `{run_interval}` seconds before subsequent runs. Example: `86400` seconds = `24` hours or run once a day. Setting this property to `0` will invoke a single run and exit. Mutually exclusive with `run_schedule`. |
| `run_schedule` | `str` | `false` | Optional. Cron expression for wall-clock scheduling (e.g. `"0 2 * * *"` = 2 am daily). Standard 5-field cron; croniter also accepts 6/7-field extended forms. An invalid expression is rejected at config load. Evaluated in container-local time — set `TZ` env var to control timezone (default: `UTC`). If a cycle overruns its scheduled tick, the missed tick is skipped (no catch-up). Mutually exclusive with `run_interval`. |
| `health_port` | `int` | `false` | Optional (default: unset). Scheduled mode only (`run_interval` or `run_schedule`). When set, the daemon serves an opt-in `GET /healthz` endpoint on this port. No server is started unless set; ignored in one-shot mode. See [Health Endpoint](#health-endpoint). |
| `health_host` | `str` | `false` | Optional (default: `0.0.0.0`). Bind address for the `health_port` server. Set to `127.0.0.1` or a specific NIC to restrict exposure on a multi-homed host. Only used when `health_port` is set. |
| `object_storage` | `list` | `false` | Optional list of object storage upload targets. See [Object Storage Upload](#object-storage-upload-minio--s3) for details. |
| `notifications` | `object` | `false` | Optional [notification](#notifications) configuration options. |
| `filters` | `object` | `false` | Optional per-resource-type regex filters (include/exclude lists). See [Filters](#filters) for details. |
| `filters.exclude_unassigned_books` | `bool` | `false` | Optional (default: `false`). When `true`, drop all books that are not on any shelf, independent of the `books` patterns. See [Filters](#filters) for details. |

#### Valid Environment Variables
General
- `LOG_LEVEL`: default: `info`. Provide a valid log level: info, debug, warning, error.
- `LOG_FORMAT`: default: `text`. Set to `json` for JSON Lines output. See [Log Format](#log-format).

[Bookstack Credentials](#authentication)
- `BOOKSTACK_TOKEN_ID`
- `BOOKSTACK_TOKEN_SECRET`

[Object Storage Credentials](#object-storage-upload-minio--s3)
- `MINIO_ACCESS_KEY` — default MinIO access key (single-target MinIO, backward-compatible with v2)
- `MINIO_SECRET_KEY` — default MinIO secret key
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` — AWS default chain for S3 targets

## Export Level

The `export_level` configuration option controls the granularity of exports:

| Value | Description |
| ----- | ----------- |
| `pages` (default) | One file per page. Supports `assets.export_images`, `assets.export_attachments`, and `assets.modify_links`. |
| `books` | One combined file per book per format, written to a per-book folder (`<shelf>/<book>/<book>.<ext>`). Setting `assets.export_images` and/or `assets.export_attachments` downloads those assets at book level. Set `assets.modify_links: true` to also rewrite asset links in `markdown` and `html` to local relative paths. `pdf` stays self-contained (assets embedded by Bookstack server-side). |
| `chapters` | One combined file per chapter per format, in a per-chapter folder (`<shelf>/<book>/<chapter>/<chapter>.<ext>`). Same `export_images`/`export_attachments` and `modify_links` support as `books`. **Note:** pages not under any chapter are not captured at this level. |

**Example:** `formats: [pdf]` + `export_level: books` exports one PDF per book through the server-side BookStack API export.

**Empty nodes:** At `books` and `chapters` levels, a book or chapter with no child content is skipped — no file is written and the omission is logged at `INFO`. This keeps the archive free of empty placeholder documents.

The shelf/book/chapter hierarchy is preserved as directories inside the archive regardless of level — e.g. `books` produces `<shelf>/<book>/<book>.pdf` and `chapters` produces `<shelf>/<book>/<chapter>/<chapter>.pdf` (books without a shelf go under the unassigned directory).

`assets.export_meta` applies at all levels: when enabled, a `_meta.json` file is written alongside each exported node.

For non-default levels the archive filename is suffixed with the level (e.g. `bkps_books_<timestamp>.tgz`, `bkps_chapters_<timestamp>.tgz`); `pages` keeps the unsuffixed `bkps_<timestamp>.tgz`. Because `keep_last` cleanup matches on this prefix, archive retention is scoped independently per level.

## Parallel Export

`export_workers` controls how many nodes (pages/books/chapters) are fetched at once. The default `1` preserves the original one-node-at-a-time behavior; raising it overlaps the network waits across nodes.

**How it works:** each worker is a thread that fetches one node's export renders and assets. The work is I/O-bound — the bulk of the time is spent waiting on BookStack — so the threads overlap those waits rather than competing for CPU. Writes into the tar archive are serialized internally, so the archive stays consistent regardless of worker count.

**Tuning:** raising `export_workers` speeds up large exports, but only until your BookStack server becomes the limiting factor — beyond that, more workers could just add load without much benefit. How much you gain depends on how quickly your BookStack instance serves requests, which varies with its resources, configuration, and deployment, so the ideal value differs between setups. In local testing a handful of workers gave roughly a 2x speedup over serial with gains flattening after that; treat `export_workers` as a knob to tune for your environment rather than a guaranteed multiplier.

**Rate limiting:** more workers means more concurrent API requests. BookStack rate-limits the API (`API_REQUESTS_PER_MIN`, default `180`/min per user → HTTP `429`). If you raise `export_workers` and start seeing `429`s, raise `API_REQUESTS_PER_MIN` in BookStack's `.env`.

Values above `16` emit a startup warning — a heads-up for users, not a hard cap.

## Filters

The `filters` configuration option lets you include or exclude BookStack resources (shelves, books, chapters, pages) by name during export. Filtering runs during the tree build, before the exporter issues any detail API call for a node — excluded books, chapters, and pages — and all descendants of any excluded node — are never fetched.

#### Schema

All keys are optional. Omit a type entirely (or leave its lists empty/`[]`) to apply no filter for that type.

```yaml
filters:
  shelves:
    exclude: ["Archive"]            # drops the Archive shelf + everything under it
  books:
    include: ["eng-.*"]             # optional allow-list (fullmatch)
    exclude: ["draft"]
  chapters:
    exclude: []
  pages:
    exclude: ["secret", "scratch"]
  # structural toggle: drop every book that is not on a shelf
  exclude_unassigned_books: false
```

#### Pattern matching

Patterns are Python [`re.fullmatch`](https://docs.python.org/3/library/re.html#re.fullmatch) — the **entire** display name must match. Substring matching is opt-in via `.*`:

| Pattern | Matches |
| ------- | ------- |
| `draft` | `draft` only |
| `draft.*` | `draft`, `draft-api` |
| `.*draft.*` | `draft`, `draft-api`, `old-draft` |

This means `exclude: ["draft"]` drops only the resource named exactly `draft`, not `draft-api` or `old-draft`. Add those names to the list (or use a pattern like `draft.*`) to drop them too.

Patterns are also **case-sensitive** by default — `windows` does not match a shelf named `Windows`. Prefix with the inline flag `(?i)` for case-insensitive matching:

| Pattern | Matches |
| ------- | ------- |
| `Windows` | `Windows` only |
| `(?i)windows` | `windows`, `Windows`, `WINDOWS` |
| `(?i).*windows.*` | any name containing `windows`, any case |

#### What the pattern matches

Filters currently only match the resource's **display name** (the title shown in the BookStack UI), *not* the lowercased slug used for on-disk directory names. A shelf shown as `Windows` exports to a `windows/` directory, but the filter pattern must target `Windows` (or `(?i)windows`), not the `windows` directory name.

#### Precedence

Per resource node:
1. If `include` is non-empty, the name must `fullmatch` at least one include pattern to survive.
2. If the name `fullmatch`es any `exclude` pattern, it is dropped — **exclude wins**.

Both conditions are evaluated against the bare display name of the node (not a path).

#### Cascade

Excluding a shelf, book, or chapter prunes its entire subtree — children are never fetched or exported. For example, `shelves.exclude: ["Archive"]` suppresses the Archive shelf and all books, chapters, and pages beneath it with no additional configuration.

#### Interaction with export_level

Filters are applied as the resource tree is built, which happens before [`export_level`](#export-level) selects what to archive. Shelves and books are always built (books are the basis for every level), so their filters always apply. Chapter and page filters only take effect when the level builds those nodes:

| `export_level` | Filters applied |
| -------------- | --------------- |
| `books` | `shelves`, `books` |
| `chapters` | `shelves`, `books`, `chapters` |
| `pages` (default) | `shelves`, `books`, `chapters`, `pages` |

A filter for a type below the selected level is **silently ignored** — e.g. a `pages` filter has no effect when `export_level: books`. Cascade still works at every level: excluding a parent prunes its whole subtree.

#### Excluding books with no shelf

A `shelves` filter only decides which shelves survive (and cascades to books *on* dropped shelves). A book on no shelf is an independent root and is **not** governed by the `shelves` filter. To drop such books, either name them with a `books` rule or set the structural toggle:

```yaml
filters:
  shelves:
    include: ["(?i)windows"]      # keep only the Windows shelf
  exclude_unassigned_books: true  # drop every book not on a shelf
```

`exclude_unassigned_books` is structural and takes precedence over `books` patterns: when `true`, every shelfless book is dropped even if it would match a `books.include` pattern. `books` filters then only affect books that live on a surviving shelf. The toggle is independent of `export_level` (it applies at all levels, since books are always built).

#### Validation

All patterns are compiled with `re.compile` at config load time. An invalid regex or an empty string `""` pattern is rejected with a clear error message before any API call is made.

#### Known limitations

- **Same-name resources cannot be individually disambiguated.** If two books share the same display name, a filter pattern will match both. Use cascade (exclude the parent shelf/book) to scope the filter more precisely, or rename one of the resources.
- **Renaming a resource can silently break a filter.** Filters match display names, not IDs — if a resource is renamed, existing patterns will no longer match it.
- **Shelfless books aren't governed by `shelves` filters** — see [Excluding books with no shelf](#excluding-books-with-no-shelf).

## Backup Behavior

### General
Backups are exported in `.tgz` format and generated based off timestamp. Export names will be in the format: `%Y-%m-%d_%H-%M-%S` (Year-Month-Day_Hour-Minute-Second). *Files are first pulled locally to create the tarball and then can be sent to object storage if needed*. Example file name: `bookstack_export_2023-09-22_07-19-54.tgz`.

The exporter can also do housekeeping duties and keep a configured number of archives and delete older ones. See `keep_last` property in the [Configuration](#options-and-descriptions) section. Object storage provider configurations include their own `keep_last` property for flexibility. 

#### File Naming
For file names, `slug` names (from Bookstack API) are used, as such certain characters like `!`, `/` will be ignored and spaces replaced from page names/titles. If your page has an empty `slug` value for some reason (draft that was never fully saved), the exporter will use page name with the `slugify` function from Django to generate a valid slug. Example: `My Page.bin Name!` will be converted to `my-page-bin-name`.

You may also notice some directories (books) and/or files (pages) in the archive have a random string at the end, example - `nKA`: `user-and-group-management-nKA`. This is expected and is because there were resources with the same name created in another shelve and bookstack adds a string at the end to ensure uniqueness.

#### Directory Layout
All sub directories will be created as required during the export process.
```
Shelves --> Books --> Chapters --> Pages

## Example
kafka (shelf)
---> controller (book)
    ---> settings (chapter)
        ---> retention-settings.md (page)
        ---> retention-settings_meta.json
            ...
        ---> compression.html (page)
        ---> compression.pdf
        ---> compression_meta.json
            ...
        ---> optional-config.md (page)
            ...
        ---> main.md (page)
            ...
---> broker (book)
    ---> settings.md (page)
        ...
    ---> deploy.md (page)
        ...
kafka-apps (shelf)
---> schema-registry (book)
    ---> protobuf.md (page)
        ...
    ---> settings.md (page)
        ...

## Example with image and attachment layout
# unassigned dir is used for books with no shelf
unassigned (shelf)
---> test (book)
    ---> images (image_dir)
        ---> test_page (page directory)
            ---> img-001.png
            ---> img-002.png
        ---> rec-page
            ---> img-010.png
            ---> img-020.png
    --> attachments (attachment_dir)
        ---> test_page (page directory)
            ---> something.config
            ---> something_else.config
        ---> rec-page
            ---> test_output.log
            ---> actual_output.log
    ---> test_page.md (page)
            ...
    ---> rec_page (page)
        ---> rec_page.md
        ---> rec_page.pdf
```

Another example is shown below:
```
## First example:
# programming = shelf
# book = react
# basics = page

bookstack_export_2023-11-28_06-24-25/programming/react/basics.md
bookstack_export_2023-11-28_06-24-25/programming/react/basics.pdf
bookstack_export_2023-11-28_06-24-25/programming/react/images/basics/YKvimage.png
bookstack_export_2023-11-28_06-24-25/programming/react/images/basics/dwwimage.png
bookstack_export_2023-11-28_06-24-25/programming/react/images/basics/NzZimage.png
bookstack_export_2023-11-28_06-24-25/programming/react/images/nextjs/next1.png
bookstack_export_2023-11-28_06-24-25/programming/react/images/nextjs/tips.png
bookstack_export_2023-11-28_06-24-25/programming/react/attachments/nextjs/sample.config
bookstack_export_2023-11-28_06-24-25/programming/react/attachments/nextjs/sample_output.log
bookstack_export_2023-11-28_06-24-25/programming/react/nextjs.md
bookstack_export_2023-11-28_06-24-25/programming/react/nextjs.pdf
```

Books without a shelf will be put in a shelve folder named `unassigned`.

#### Empty/New Pages
Empty/New Pages are ignored: they have not been modified from creation, so they have no content and no valid slug. From the Bookstack API they appear as `"name": "New Page"` with an empty `"slug": ""`.

### Images
Images will be dumped in a separate directory, `images` within the page parent (book/chapter) directory it belongs to. The relative path will be `{parent}/images/{page}/{image_name}`. As shown earlier:

```
bookstack_export_2023-11-28_06-24-25/programming/react/images/basics/dwwimage.png
bookstack_export_2023-11-28_06-24-25/programming/react/images/basics/NzZimage.png
bookstack_export_2023-11-28_06-24-25/programming/react/images/nextjs/next1.png
bookstack_export_2023-11-28_06-24-25/programming/react/images/nextjs/tips.png
```

**Note you may see old images in your exports. This is because, by default, Bookstack retains images/drawings that are uploaded even if no longer referenced on an active page. Admins can run `Cleanup Images` in the Maintenance Settings or via [CLI](https://www.bookstackapp.com/docs/admin/commands/#cleanup-unused-images) to remove them.**

If an API call to get an image or its metadata fails, the exporter will skip the image and log the error. If using `modify_links` option, the image links in the document will be untouched and in its original form. All API calls are retried 3 times after initial failure.

### Attachments
Attachments will be dumped in a separate directory, `attachments` within the page parent (book/chapter) directory it belongs to. The relative path will be `{parent}/attachments/{page}/{attachment_name}`. As shown earlier:

```
bookstack_export_2023-11-28_06-24-25/programming/react/attachments/nextjs/sample.config
bookstack_export_2023-11-28_06-24-25/programming/react/attachments/nextjs/sample_package.json
...
...
```

**Note attachments that are just external links are ignored. Only attachments that are shown as `external: False` will be exported.**

[Reference](https://demo.bookstackapp.com/api/docs#attachments-list) and excerpt from Bookstack API docs:
> Get a listing of attachments visible to the user. The external property indicates whether the attachment is simple a link. A false value for the external property would indicate a file upload.

If an API call to get an attachment or its metadata fails, the exporter will skip the attachment and log the error. If using `modify_links` option, the attachment links in the document will be untouched and in its original form. All API calls are retried 3 times after initial failure.

### Modify Links
**To use this feature, `assets.export_images` should be set to `true` and/or `assets.export_attachments` should be set to `true`.**

The configuration item, `assets.modify_links`, can be set to `true` to rewrite image and attachment URL links in exported files to local relative paths. This feature makes your `markdown` and `html` exports fully portable — assets resolve locally without a network connection to the Bookstack instance.

- **Eligible formats**: `markdown` and `html` only. PDF, plaintext, and zip exports are not yet requested/implemented.
- **Scope**: rewrites image `src` attributes and their outer anchor `href` wrappers; rewrites attachment `<a href>` links. Does **not** rewrite inter-page, inter-book, inter-chapter, or inter-shelf links (deferred to a future issue).
- **Legacy alias**: the old key `modify_markdown` will be removed in a future version. Rename to `modify_links` in your configuration.

#### Markdown example

```
## before
[![pool-topology-1.png](https://demo.bookstack/uploads/images/gallery/2023-07/scaled-1680-/pool-topology-1.png)](https://demo.bookstack/uploads/images/gallery/2023-07/pool-topology-1.png)

## after
[![pool-topology-1.png](images/{page_name}/pool-topology-1.png)](images/{page_name}/pool-topology-1.png)
```

#### HTML example

Bookstack HTML exports wrap images in an anchor tag (click-to-zoom). Both the
`<img src>` and the outer `<a href>` are rewritten to the same local file.
Images appear in one of two forms; both are localized:

```html
<!-- before: remote "scaled" thumbnail src (older bookstack installations) -->
<a href="https://demo.bookstack/uploads/images/gallery/2023-07/pool-topology-1.png">
  <img src="https://demo.bookstack/uploads/images/gallery/2023-07/scaled-1680-/pool-topology-1.png">
</a>

<!-- before: inline base64 src (recent bookstack installations) -->
<a href="https://demo.bookstack/uploads/images/gallery/2023-07/pool-topology-1.png">
  <img src="data:image/png;base64,...">
</a>

<!-- after (both forms): src and href point at the one local file -->
<a href="images/{page_name}/pool-topology-1.png">
  <img src="images/{page_name}/pool-topology-1.png">
</a>
```

Inline base64 images are de-inlined to the local file (shrinking the export by
up to ~700 KB per full-size image). A base64 image **not** wrapped in a
downloadable anchor is left inline (it still resolves offline).

Attachment links are rewritten from the live URL to a local relative path.

```html
<!-- before: attachment link -->
<a href="https://demo.bookstack/attachments/42">my-config.yml</a>

<!-- after -->
<a href="attachments/{page_name}/my-config.yml">my-config.yml</a>
```

#### Known limitations

Markdown link rewriting is a plain text substitution: if an asset URL appears verbatim anywhere in the markdown (code block, comment, plain text), it is also rewritten. HTML rewriting is scoped to `<img src>` / `<a href>` attributes only, so it is unaffected.

## Object Storage
Optionally, one or more upload targets can be specified to push generated archives to remote object storage. Optionally, look at `examples/config.yml` in the github repo for a commented-out example.

### Object Storage Upload (MinIO / S3)

Configure one or more upload targets under `object_storage:`. Each entry has a `type`
(`minio` or `s3`). Any S3-compatible store — Wasabi, Cloudflare R2, Backblaze B2, Ceph, DigitalOcean Spaces — also works under `type: s3` (or `type: minio`) by setting an explicit `host`.

```yaml
object_storage:
  # MinIO, creds from fixed MINIO_ACCESS_KEY / MINIO_SECRET_KEY env vars (default)
  - type: minio
    host: minio.local:9000        # required for minio (host:port)
    bucket: backups
    region: us-east-1             # optional for minio
    secure: false                 # local minio is often non-TLS
    path: exports                 # optional object key prefix
    keep_last: 5

  # Second MinIO with DISTINCT creds kept out of the file -> per-entry env NAMES
  - type: minio
    host: minio2.local:9000
    bucket: backups2
    secure: false
    access_key_env: MINIO2_ACCESS_KEY   # names of env vars to read
    secret_key_env: MINIO2_SECRET_KEY

  # AWS S3 with inline creds
  - type: s3
    bucket: aws-backups
    region: us-east-1             # required for s3
    # host optional; defaults to s3.<region>.amazonaws.com
    # secure defaults to true for s3
    keep_last: 10
    access_key: AKIA...
    secret_key: wJalr...

  # AWS S3 with no creds in config -> standard AWS_* env, else IAM role (EC2/ECS/EKS, auto-detected)
  - type: s3
    bucket: role-backups
    region: us-east-1
    keep_last: 10
```

#### Entry fields

| Item | Type | Required | Description |
| ---- | ---- | -------- | ----------- |
| `type` | `str` | `true` | `minio` or `s3` |
| `host` | `str` | required for `minio` | Hostname (and optional port) for the MinIO instance, e.g. `minio.yourdomain.com:9000`. For `s3`, defaults to `s3.<region>.amazonaws.com` if omitted. |
| `bucket` | `str` | `true` | Bucket to upload to |
| `region` | `str` | required for `s3`, optional for `minio` | AWS region or MinIO region. If unsure for MinIO, try `us-east-1`. |
| `secure` | `bool` | `false` | Optional (default: `true`). Set `false` for plain-HTTP local MinIO. |
| `path` | `str` | `false` | Optional object key prefix. Will use root bucket path if not set. |
| `keep_last` | `int` | `false` | Optional (default: `0`). Number of archives to retain in this target.<br>- set to `1+` to retain a certain number of archives<br>- `0` will result in no action done |
| `access_key` | `str` | `false` | Inline access key credential. |
| `secret_key` | `str` | `false` | Inline secret key credential. |
| `access_key_env` | `str` | `false` | Name of an environment variable to read for the access key. Use with `secret_key_env` to keep credentials out of the config file, or to give two targets of the same type distinct credentials. |
| `secret_key_env` | `str` | `false` | Name of an environment variable to read for the secret key. Must be paired with `access_key_env`. |
| `name` | `str` | `false` | Optional human-readable label for this target (intended for logs and notifications). If two entries share the same `type` and `bucket` (e.g. same bucket reached via different credentials), each **must** set a distinct `name` — the exporter rejects the config if two entries would produce the same derived `type/bucket` label and no `name` is set to disambiguate. |

#### Credential resolution (per entry, first match wins)

Each entry resolves credentials through an ordered chain; the first source that supplies a
full key pair wins.

1. **Per-entry named env vars** — `access_key_env` + `secret_key_env` give the *names* of the
   env vars to read. The only way to give two same-type targets *distinct* credentials kept
   out of the config file (the standard env vars in tier 2 are global, so they cannot).
   ```yaml
   - type: minio
     host: minio2.local:9000
     bucket: backups2
     access_key_env: MINIO2_ACCESS_KEY   # the value is the env var NAME, not the secret
     secret_key_env: MINIO2_SECRET_KEY
   ```
   ```bash
   export MINIO2_ACCESS_KEY=AKIA... MINIO2_SECRET_KEY=wJalr...
   ```
2. **Standard env vars** — the fixed, SDK-recognized names, picked up automatically. These are
   global: every entry of that type shares them.
   - minio: `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`
   - s3: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` (optional)

   They override inline keys (tier 3), consistent with the BookStack token and 12-factor
   precedence.
   ```yaml
   - type: minio
     host: minio.local:9000
     bucket: backups        # no creds in the YAML
   ```
   ```bash
   export MINIO_ACCESS_KEY=AKIA... MINIO_SECRET_KEY=wJalr...
   ```
3. **Inline keys** — `access_key` + `secret_key` in the entry itself.
   ```yaml
   - type: s3
     bucket: aws-backups
     region: us-east-1
     access_key: AKIA...
     secret_key: wJalr...
   ```
4. **IAM role** (`type: s3` only) — no secrets anywhere; the instance/pod role supplies
   short-lived credentials at runtime. Auto-detected by minio-py's `IamAwsProvider`: EC2
   (IMDS), ECS (container credentials), and EKS (IRSA web-identity / Pod Identity) — the
   cloud-native k8s/EC2 path.
   ```yaml
   - type: s3
     bucket: role-backups
     region: us-east-1      # no creds in the YAML, no env vars
   ```

Setting only one half of an *in-config* credential pair (`access_key` without `secret_key`,
or `*_env` without its partner) is a config error. A partially-set *standard env var* pair
(e.g. `MINIO_ACCESS_KEY` set but `MINIO_SECRET_KEY` unset) is **ignored, not an error** —
resolution falls through to the next source.

#### Multi-target upload behavior

Every configured `object_storage` target is attempted, even if an earlier one fails. The run
outcome is one of:

| Outcome | When | Exit code | Notification |
|---|---|---|---|
| Success | all targets uploaded | `0` | "Success" (`on_success`) |
| Partial | some targets failed, **or** all failed but a local copy is kept (`keep_last >= 0`) | `3` | "Partial" (`on_failure`) |
| Failure | the export itself failed, **or** all uploads failed with no local copy kept (`keep_last < 0`) | `1` | "Failed" (`on_failure`) |

A *partial* run means at least one durable copy of the backup survived (a remote target, or the
local `.tgz` when `keep_last >= 0`). It is reported via the `on_failure` notification so it is
not silently treated as a clean success. When `keep_last < 0` (local archive deleted) AND every
upload fails, the run is a hard failure — the local archive is preserved so the run can be retried.

In scheduled mode the `/healthz` endpoint reports `last_run.status` as `degraded` for a partial
run (distinct from `success` and `failed`).

## Migrating from v2

v3.0.0 removes the single `minio:` block. Move your settings into an `object_storage:`
list entry with `type: minio`:

```yaml
# v2 (removed)
minio:
  host: minio.local:9000
  bucket: backups
  region: us-east-1
  path: exports
  keep_last: 5

# v3
object_storage:
  - type: minio
    host: minio.local:9000
    bucket: backups
    region: us-east-1          # now optional for minio
    path: exports
    keep_last: 5
    secure: false              # NEW: set false for non-TLS local minio
```

`MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` env vars work unchanged for a single MinIO entry.
Note `secure` now defaults to `true`; set `secure: false` for plain-HTTP local MinIO.

## Notifications
It is possible to send notifications when an export run succeeds or fails. Currently, the only supported notification service is [apprise](https://github.com/caronc/apprise). Apprise is a general purpose notification service and has a variety of integrations and includes generic HTTP POST.

Notifications are optional and the `notification` section can be omitted/removed/commented out entirely to keep a smaller configuration if not required.

The title for notifications is configurable but if not specified, a default will be used. Example:
```
##### Failure Message #####
{TITLE}: Bookstack File Exporter Failed
{BODY}:
Bookstack File Exporter encountered an unrecoverable error.

Occurred At: 2025-09-06 01:02:47

Error message: 401 Client Error: Unauthorized for url: https://test.bookstack/api/shelve


##### Success Message #####
{TITLE}: Bookstack File Exporter Success
{BODY}:
Bookstack File Exporter completed successfully.

Completed At: 2025-09-06 01:05:27
Archive: bkps/bookstack_export_2025-09-06_010527.tgz (removed locally after upload)
Uploaded to: minio://my-bucket/bookstack, s3://my-bucket/bookstack
Pruned 2 old local archive(s)
```
The success body reports the archive details only when an archive is produced. `Archive:` shows the local `.tgz` path (with `(removed locally after upload)` when it was uploaded then deleted), `Uploaded to:` lists each remote destination, and `Pruned N old local archive(s)` appears when `keep_last` removed older archives.

### apprise
The apprise configuration is a part of the configuration yaml file under the notifications section and can be modified under `notifications.apprise`.

| Item | Type | Description |
| ---- | ---- | ----------- |
| `apprise.service_urls` | `List<str>` | Provide the apprise urls for apprise to send notifications to. Can also be provided as environment variable: `APPRISE_URLS`, see example further below. |
| `apprise.config_path` | `str` | If specified, overrides `apprise.service_urls`. Can specify the path to an apprise configuration file |
| `apprise.plugin_paths` | `List<str>` | Provide the plugin paths for apprise to use |
| `apprise.storage_path` | `str` | For persistent storage, specify a path for apprise to use |
| `apprise.custom_title` | `str` | Replace the default message title for apprise notifications |
| `apprise.custom_attachment_path` | `str` | To include a custom attachment to the apprise notification, specify the path to a file | 
| `apprise.on_success` | `bool` | Default: `false`, set to `true` if notifications should be sent on successful export runs |
| `apprise.on_failure` | `bool` | Default: `true`, send notifications if run fails |

`apprise.service_urls` can contain sensitive information and can be specified as an environment variable instead as a string list, example: `export APPRISE_URLS='["json://localhost:8080/notify"]'`.

**If using apprise for notifications, one of `apprise.service_urls` or `apprise.config_path` should be specified.**

## Potential Breaking Upgrades
Below are versions that have major changes to the way configuration or exporter runs.

| Start Version | Target Version | Description |
| ------------- | -------------- | ----------- |
| `< 1.4.X` | `1.5.0` | `assets.verify_ssl` has been moved to `http_config.verify_ssl` and the default value has been updated to `false`. `additional_headers` has been moved to `http_config.additional_headers` |
| `1.6.X` | `vX.X.X` | `assets.modify_markdown` is deprecated — HTML image and attachment link rewrites are now supported, so the markdown-specific name no longer fits. Use `assets.modify_links` instead. The legacy `modify_markdown` key still works but will be removed in a future release. |
| `< 3.0.0` | `3.0.0` | The top-level `minio:` config block is removed. Replace it with an `object_storage:` list entry with `type: minio`. See [Migrating from v2](#migrating-from-v2) for the exact mapping. |

## Running Tests

This project uses [uv](https://docs.astral.sh/uv/) for development. Sync dev dependencies and run the test suite:

```bash
uv sync --all-groups
uv run pytest
```

Or via the [Taskfile](https://taskfile.dev) target:

```bash
task test
```

The pytest run includes coverage by default (configured in `pyproject.toml`). For an HTML coverage report:

```bash
uv run pytest --cov-report=html
open htmlcov/index.html
```

To run only unit tests (skipping integration tests):

```bash
uv run pytest tests/unit
```

To run only the integration tests:

```bash
pytest -m integration
```

## Future Items
1. ~~Be able to pull images locally and place in their respective page folders for a more complete file level backup.~~
2. ~~Include the exporter in a maintained helm chart as an optional deployment. The helm chart is [here](https://github.com/homeylab/helm-charts/tree/main/charts/bookstack).~~
3. ~~Be able to modify markdown links of images to local exported images in their respective page folders for a more complete file level backup.~~
4. ~~Be able to pull attachments locally and place in their respective page folders for a more complete file level backup.~~
5. Export S3 and more options.
6. ~~Filter shelves and books by name - for more targeted backups. Example: you only want to share a book about one topic with an external friend/user.~~
7. Be able to pull media/photos from 3rd party providers like `drawio`
