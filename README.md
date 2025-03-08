# bookstack-file-exporter
Table of Contents
- [bookstack-file-exporter](#bookstack-file-exporter)
  - [Background](#background)
    - [Features](#features)
    - [Use Case](#use-case)
  - [Using This Application](#using-this-application)
    - [Run via Pip](#run-via-pip)
    - [Run via Docker](#run-via-docker)
    - [Run via Helm](#run-via-helm)
    - [Authentication and Permissions](#authentication-and-permissions)
    - [Configuration](#configuration)
  - [Backup Behavior](#backup-behavior)
    - [General](#general)
    - [Images](#images)
    - [Attachments](#attachments)
    - [Modify Markdown Files](#modify-markdown-files)
  - [Object Storage](#object-storage)
    - [Minio Backups](#minio-backups)
  - [Potential Breaking Upgrades](#potential-breaking-upgrades)
  - [Future Items](#future-items)

## Background
_If you encounter any issues, want to request an additional feature, or provide assistance, feel free to open a Github issue._

This tool provides a way to export [Bookstack](https://github.com/BookStackApp/BookStack) pages and their content (_text, images, attachments, metadata, etc._) into a relational parent-child layout locally with an option to push to remote object storage locations. See [Backup Behavior](#backup-behavior) section for more details on how pages are organized. Image and attachment links can also be modified in markdown exports to point to local exported paths.

This small project was mainly created to run as a cron job in k8s but works anywhere. This tool allows me to export my docs in markdown, or other formats like pdf. I use Bookstack's markdown editor as default instead of WYSIWYG editor and this makes my notes portable anywhere even if offline.

### Features
What it does:

- Discover and build relationships between Bookstack `Shelves/Books/Chapters/Pages` to create a relational parent-child layout
- Export Bookstack pages and their content to a `.tgz` archive
- Additional content for pages like their images, attachments, and metadata and can be exported
- The exporter can also [Modify Markdown Files](#modify-markdown-files) to replace image and/or attachment links with local exported paths for a more portable backup
- YAML configuration file for repeatable and easy runs
- Can be run via [Python](#run-via-pip) or [Docker](#run-via-docker)
- Can push archives to remote object storage like [Minio](https://min.io/)
- Basic housekeeping option (`keep_last`) to keep a tidy archive destination
- Can run in application mode (always running) using `run_interval` property. Used for basic scheduling of backups.

Supported backup targets are:

1. local
2. minio
3. s3 (Not Yet Implemented)

Supported backup formats are based on Bookstack API and shown [here](https://demo.bookstackapp.com/api/docs#pages-exportHtml) and below:

1. html
2. pdf
3. markdown
4. plaintext

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
output_path: "bkps/"
assets:
  export_images: false
  export_attachments: false
  modify_markdown: false
  export_meta: false
```

### Run via Pip
The exporter can be installed via pip and run directly.

#### Python Version
_Note: This application is tested and developed on Python version `3.13.2`. The min required version is >= `3.8` but is recommended to install (or set up a venv) a `3.13.2` version._

#### Examples
```bash
python -m pip install bookstack-file-exporter

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

#### Environment Variables
See [Valid Environment Variables](#valid-environment-variables) for more options.

Example:
```bash
export LOG_LEVEL=debug

# using pip
python -m bookstack_file_exporter -c <path_to_config_file>
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

#### Docker Compose
When using the configuration option: `run_interval`, a docker compose set up could be used to run the exporter as an always running application. The exporter will sleep and wait until `{run_interval}` seconds has elapsed before subsequent runs.

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

For object storage configuration, find more information in their respective sections
- [Minio](#minio-backups)

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
http_config:
  verify_ssl: false
  timeout: 30
  backoff_factor: 2.5
  retry_codes: [413, 429, 500, 502, 503, 504]
  retry_count: 5
  additional_headers:
    User-Agent: "test-agent"
minio:
  host: "minio.yourdomain.com"
  access_key: ""
  secret_key: ""
  region: "us-east-1"
  bucket: "mybucket"
  path: "bookstack/file_backups"
  keep_last: 5
output_path: "bkps/"
assets:
  export_images: true
  export_attachments: true
  modify_markdown: false
  export_meta: false
keep_last: 5
run_interval: 0
```

#### Options and Descriptions
More descriptions can be found for each section below:

| Configuration Item | Type | Required | Description |
| ------------------ | ---- | -------- | ----------- |
|  `host` | `str` | `true` | If `http/https` not specified in the url, defaults to `https`. Use `http_config.verify_ssl` to disable certificate checking. |
| `credentials` | `object` | `false` | Optional section where Bookstack tokenId and tokenSecret can be specified. Env variable for credentials may be supplied instead. See [Authentication](#authentication) for more details. |
| `credentials.token_id` | `str`| `false` if specified through env var instead, otherwise `true` | A valid Bookstack tokenId. |
| `credentials.token_secret` | `str` | `false` if specified through env var instead, otherwise `true` | A valid Bookstack tokenSecret. |
| `formats` | `list<str>` | `true` | Which export formats to use for Bookstack page content. Valid options are: `["markdown", "html", "pdf", "plaintext"]`|
| `output_path` | `str` | `false` | Optional (default: `cwd`) which directory (relative or full path) to place exports. User who runs the command should have access to read/write to this directory. This directory and any parent directories will be attempted to be created if they do not exist. If not provided, will use current run directory by default. If using docker, this option can be omitted. |
| `assets` | `object` | `false` | Optional section to export additional assets from pages. |
| `assets.export_images` | `bool` | `false` | Optional (default: `false`), export all images for a page to an `image` directory within page directory. See [Backup Behavior](#backup-behavior) for more information on layout |
| `assets.export_attachments` | `bool` | `false` | Optional (default: `false`), export all attachments for a page to an `attachments` directory within page directory. See [Backup Behavior](#backup-behavior) for more information on layout |
| `assets.modify_markdown` | `bool` | `false` | Optional (default: `false`), modify markdown files to replace image links with local exported image paths. This requires `assets.export_images` to be `true` in order to work. See [Modify Markdown Files](#modify-markdown-files) for more information. |
| `assets.export_meta` | `bool` | `false` | Optional (default: `false`), export of metadata about the page in a json file. |
| `http_config` | `object` | `false` | Optional section to override default http configuration. |
| `http_config.verify_ssl` | `bool` | `false` | Optional (default: `false`), whether or not to verify ssl certificates if using https. |
| `http_config.timeout` | `int` | `false` | Optional (default: `30`), set the timeout, in seconds, for http requests. |
| `http_config.retry_count` | `int` | `false` | Optional (default: `5`), the number of http retries after initial failure. |
| `http_config.retry_codes` | `List[int]` | `false` | Optional (default: `[413, 429, 500, 502, 503, 504]`), which http response status codes trigger a retry. |
| `http_config.backoff_factor` | `float` | `false` | Optional (default: `2.5`), set the backoff_factor for http request retries. Default backoff_factor `2.5` means we wait 5, 10, 20, and then 40 seconds (with default `http_config.retry_count: 5`) before our last retry. This should allow for per minute rate limits to be refreshed. |
| `http_config.additional_headers` | `object` | `false` | Optional (default: `{}`), specify key/value pairs that will be added as additional headers to http requests. |
| `keep_last` | `int` | `false` | Optional (default: `0`), if exporter can delete older archives. valid values are:<br>- set to `-1` if you want to delete all archives after each run (useful if you only want to upload to object storage)<br>- set to `1+` if you want to retain a certain number of archives<br>- `0` will result in no action done. |
| `run_interval` | `int` | `false` | Optional (default: `0`). If specified, exporter will run as an application and pause for `{run_interval}` seconds before subsequent runs. Example: `86400` seconds = `24` hours or run once a day. Setting this property to `0` will invoke a single run and exit. Used for basic scheduling of backups. |
| `minio` | `object` | `false` | Optional [Minio](#minio-backups) configuration options. |

#### Valid Environment Variables
General
- `LOG_LEVEL`: default: `info`. Provide a valid log level: info, debug, warning, error.

[Bookstack Credentials](#authentication)
- `BOOKSTACK_TOKEN_ID`
- `BOOKSTACK_TOKEN_SECRET`

[Minio Credentials](#authentication-1)
- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`

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
Empty/New Pages will be ignored since they have not been modified yet from creation and are empty but also do not have a valid slug. 

Example from Bookstack API:
```
{
    ...
    "name": "New Page",
    "slug": "",
    ...
}
```

### Images
Images will be dumped in a separate directory, `images` within the page parent (book/chapter) directory it belongs to. The relative path will be `{parent}/images/{page}/{image_name}`. As shown earlier:

```
bookstack_export_2023-11-28_06-24-25/programming/react/images/basics/dwwimage.png
bookstack_export_2023-11-28_06-24-25/programming/react/images/basics/NzZimage.png
bookstack_export_2023-11-28_06-24-25/programming/react/images/nextjs/next1.png
bookstack_export_2023-11-28_06-24-25/programming/react/images/nextjs/tips.png
```

**Note you may see old images in your exports. This is because, by default, Bookstack retains images/drawings that are uploaded even if no longer referenced on an active page. Admins can run `Cleanup Images` in the Maintenance Settings or via [CLI](https://www.bookstackapp.com/docs/admin/commands/#cleanup-unused-images) to remove them.**

If an API call to get an image or its metadata fails, the exporter will skip the image and log the error. If using `modify_markdown` option, the image links in the document will be untouched and in its original form. All API calls are retried 3 times after initial failure.

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

If an API call to get an attachment or its metadata fails, the exporter will skip the attachment and log the error. If using `modify_markdown` option, the attachment links in the document will be untouched and in its original form. All API calls are retried 3 times after initial failure.

### Modify Markdown Files
**To use this feature, `assets.export_images` should be set to `true` and/or `assets.export_attachments`**

The configuration item, `assets.modify_markdown`, can be set to `true` to modify markdown files to replace image and attachment url links with local exported image paths. This feature allows for you to make your `markdown` exports much more portable.

Page (parent) -> Images (Children) relationships are created and then each image/attachment url is replaced with its own respective local export path. Example:
```
## before
[![pool-topology-1.png](https://demo.bookstack/uploads/images/gallery/2023-07/scaled-1680-/pool-topology-1.png)](https://demo.bookstack/uploads/images/gallery/2023-07/pool-topology-1.png)

## after
[![pool-topology-1.png](images/{page_name}/pool-topology-1.png)](https://demo.bookstack/uploads/images/gallery/2023-07/pool-topology-1.png)
```
This allows the image or attachment to be found locally within the export files and allow your `markdown` docs to have all the assets display properly like it would normally would.

**Note: This will work properly if your pages are using the notation used by Bookstack for Markdown image links, example: ` [![image alt text](Bookstack Markdown image URL link)](anchor/url link)` The `(anchor/url link)` is optional. For attachments the format is: `[file](url link)`**

## Object Storage
Optionally, target(s) can be specified to upload generated archives to a remote location. Supported object storage providers can be found below:
- [Minio](#minio-backups)

### Minio Backups
Optionally, look at `examples/minio_config.yml` folder of the github repo for more examples. 

#### Authentication
Credentials can be specified directly in the `minio` configuration section or as environment variables. If specified in config and env, env variable will take precedence.

Environment variables:
- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`

#### Example
```yaml
minio:
    host: "minio.yourdomain.com"
    region: "us-east-1"
    bucket: "mybucket"
    access_key: ""
    secret_key: ""
    path: "bookstack/file_backups"
    keep_last: 5
```
#### Configuration
| Item | Type | Required | Description |
| ---- | ---- | -------- | ----------- |
| `host` | `str` | `true` | Hostname for minio. A host/ip + port combination is also allowed, example: `minio.yourdomain.com:8443` |
| `region` | `str` | `true` | This is required since minio api appears to require it. Set to the region your bucket resides in, if unsure, try `us-east-1` |
| `bucket` | `str` | `true` | Bucket to upload to |
| `access_key` | `str` | `false` if specified through env var instead, otherwise `true` | Access key for the minio instance |
| `secret_key` | `str` | `false` if specified through env var, otherwise `true` | Secret key for the minio instance |
| `path` | `str` | `false` | Optional, path of the backup to use. Will use root bucket path if not set. `<bucket_name>:/<path>/bookstack-<timestamp>.tgz` |
| `keep_last` | `int` | `false` | Optional (default: `0`), if exporter can delete older archives in minio.<br>- set to `1+` if you want to retain a certain number of archives<br>-  `0` will result in no action done |

## Potential Breaking Upgrades
Below are versions that have major changes to the way configuration or exporter runs.

| Start Version | Target Version | Description |
| ------------- | -------------- | ----------- |
| `< 1.4.X` | `1.5.0` | `assets.verify_ssl` has been moved to `http_config.verify_ssl` and the default value has been updated to `false`. `additional_headers` has been moved to `http_config.additional_headers` |

## Future Items
1. ~~Be able to pull images locally and place in their respective page folders for a more complete file level backup.~~
2. ~~Include the exporter in a maintained helm chart as an optional deployment. The helm chart is [here](https://github.com/homeylab/helm-charts/tree/main/charts/bookstack).~~
3. ~~Be able to modify markdown links of images to local exported images in their respective page folders for a more complete file level backup.~~
4. ~~Be able to pull attachments locally and place in their respective page folders for a more complete file level backup.~~
5. Export S3 and more options.
6. Filter shelves and books by name - for more targeted backups. Example: you only want to share a book about one topic with an external friend/user.
7. Be able to pull media/photos from 3rd party providers like `drawio`