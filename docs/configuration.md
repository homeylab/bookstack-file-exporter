# Configuration

[← Back to README](../README.md#documentation)

> [!NOTE]
> Credentials: BookStack API token setup (role permissions + generating `tokenId`/`tokenSecret`) lives in [Authentication & Permissions](getting-started.md#authentication-and-permissions). Object-storage credentials are documented in [Remote Storage](remote-storage.md#object-storage-upload).

- [Full Example](#full-example)
- [Options and Descriptions](#options-and-descriptions)
- [Valid Environment Variables](#valid-environment-variables)
- [Export Level](#export-level)
- [Parallel Export](#parallel-export)

_Ensure [Authentication](getting-started.md#authentication-and-permissions) has been set up beforehand for required credentials._ For a simple config example to run quickly, refer to the one in the [Using This Application](getting-started.md#using-this-application) section.

A full example is also shown below. _Optionally, look at `examples/` folder of the github repo for more examples with long descriptions_.

For object storage configuration, find more information in the [Object Storage Upload](remote-storage.md#object-storage-upload) section.

**Schema and values are checked so ensure proper settings are provided. As mentioned, credentials can be specified as environment variables instead if preferred.**

## Full Example
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

## Options and Descriptions
More descriptions can be found for each section below:

| Configuration Item | Type | Required | Description |
| ------------------ | ---- | -------- | ----------- |
|  `host` | `str` | `true` | If `http/https` not specified in the url, defaults to `https`. Use `http_config.verify_ssl` to disable certificate checking. |
| `credentials` | `object` | `false` | Optional section where Bookstack tokenId and tokenSecret can be specified. Env variable for credentials may be supplied instead. See [Authentication](getting-started.md#authentication-and-permissions) for more details. |
| `credentials.token_id` | `str`| `false` if specified through env var instead, otherwise `true` | A valid Bookstack tokenId. |
| `credentials.token_secret` | `str` | `false` if specified through env var instead, otherwise `true` | A valid Bookstack tokenSecret. |
| `formats` | `list<str>` | `true` | Which export formats to use for BookStack content. Valid options are: `["markdown", "html", "pdf", "plaintext", "zip"]`|
| `export_level` | `str` | `false` | Optional (default: `pages`). Export granularity. See [Export Level](#export-level) for details. Valid options: `pages`, `books`, `chapters`. |
| `export_workers` | `int` | `false` | Optional (default: `1`). Number of nodes (pages/books/chapters) fetched in parallel; `1` keeps the original serial behavior. Raising it speeds up large exports but increases concurrent API load. See [Parallel Export](#parallel-export) for tuning and rate-limit guidance. |
| `output_path` | `str` | `false` | Optional (default: `cwd`) which directory (relative or full path) to place exports. User who runs the command should have access to read/write to this directory. This directory and any parent directories will be attempted to be created if they do not exist. If not provided, will use current run directory by default. If using docker, this option can be omitted. |
| `assets` | `object` | `false` | Optional section to export additional assets from pages. |
| `assets.export_images` | `bool` | `false` | Optional (default: `false`), export all images to an `images` directory. Works at all export levels: per-page directory at `pages` level; per-book or per-chapter directory at `books`/`chapters` level. See [Backup Behavior](backup-behavior.md#backup-behavior) for more information on layout |
| `assets.export_attachments` | `bool` | `false` | Optional (default: `false`), export all attachments to an `attachments` directory. Works at all export levels: per-page directory at `pages` level; per-book or per-chapter directory at `books`/`chapters` level. See [Backup Behavior](backup-behavior.md#backup-behavior) for more information on layout |
| `assets.modify_links` | `bool` | `false` | Optional (default: `false`). Rewrites image and attachment URLs in markdown AND html exports to local relative paths. Requires `assets.export_images` and/or `assets.export_attachments` to be `true`. Controls link *rewriting* only — assets are downloaded whenever their export flag is set, regardless of `modify_links`. Only applies to `markdown` and `html` formats; pdf, plaintext, and zip are not eligible. Legacy key `modify_markdown` still accepted (deprecated); will be removed in a future version. See [Modify Links](backup-behavior.md#modify-links) for more information. |
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
| `health_port` | `int` | `false` | Optional (default: unset). Scheduled mode only (`run_interval` or `run_schedule`). When set, the daemon serves an opt-in `GET /healthz` endpoint on this port. No server is started unless set; ignored in one-shot mode. See [Health Endpoint](getting-started.md#health-endpoint). |
| `health_host` | `str` | `false` | Optional (default: `0.0.0.0`). Bind address for the `health_port` server. Set to `127.0.0.1` or a specific NIC to restrict exposure on a multi-homed host. Only used when `health_port` is set. |
| `object_storage` | `list` | `false` | Optional list of object storage upload targets. See [Object Storage Upload](remote-storage.md#object-storage-upload) for details. |
| `notifications` | `object` | `false` | Optional [notification](notifications.md#notifications) configuration options. |
| `filters` | `object` | `false` | Optional per-resource-type regex filters (include/exclude lists). See [Filters](filters.md#filters) for details. |
| `filters.exclude_unassigned_books` | `bool` | `false` | Optional (default: `false`). When `true`, drop all books that are not on any shelf, independent of the `books` patterns. See [Filters](filters.md#filters) for details. |

## Valid Environment Variables
General
- `LOG_LEVEL`: default: `info`. Provide a valid log level: info, debug, warning, error.
- `LOG_FORMAT`: default: `text`. Set to `json` for JSON Lines output.

[Bookstack Credentials](getting-started.md#authentication-and-permissions)
- `BOOKSTACK_TOKEN_ID`
- `BOOKSTACK_TOKEN_SECRET`

[Object Storage Credentials](remote-storage.md#object-storage-upload)
- `MINIO_ACCESS_KEY` — default MinIO access key; shared by all `minio` targets (v2-compatible). For distinct per-target creds, use `access_key_env`/`secret_key_env`.
- `MINIO_SECRET_KEY` — default MinIO secret key (shared, as above)
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

