# bookstack-file-exporter

> [!NOTE]
> This documentation reflects the branch, tag, or commit you are currently viewing; the default branch (`main`) may describe unreleased changes.
> For docs matching your installed version, use the branch/tag dropdown to switch to your release tag. See [Releases](https://github.com/homeylab/bookstack-file-exporter/releases) for the list of published versions.

Table of Contents
- [Background](#background)
  - [Features](#features)
  - [Use Case](#use-case)
- [Documentation](#documentation)
- [Potential Breaking Upgrades](#potential-breaking-upgrades)
- [Future Items](#future-items)

## Background
_If you encounter any issues, want to request an additional feature, or provide assistance, feel free to open a Github issue._

This tool provides a way to export [Bookstack](https://github.com/BookStackApp/BookStack) pages and their content (_text, images, attachments, metadata, etc._) into a relational parent-child layout locally with an option to push to remote object storage locations. See [Backup Behavior](docs/backup-behavior.md#backup-behavior) section for more details on how pages are organized. Image and attachment links can also be modified in markdown and html exports to point to local exported paths.

This small project was mainly created to run as a cron job in k8s but works anywhere. This tool allows me to export my docs in markdown, or other formats like pdf. I use Bookstack's markdown editor as default instead of WYSIWYG editor and this makes my notes portable anywhere even if offline.

### Features
What it does:

- Discover and build relationships between Bookstack `Shelves/Books/Chapters/Pages` to create a relational parent-child layout
- Export Bookstack pages and their content to a `.tgz` archive
- Additional content for pages like their images, attachments, and metadata and can be exported
- The exporter can also [Modify Links](docs/backup-behavior.md#modify-links) to replace image and/or attachment links with local exported paths for a more portable backup
- Fine grained filtering and selectable export levels.
- YAML configuration file for repeatable and easy runs
- Can be run via [Python](docs/getting-started.md#run-via-pip) or [Docker](docs/getting-started.md#run-via-docker)
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

## Documentation
Detailed docs live under [`docs/`](docs/):

- [Getting Started](docs/getting-started.md) — install via Pip/Docker/Helm, run modes, scheduling, health endpoint, authentication
- [Configuration](docs/configuration.md) — full `config.yml` reference, all options, environment variables, export level, parallel export
- [Filters](docs/filters.md) — include/exclude shelves, books, chapters, pages by name
- [Backup Behavior](docs/backup-behavior.md) — archive layout, file naming, images, attachments, modify-links
- [Remote Storage](docs/remote-storage.md) — MinIO / S3 upload, credential resolution, multi-target behavior, v2→v3 migration
- [Notifications](docs/notifications.md) — apprise notifications on export success/failure

## Potential Breaking Upgrades
Below are versions that have major changes to the way configuration or exporter runs.

| Start Version | Target Version | Description |
| ------------- | -------------- | ----------- |
| `< 1.4.X` | `1.5.0` | `assets.verify_ssl` has been moved to `http_config.verify_ssl` and the default value has been updated to `false`. `additional_headers` has been moved to `http_config.additional_headers` |
| `1.6.X` | `vX.X.X` | `assets.modify_markdown` is deprecated — HTML image and attachment link rewrites are now supported, so the markdown-specific name no longer fits. Use `assets.modify_links` instead. The legacy `modify_markdown` key still works but will be removed in a future release. |
| `< 3.0.0` | `3.0.0` | The top-level `minio:` config block is removed. Replace it with an `object_storage:` list entry using the flat schema (`name`, `endpoint`, `prefix`, `ambient_auth`, etc — no `type` field). See [Migrating from v2](docs/remote-storage.md#migrating-from-v2) for the exact mapping. |

## Future Items
1. ~~Be able to pull images locally and place in their respective page folders for a more complete file level backup.~~
2. ~~Include the exporter in a maintained helm chart as an optional deployment. The helm chart is [here](https://github.com/homeylab/helm-charts/tree/main/charts/bookstack).~~
3. ~~Be able to modify markdown links of images to local exported images in their respective page folders for a more complete file level backup.~~
4. ~~Be able to pull attachments locally and place in their respective page folders for a more complete file level backup.~~
5. ~~Export S3 and more options~~.
6. ~~Filter shelves and books by name - for more targeted backups. Example: you only want to share a book about one topic with an external friend/user.~~
7. Be able to pull media/photos from 3rd party providers like `drawio`
