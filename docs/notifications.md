# Notifications

[← Back to README](../README.md#documentation)

- [General](#general)
- [Format](#format)
- [apprise](#apprise)

## General
It is possible to send notifications when an export run succeeds or fails. Currently, the only supported notification service is [apprise](https://github.com/caronc/apprise). Apprise is a general purpose notification service and has a variety of integrations and includes generic HTTP POST.

Notifications are optional and the `notification` section can be omitted/removed/commented out entirely to keep a smaller configuration if not required.

## Format
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

## apprise
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
