# Remote Storage

[← Back to README](../README.md#documentation)

- [Object Storage Upload](#object-storage-upload)
  - [Entry fields](#entry-fields)
  - [Credential resolution (per entry, fail-closed)](#credential-resolution-per-entry-fail-closed)
- [Multi-target upload behavior](#multi-target-upload-behavior)
- [Migrating from v2](#migrating-from-v2)

## Object Storage Upload
_Currently, S3-compatible object storage providers are supported. Feel free to create a github issue to request something else_.

One or more upload targets can be specified to push generated archives to remote object storage. Optionally, look at `examples/config.yml` in the github repo for a commented-out example.

Configure one or more upload targets under `object_storage:`. There is no `type` field —
behavior is driven entirely by the fields on the entry:
- Set `endpoint` to point at any S3-compatible store — MinIO, Ceph, Cloudflare R2, Backblaze
  B2, Wasabi, DigitalOcean Spaces, etc. Its presence selects "custom store" mode and infers
  path-style addressing.
- Omit `endpoint` for AWS S3.

These all use the generic boto3 S3 API and the credential resolution below — there is no
per-provider code, so most S3-compatible stores work as-is. If one fails (addressing-style,
signature, or checksum quirks), [open an issue](https://github.com/homeylab/bookstack-file-exporter/issues) with the provider name and the error.

```yaml
object_storage:
  # MinIO / self-hosted S3-compatible store: 'endpoint' present => custom store,
  # path-style addressing inferred automatically.
  - name: minio-main             # required, unique across all entries
    endpoint: minio.local:9000   # host[:port], no scheme -- 'secure' controls http/https
    bucket: backups
    region: us-east-1            # optional; defaults to us-east-1 when endpoint is set
    secure: false                # local MinIO is often non-TLS
    prefix: exports              # optional object key prefix
    keep_last: 5
    access_key_env: MINIO_ACCESS_KEY   # names of env vars to read
    secret_key_env: MINIO_SECRET_KEY

  # Second MinIO target with its own distinct creds/name
  - name: minio-secondary
    endpoint: minio2.local:9000
    bucket: backups2
    secure: false
    access_key_env: MINIO2_ACCESS_KEY
    secret_key_env: MINIO2_SECRET_KEY

  # A compat store that requires virtual-hosted addressing instead of the
  # path-style that 'endpoint' infers by default (e.g. DigitalOcean Spaces)
  - name: do-spaces
    endpoint: nyc3.digitaloceanspaces.com
    bucket: my-space
    addressing_style: virtual    # boto3 value passed through: path | virtual | auto
    access_key: DOACCESSKEY
    secret_key: DOSECRETKEY

  # AWS S3 with inline creds (no 'endpoint' => AWS)
  - name: aws-inline
    bucket: aws-backups
    region: us-east-1            # required for AWS unless ambient_auth resolves it
    keep_last: 10
    access_key: AKIA...
    secret_key: wJalr...

  # AWS S3 with no static creds -- opt into the boto3 ambient credential chain
  # (env vars / shared config profile / IRSA or Pod Identity on EKS / IMDS
  # instance profile on EC2 / assume-role)
  - name: aws-dr
    bucket: bookstack-dr
    region: us-east-1
    ambient_auth: true
    keep_last: 10
```

### Entry fields

| Item | Type | Required | Default | Description |
| ---- | ---- | -------- | ------- | ----------- |
| `name` | `str` | `true` | — | Unique label for this target, used in logs/notifications and to disambiguate entries. The exporter rejects the config if two entries share the same `name`. |
| `endpoint` | `str` | `false` | `None` | `host[:port]`, no scheme (a pasted `https://...` value is rejected — use `secure` to control the scheme). Presence selects a custom S3-compatible store and infers path-style addressing. Omit for AWS S3. |
| `bucket` | `str` | `true` | — | Bucket to upload to. |
| `region` | `str` | conditionally | `None` | Explicit value always wins. If omitted and `endpoint` is set, defaults to `us-east-1`. If omitted and no `endpoint` (AWS), required unless `ambient_auth: true` (botocore can then resolve it from env/profile). |
| `secure` | `bool` | `false` | `true` | TLS toggle; selects the `https://`/`http://` scheme used when building the endpoint URL. Set `false` for plain-HTTP local MinIO. |
| `prefix` | `str` | `false` | `""` | Optional object key prefix. Empty means bucket root. |
| `addressing_style` | `str` | `false` | `None` (inferred) | Passed straight to boto3: `path`, `virtual`, or `auto`. Left unset, `path` is inferred when `endpoint` is set (MinIO/Ceph work out of the box) and `auto` (virtual-hosted) for AWS. Use `virtual` for compat stores that require virtual-hosted addressing (e.g. DigitalOcean Spaces, Backblaze B2) — note boto3 treats `auto` the same as `path` when a custom `endpoint` is set, so `virtual` is the only way to get virtual-hosted there. |
| `ambient_auth` | `bool` | `false` | `false` | Opt in to the boto3 SDK's own ambient credential chain: environment variables, shared config/profile, **IRSA or Pod Identity (EKS/Kubernetes)**, IMDS instance profile (EC2), or assume-role. Required whenever no `access_key(_env)` pair is configured on the entry — there is no silent fallback to ambient credentials. |
| `keep_last` | `int` | `false` | `0` | Retention pruning of this target's uploaded objects. `0` = keep all (no pruning). `1+` = retain that many most-recently-modified archives, deleting older ones. A negative value is a no-op — logged as a warning, nothing is deleted. Only objects directly under `prefix` are scanned — archives you move into nested "subfolders" are never deletion candidates. |
| `access_key` / `secret_key` | `str` | `false` | `""` | Inline static credentials. Must be set together — one without the other is a config error. |
| `access_key_env` / `secret_key_env` | `str` | `false` | `None` | Names of environment variables to read for the access/secret key. Must be set together. Once configured, both named vars are **required** at run time — if either is unset or empty, the run fails immediately (no silent fallthrough to inline creds or ambient auth). |

### Credential resolution (per entry, fail-closed)

Each entry resolves credentials through an ordered chain; the first configured source wins.
If none apply, the config is **rejected at parse time** — there is no silent fallback to
ambient credentials.

1. **Per-entry named env vars** — `access_key_env` + `secret_key_env` give the *names* of the
   env vars to read. This is the only way to give two targets distinct credentials kept out
   of the config file.
   ```yaml
   - name: minio-secondary
     endpoint: minio2.local:9000
     bucket: backups2
     access_key_env: MINIO2_ACCESS_KEY   # the value is the env var NAME, not the secret
     secret_key_env: MINIO2_SECRET_KEY
   ```
   ```bash
   export MINIO2_ACCESS_KEY=AKIA... MINIO2_SECRET_KEY=wJalr...
   ```
   Once configured, both named vars are mandatory: if either resolves to unset/empty at run
   time, the run fails with an error rather than falling through to inline creds.
2. **Inline keys** — `access_key` + `secret_key` set directly on the entry.
   ```yaml
   - name: aws-inline
     bucket: aws-backups
     region: us-east-1
     access_key: AKIA...
     secret_key: wJalr...
   ```
3. **`ambient_auth: true`** — no secrets anywhere in the config; the boto3 SDK's own
   credential chain supplies them at run time: standard `AWS_ACCESS_KEY_ID` /
   `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN` env vars, a shared config/credentials profile,
   an EC2 instance profile (IMDS), an ECS task role, or — for the common Kubernetes case — an
   **IRSA or EKS Pod Identity** web-identity role bound to the pod's service account.
   ```yaml
   - name: aws-dr
     bucket: bookstack-dr
     region: us-east-1
     ambient_auth: true      # no creds in the YAML, no per-entry env vars
   ```

Setting only one half of a credential pair (`access_key` without `secret_key`, or `*_env`
without its partner) is always a config validation error, regardless of which chain tier it
belongs to. An entry with **no** env-name pair, no inline pair, and `ambient_auth: false`
(the default) fails config validation immediately — object storage credentials must be
explicit or explicitly delegated to the ambient chain, never assumed.

## Bucket validation

At startup each target's bucket is checked with a `HeadBucket` call:

- A **missing bucket** (HTTP `404`) is a hard failure — the run stops before the export, so a
  typo or an uncreated bucket is caught early rather than after a full export.
- An **ambiguous** result (e.g. `403` from a write-only key that can `PutObject` but lacks
  `ListBucket`, or a provider that restricts `HeadBucket`) is logged as a **warning** and the
  upload is attempted anyway — a least-privilege credential is not falsely rejected, and the
  upload itself surfaces any real problem.
- An **unreachable or misconfigured endpoint** is a hard failure.

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

The same applies locally: if pruning old local archives (top-level `keep_last`) fails after the
export and uploads succeeded, the run is **Partial** — the backup is safe, the failed cleanup is
surfaced in the notification, and stale local files are left for the next run to prune.

In scheduled mode the `/healthz` endpoint reports `last_run.status` as `degraded` for a partial
run (distinct from `success` and `failed`).

## Migrating from v2

v3.0.0 removes the single top-level `minio:` block entirely — its presence is now a hard
config error, not a silent no-op. Move your settings into an `object_storage:` list, using the
flat schema above:

```yaml
# v2 (removed; now a config error if present)
minio:
  host: minio.local:9000
  bucket: backups
  region: us-east-1
  path: exports
  keep_last: 5

# v3
object_storage:
  - name: minio-main          # now required
    endpoint: minio.local:9000  # was 'host'
    bucket: bookstack-backups
    prefix: daily              # was 'path'
    region: us-east-1          # optional (defaults to us-east-1 when endpoint is set)
    secure: false
    access_key_env: MINIO_ACCESS_KEY
    secret_key_env: MINIO_SECRET_KEY
  # AWS with an instance/pod role (IRSA):
  - name: aws-dr
    bucket: bookstack-dr
    region: us-east-1
    ambient_auth: true        # opt into boto3's ambient chain (env / IRSA / Pod Identity / IMDS)
```

Key renames, all enforced by validation (not silently ignored):
- `host` → `endpoint`.
- `path` → `prefix`.
- A leftover `host:` or `path:` key in an `object_storage` entry now **errors** with a
  rename hint, rather than being silently dropped.
- There is no more implicit, globally-shared credential env var (the old `MINIO_ACCESS_KEY` /
  `MINIO_SECRET_KEY` / `AWS_ACCESS_KEY_ID` auto-pickup). For MinIO's legacy
  `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY`, point `access_key_env`/`secret_key_env` at them
  explicitly, or set `ambient_auth: true` to use boto3's own ambient chain (which does still
  recognize the standard `AWS_*` env vars, a shared profile, or IRSA/IMDS/assume-role).
- `secure` now defaults to `true`; set `secure: false` for plain-HTTP local MinIO.

### Other v3 key changes (outside `object_storage`)

- `assets.modify_markdown` (deprecated alias since v2.3.0) was **removed** — rename it to
  `assets.modify_links`. Presence is now a config error with a rename hint.
