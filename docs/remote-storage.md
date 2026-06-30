# Remote Storage

[← Back to README](../README.md#documentation)

- [Object Storage Upload](#object-storage-upload)
  - [Entry fields](#entry-fields)
  - [Credential resolution (per entry, first match wins)](#credential-resolution-per-entry-first-match-wins)
- [Multi-target upload behavior](#multi-target-upload-behavior)
- [Migrating from v2](#migrating-from-v2)

Optionally, one or more upload targets can be specified to push generated archives to remote object storage. Optionally, look at `examples/config.yml` in the github repo for a commented-out example.

## Object Storage Upload

Currently, s3 compatible object storage providers are supported. Feel free to create a github issue to request something else.

Configure one or more upload targets under `object_storage:`. Each entry has a `type`
(`minio` or `s3`). Any S3-compatible store — Wasabi, Cloudflare R2, Backblaze B2, Ceph, DigitalOcean Spaces — also works under `type: s3` (or `type: minio`) by setting an explicit `host`. These use the generic S3 API and the credential resolution below — there is no per-provider code, so most S3-compatible stores work as-is. If one fails under `type: s3` (addressing-style, signature, or checksum quirks), [open an issue](https://github.com/homeylab/bookstack-file-exporter/issues) with the provider name and the error.

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

### Entry fields

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

### Credential resolution (per entry, first match wins)

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

## Multi-target upload behavior

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

A target that uploads successfully but whose retention cleanup (pruning old objects per `keep_last`)
fails also yields a **Partial** run — the backup is safely stored, but the failed cleanup is surfaced
(exit 3 / `on_failure` / `degraded` health) so unbounded object growth is noticed.

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

