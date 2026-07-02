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
Uploaded to: my-bucket/bookstack, my-bucket-s3/bookstack
Pruned 2 old local archive(s)
```
The success body reports the archive details only when an archive is produced. `Archive:` shows the local `.tgz` path (with `(removed locally after upload)` when it was uploaded then deleted), `Uploaded to:` lists each remote destination, and `Pruned N old local archive(s)` appears when `keep_last` removed older archives.

### Body Format
By default the notification body is sent as plain text (`body_format: text`), as shown in the examples above. Set `apprise.body_format: markdown` to render the body as Markdown instead: the headline and the `Failed:`/`Warnings:` group headers become bold, failed targets and warnings render as real bullet lists, and values like paths, destinations, and error messages are quoted in code spans.
```yaml
notifications:
  apprise:
    service_urls:
      - "slack://TokenA/TokenB/TokenC/"
    body_format: markdown
```
Whether `markdown` is an improvement depends on your notification targets:
- Markdown-native targets (e.g. Slack) and HTML-native targets (e.g. Telegram, email) render the bold headers, bullet lists, and code-quoted error messages properly.
- Plain-text targets (e.g. generic `json://` webhooks, ntfy, SMS) will show the literal `**` and backtick characters — apprise passes a Markdown body through to text targets unchanged, it does not strip the markup. This is why `markdown` is opt-in; choose based on your target mix.

`body_format` is the input-side knob: it tells apprise what format the body is written in, and apprise then converts it to each service URL's native format. To override the target-side format for a specific URL, use apprise's per-URL `?format=` parameter (e.g. `json://host/notify?format=markdown`) — see the [apprise wiki](https://github.com/caronc/apprise/wiki) for details.

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
| `apprise.body_format` | `str` | Default: `text`, set to `markdown` to render the notification body as Markdown. See [Body Format](#body-format) for the trade-offs |

`apprise.service_urls` can contain sensitive information and can be specified as an environment variable instead as a string list, example: `export APPRISE_URLS='["json://localhost:8080/notify"]'`.

**If using apprise for notifications, one of `apprise.service_urls` or `apprise.config_path` should be specified.**
