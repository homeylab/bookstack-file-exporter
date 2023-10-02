# bookstack-file-exporter

_This is project is still under active development. Functionality is there and is relatively stable at this time._

This tool provides a way to export Bookstack pages in a folder-tree layout locally with an option to push to remote object storage locations.

This small project was mainly created to run as a cron job in k8s but works anywhere. This would allow me to export my docs in markdown, or other formats like pdf. I use Bookstack's markdown editor as default instead of WYSIWYG editor and this makes my notes portable anywhere even if offline.

The main use case is to backup all docs in a folder-tree format to cover the scenarios:

1. Offline copy wanted.
2. Back up at a file level as an accessory or alternative to disk and volume backups.
3. Share docs with another person to keep locally.
4. Migrate to Markdown documenting for simplicity.
5. Provide an easy way to do automated file backups locally, in docker, or kubernetes.

Supported backup formats are

1. local
2. minio
3. s3 (Not Yet Implemented)

Backups are exported in `.tgz` format and generated based off timestamp. Export names will be in the format: `%Y-%m-%d_%H-%M-%S` (Year-Month-Day_Hour-Minute-Second). *Files are first pulled locally to create the tarball and then can be sent to object storage if needed*. Example file name: `bookstack_export_2023-09-22_07-19-54.tgz`.

This script can be run directly via cli as a pip module.
```
# if you already have python bin directory in your path
bookstack-file-exporter -c <path_to_config_file>

# using pip
python -m bookstack_file_exporter -c <path_to_config_file>
```

## Using This Application

### Run via Pip
Note: This application is tested and developed on Python `3.11.X`. It will probably work for >= `3.8` but is recommended to install (or set up a venv) a `3.11.X` version.

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

### Run Via Docker
Example
```bash
docker run \
    --user ${USER_ID}:${USER_GID} \
	-v $(pwd)/local/config.yml:/export/config/config.yml:ro \
	-v $(pwd)/bkps:/export/dump \
	bookstack-file-exporter:0.0.1
```
Required Options:
| option | description |
| `config.yml` file mount | Provide a valid configuration file. Specified in example as read only: `-v ${CURDIR}/local/config.yml:/export/config/config.yml:ro`, `${USER_LOCAL_PATH}:${STATIC_DOCKER_PATH}` |
| `dump` file mount | Directory to place exports. Specified in example: `-v ${CURDIR}/bkps:/export/dump`, `${USER_LOCAL_PATH}:${STATIC_DOCKER_PATH}` |

Tokens and other options can be specified, example:
```bash
# '-e' flag for env vars
# --user flag to override the uid/gid for created files
docker run \
	-e LOG_LEVEL='debug' \
    -e BOOKSTACK_TOKEN_ID='xyz' \
    -e BOOKSTACK_TOKEN_SECRET='xyz' \
	--user 1000:1000 \
	-v $(pwd)/local/config.yml:/export/config/config.yml:ro \
	-v $(pwd):/export/dump \
	bookstack-file-exporter:0.0.1
```

### Authentication
**Note visibility of pages is based on user**, so use a user that has access to pages you want to back up

Ref: [https://demo.bookstackapp.com/api/docs#authentication](https://demo.bookstackapp.com/api/docs#authentication)

Provide a tokenId and a tokenSecret as environment variables or directly in the configuration file.
- `BOOKSTACK_TOKEN_ID`
- `BOOKSTACK_TOKEN_SECRET`

For object storage authentication, find the relevant sections further down in this document.

### Configuration file
See below for an example and explanation. Optionally, look at `examples/` folder for more. 

Schema and values are checked so ensure proper settings are provided.
```
# if http/https not specified, defaults to https
# if you put http here, it will try verify=false, to not check certs
host: "https://bookstack.yourdomain.com"

# You could optionally set the bookstack token_id and token_secret here instead of env
# If env variable is also supplied, env variable will take precedence
credentials:
    token_id: ""
    token_secret: ""

# additional headers to add, examples below
additional_headers:
  test: "test"
  test2: "test2"
  User-Agent: "test-agent"

# supported formats from bookstack below
# valid formats: markdown, html, pdf, plaintext
# you can specify one or as many as you'd like
formats:
  - markdown
  - html
  - pdf
  - plaintext

# optional minio configuration
# If not required, you should omit/comment out the section
# You can specify env vars instead for access and secret key
# See Minio Backups section of this doc for more info on required fields
minio_config:
  host: "minio.yourdomain.com"
  access_key: ""
  secret_key: ""
  region: "us-east-1"
  bucket: "mybucket"
  path: "bookstack/backups"

# output directory for the exported archive
# relative or full path
# User who runs the command should have access to write and create sub folders in this directory
# optional, if not provided, will use current run directory by default
output_path: "bkps/"

# optional export of metadata about the page in a json file
# this metadata contains general information about the page
# like: last update, owner, revision count, etc.
# omit this or set to false if not needed
export_meta: true

# optional if using object storage targets
# After uploading to object storage targets, choose to clean up local files
# delete the archive from local filesystem
# will not be cleaned up if set to false or omitted
clean_up: true
```

### Backup Behavior
We will use slug names (from Bookstack API) by default, as such certain characters like `!`, `/` will be ignored and spaces replaced.

All sub directories will be created as required during the export process.

```
Shelves --> Books --> Chapters --> Pages

## Example
kafka
---> controller
    ---> settings
        ---> logs (chapter)
            ---> retention.md
            ---> compression.pdf
            ---> something.html
            ---> other.txt
        ---> optional
        ---> main
    ---> deploy
---> broker
    ---> settings
    ---> deploy
---> schema-registry
    ---> protobuf
    ---> settings
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
When specifying `minio_config` in the configuration file, these fields are required in the file:
```
# a host/ip + port combination is also allowed
# example: "minio.yourdomain.com:8443"
host: "minio.yourdomain.com"

# this is required since minio api appears to require it
# set to the region your bucket resides in
# if unsure, try "us-east-1" first
region: "us-east-1"

# bucket to upload to
bucket "mybucket"
```

These fields are optional:
```
# access key for the minio instance
# optionally set as env variable instead
access_key: ""

# secret key for the minio instance
# optionally set as env variable instead
secret_key: ""

# the path of the backup
# in example below, the exported archive will appear in: `<bucket_name>:/bookstack/backups/bookstack-<timestamp>.tgz`
path: "bookstack/backups"
```

As mentioned you can optionally set access and secret key as env variables. If both are specified, env variable will take precedence.
- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`

## Future Items
1. Be able to pull media/photos locally and place in their respective page folders for a more complete file level backup.
2. Include the exporter in a maintained helm chart as an optional deployment. The helm chart is [here](https://github.com/homeylab/helm-charts/tree/main/charts/bookstack).
3. Export S3 or more options.