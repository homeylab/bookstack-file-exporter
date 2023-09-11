# bookstack-file-exporter
This tool provides a way to export bookstack pages in a folder-tree layout into object storage or locally.

This small project was mainly created to run as a cronjob in k8s and also run locally if needed. This would allow me to export my docs in markdown (or other of your preference) which I use for most of my notes. 

The main use case is to backup all docs in a folder-tree format to cover scenarios:

1. Offline copy wanted
2. Back up at a file level as an accessory/alternative to disk/volume backups
3. Potentially deprecating bookstack

Supported backup formats are

1. local
2. minio
3. s3 (wip not yet)

Backups are exported in `.tgz` format and generated based off timestamp. Files are first pulled locally to create the tarball and then can be sent to object storage if needed. This script can be run directly via cli

## Using This Application

Note visibility of pages is based on user, so use a user that has access to pages you want to back up

### Authentication
Ref: [https://demo.bookstackapp.com/api/docs#authentication](https://demo.bookstackapp.com/api/docs#authentication)

Provide a tokenId and a tokenSecret

### Backup Behavior
We will use slug names (directory/file safe naming) by default, as such certain characters like `!`, `/` will be ignored and spaces replaced.

```
Shelves --> Books --> Chapters --> Pages

## Example
kafka
---> controller
    ---> settings
    ---> deploy
---> broker
    ---> settings
    ---> deploy
---> schema-registry
    ---> protobuf
    ---> settings
```