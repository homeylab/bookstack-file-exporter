# bookstack-file-exporter
## Background
_Features are actively being developed. See `Future Items` section for more details. Open an issue for a feature request._

This tool provides a way to export [Bookstack]() pages and their contents (_images, metadata, etc._) to a directory-tree layout locally with an option to push to remote object storage locations. See [Backup Behavior](#backup-behavior) section for more details on how pages are organized.

This small project was mainly created to run as a cron job in k8s but works anywhere. This tool allows me to export my docs in markdown, or other formats like pdf. I use Bookstack's markdown editor as default instead of WYSIWYG editor and this makes my notes portable anywhere even if offline.

### Features
What it does:

- Build relationships between Bookstack `Shelves/Books/Chapters/Pages` to create a relational directory-tree layout
- Export Bookstack pages and their content to a `.tgz` archive
- Additional content for pages like their images and metadata and can be exported
- YAML configuration file for repeatable and easy runs
- Can be run via [Python](#run-via-pip) or [Docker](#run-via-docker)
- Can push archives to remote object storage like [Minio](https://min.io/)
- Basic housekeeping option (`keep_last`) to keep a tidy archive destination


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
The main use case is to backup all docs in a directory-tree format to cover the scenarios:

1. Offline copy wanted.
2. Back up at a file level as an accessory or alternative to disk and volume backups.
3. Share docs with another person to keep locally.
4. Migrate to Markdown documenting for simplicity.
5. Provide an easy way to do automated file backups locally, in docker, or kubernetes.

## Using This Application
Ensure a valid configuration is provided when running this application. See [Configuration](#Configuration) section for more details.

### Run via Pip
```bash
python -m pip install bookstack-file-exporter

# if you already have python bin directory in your path
bookstack-file-exporter -c <path_to_config_file>

# using pip
python -m bookstack_file_exporter -c <path_to_config_file>
```
Command line options:
| option | required | description |
| ------ | -------- | ----------- |
|`-c`, `--config-file`|True|Relative or Absolute path to a valid configuration file. This configuration file is checked against a schema for validation.|
|`-v`, `--log-level` |False, default: info|Provide a valid log level: info, debug, warning, error.|

_Note: This application is tested and developed on Python version `3.12.X`. It will probably work for >= `3.8` but is recommended to install (or set up a venv) a `3.12.X` version._

### Run Via Docker
Example:

```bash
docker run \
    --user ${USER_ID}:${USER_GID} \
    -v $(pwd)/config.yml:/export/config/config.yml:ro \
    -v $(pwd)/bkps:/export/dump \
    homeylab/bookstack-file-exporter:latest
```
Minimal example with object storage upload: 
```bash
docker run \
    -v $(pwd)/config.yml:/export/config/config.yml:ro \
    homeylab/bookstack-file-exporter:latest
```

Tokens and other options can be specified, example:
```bash
# '-e' flag for env vars
# --user flag to override the uid/gid for created files
docker run \
    -e LOG_LEVEL='debug' \
    -e BOOKSTACK_TOKEN_ID='xyz' \
    -e BOOKSTACK_TOKEN_SECRET='xyz' \
    --user 1000:1000 \
    -v $(pwd)/config.yml:/export/config/config.yml:ro \
    -v $(pwd)/bkps:/export/dump \
    homeylab/bookstack-file-exporter:latest
```
Bind Mounts:
| purpose | static docker path | description | example |
| ------- | ------------------ | ----------- | ------- |
| `config` | `/export/config/config.yml` | A valid configuration file |`-v /local/yourpath/config.yml:/export/config/config.yml:ro`|
| `dump` | `/export/dump` | Directory to place exports. **This is optional when using remote storage option(s)**. Omit if you don't need a local copy. | `-v /local/yourpath/bkps:/export/dump` |

### Authentication
**Note visibility of pages is based on user**, so use a user that has access to pages you want to back up.

Ref: [https://demo.bookstackapp.com/api/docs#authentication](https://demo.bookstackapp.com/api/docs#authentication)

Provide a tokenId and a tokenSecret as environment variables or directly in the configuration file.
- `BOOKSTACK_TOKEN_ID`
- `BOOKSTACK_TOKEN_SECRET`

Env variables for credentials will take precedence over configuration file options if both are set.

**For object storage authentication**, find the relevant sections further down in their respective sections.

### Configuration
See below for an example and explanation. Optionally, look at `examples/` folder of the github repo for more examples. Ensure [Authentication](#authentication) has been set up beforehand for required credentials.

For object storage configuration, find more information in their respective sections
- [Minio](#minio-backups)

> Schema and values are checked so ensure proper settings are provided. As mentioned, credentials can be specified as environment variables instead if preferred.

#### Just Run
Below is an example configuration to just get quickly running without any additional options.

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
output_path: "bkps/"
assets:
    export_images: false
    export_meta: false
    verify_ssl: true
keep_last: 5
 ```

#### Full Example
Below is an example configuration that shows all possible options,

```yaml
host: "https://bookstack.yourdomain.com"
credentials:
    token_id: ""
    token_secret: ""
additional_headers:
  test: "test"
  test2: "test2"
  User-Agent: "test-agent"
formats:
  - markdown
  - html
  - pdf
  - plaintext
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
  export_meta: false
  verify_ssl: true
keep_last: 5
```

#### Options and Descriptions
More descriptions can be found for each section below:

| Configuration Item | Type | Required | Description |
| ------------------ | ---- | -------- | ----------- |
|  `host` | `str` | `true` | If `http/https` not specified in the url, defaults to `https`. Use `assets.verify_ssl` to disable certificate checking. |
| `credentials` | `object` | `false` | Optional section where Bookstack tokenId and tokenSecret can be specified. Env variable for credentials may be supplied instead. See [Authentication](#authentication) for more details. |
| `credentials.token_id` | `str`| `true` if `credentials` | If `credentials` section is given, this should be a valid tokenId |
| `credentials.token_secret` | `str` | `true` if `credentials`| If `credentials` section is given, this should be a valid tokenSecret | 
| `additional_headers` | `object` | `false` | Optional section where key/value for pairs can be specified to use in Bookstack http request headers.
| `formats` | `list<str>` | `true` | Which export formats to use for Bookstack page content. Valid options are: `["markdown", "html", "pdf", "plaintext"]`|
| `output_path` | `str` | `false` | Optional (default: `cwd`) which directory (relative or full path) to place exports. User who runs the command should have access to read/write to this directory. If not provided, will use current run directory by default |
| `assets` | `object` | `false` | Optional section to export additional assets from pages. |
| `assets.export_images` | `bool` | `false` | Optional (default: `false`), export all images for a page to an `image` directory within page directory. See [Backup Behavior](#backup-behavior) for more information on layout |
| `assets.export_meta` | `bool` | `false` | Optional (default: `false`), export of metadata about the page in a json file |
| `assets.verify_ssl` | `bool` | `false` | Optional (default: `true`), whether or not to check ssl certificates when requesting content from Bookstack host |
| `keep_last` | `int` | `false` | Optional (default: `None`), if exporter can delete older archives. valid values are:<br>- set to `-1` if you want to delete all archives after each run (useful if you only want to upload to object storage)<br>- set to `1+` if you want to retain a certain number of archives<br>- `0` will result in no action done |
| `minio` | `object` | `false` | Optional [Minio](#minio-backups) configuration options. |

### Backup Behavior
Backups are exported in `.tgz` format and generated based off timestamp. Export names will be in the format: `%Y-%m-%d_%H-%M-%S` (Year-Month-Day_Hour-Minute-Second). *Files are first pulled locally to create the tarball and then can be sent to object storage if needed*. Example file name: `bookstack_export_2023-09-22_07-19-54.tgz`.

The exporter can also do housekeeping duties and keep a configured number of archives and delete older ones. See `keep_last` property in the [Configuration](#options-and-descriptions) section. Object storage provider configurations include their own `keep_last` property for flexibility. 

For file names, `slug` names (from Bookstack API) are used, as such certain characters like `!`, `/` will be ignored and spaces replaced from page names/titles.

All sub directories will be created as required during the export process.
```
Shelves --> Books --> Chapters --> Pages

## Example
kafka (shelf)
---> controller (book)
    ---> settings (chapter)
        ---> retention-settings (page)
            ---> retention-settings.md
            ---> retention-settings_meta.json
        ---> compression (page)
            ---> compression.html
            ---> compression.pdf
            ---> compression_meta.json
        ---> optional-config (page)
            ...
        ---> main (page)
            ...
---> broker (book)
    ---> settings (page)
        ...
    ---> deploy (page)
        ...
kafka-apps (shelf)
---> schema-registry (book)
    ---> protobuf (page)
        ...
    ---> settings (page)
        ...

## Example with image layout
unassigned (Used for books with no shelf)
---> test (book)
    ---> test_page (page)
        ---> test_page.md
        ---> test_page.pdf
        ---> images (image_dir)
            ---> img-001.png
            ---> img-002.png
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

bookstack_export_2023-11-20_08-00-29/programming/react/basics/basics.md
bookstack_export_2023-11-20_08-00-29/programming/react/basics/basics.html
bookstack_export_2023-11-20_08-00-29/programming/react/basics/basics.pdf
bookstack_export_2023-11-20_08-00-29/programming/react/basics/basics.txt
bookstack_export_2023-11-20_08-00-29/programming/react/basics/basics_meta.json
bookstack_export_2023-11-20_08-00-29/programming/react/basics/images/YKvimage.png
bookstack_export_2023-11-20_08-00-29/programming/react/basics/images/dwwimage.png
bookstack_export_2023-11-20_08-00-29/programming/react/basics/images/NzZimage.png
bookstack_export_2023-11-20_08-00-29/programming/react/basics/images/Mymimage.png
bookstack_export_2023-11-20_08-00-29/programming/react/nextjs/nextjs.md
bookstack_export_2023-11-20_08-00-29/programming/react/nextjs/nextjs.html
bookstack_export_2023-11-20_08-00-29/programming/react/nextjs/nextjs.pdf
bookstack_export_2023-11-20_08-00-29/programming/react/nextjs/nextjs.txt
bookstack_export_2023-11-20_08-00-29/programming/react/nextjs/nextjs_meta.json
```

Books without a shelf will be put in a shelve folder named `unassigned`.

Empty/New Pages will be ignored since they have not been modified yet from creation and are empty but also do not have a valid slug. Example:
```
{
    ...
    "name": "New Page",
    "slug": "",
    ...
}
```

You may notice some directories (books) and/or files (pages) in the archive have a random string at the end, example - `nKA`: `user-and-group-management-nKA`. This is expected and is because there were resources with the same name created in another shelve and bookstack adds a string at the end to ensure uniqueness.

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
| `keep_last` | `int` | `false` | Optional (default: `None`), if exporter can delete older archives in minio.<br>- set to `1+` if you want to retain a certain number of archives<br>-  `0` will result in no action done |

## Future Items
1. ~~Be able to pull images locally and place in their respective page folders for a more complete file level backup.~~
2. ~~Include the exporter in a maintained helm chart as an optional deployment. The helm chart is [here](https://github.com/homeylab/helm-charts/tree/main/charts/bookstack).~~
3. Be able to modify markdown links of images to local exported images in their respective page folders for a more complete file level backup.
4. Be able to pull attachments locally and place in their respective page folders for a more complete file level backup.
5. Export S3 and more options.
6. Filter shelves and books by name - for more targeted backups. Example: you only want to share a book about one topic with an external friend/user.
7. Be able to pull media/photos from 3rd party providers like `drawio`