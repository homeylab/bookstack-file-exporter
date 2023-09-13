# bookstack-file-exporter
**WIP** not yet complete. This is project is still under active development but has made significant progress.

This tool provides a way to export Bookstack pages in a folder-tree layout into object storage or locally.

This small project was mainly created to run as a cronjob in k8s but also run locally if needed. This would allow me to export my docs in markdown, or other formats like pdf. I use Bookstack's markdown editor as default instead of WYSIWYG editor and this makes my notes portable anywhere even if offline.

The main use case is to backup all docs in a folder-tree format to cover the scenarios:

1. Offline copy wanted.
2. Back up at a file level as an accessory or alternative to disk and volume backups.
3. Share docs with another person to keep locally.
4. Migrate to Markdown documenting for simplicity. .
5. Provide an easy way to do automated file backups locally, in docker, or kubernetes.

Supported backup formats are

1. local
2. minio
3. s3

Backups are exported in `.tgz` format and generated based off timestamp. Files are first pulled locally to create the tarball and then can be sent to object storage if needed. This script can be run directly via cli

## Using This Application

Note visibility of pages is based on user, so use a user that has access to pages you want to back up

### Authentication
Ref: [https://demo.bookstackapp.com/api/docs#authentication](https://demo.bookstackapp.com/api/docs#authentication)

Provide a tokenId and a tokenSecret as environment variables:
    - `BOOKSTACK_TOKEN_ID`
    - `BOOKSTACK_TOKEN_SECRET`

### Backup Behavior
We will use slug names (from Bookstack API) by default, as such certain characters like `!`, `/` will be ignored and spaces replaced.

```
Shelves --> Books --> Chapters --> Pages

## Example
kafka
---> controller
    ---> settings
        ---> logs (chapter)
            ---> retention
            ---> compression
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

Books without a shelf will be put in a shelve folder named `unassigned`

## Future Items
1. Be able to pull media/photos locally and place in their respective page folders for a more complete file level backup.
2. Include the exporter in a maintained helm chart as an optional deployment. The helm chart is [here](https://github.com/homeylab/helm-charts/tree/main/charts/bookstack).