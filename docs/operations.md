# Operations

[← Back to README](../README.md#documentation)

- [Run Modes](#run-modes)
- [Run Outcomes And Exit Codes](#run-outcomes-and-exit-codes)
- [Graceful Shutdown And Grace Periods](#graceful-shutdown-and-grace-periods)
- [Health Endpoint](#health-endpoint)

## Run Modes
The exporter runs in one of two modes, selected automatically from your config:

- **One-shot** (default): `run_interval` unset or `0`, and `run_schedule` unset → runs once and exits. Exit codes: `0` success, `1` failure (clean error message; pass `-v debug` for the full traceback), `3` partial — the run completed but something was lost or degraded (content that failed to export, a failed upload target, or failed retention cleanup; details in the notification), `130`/`143` interrupted by `Ctrl-C`/`SIGTERM` (128+signal). See [Run Outcomes And Exit Codes](#run-outcomes-and-exit-codes) for the full model. Pairs well with an external scheduler (Kubernetes `CronJob`, `cron`, `systemd` timer), which owns restart, backoff, and run history.
- **Application / scheduled** (long-running): `run_interval` or `run_schedule` set → runs repeatedly, then waits for the next trigger. For a single-container `docker compose` deployment with no external scheduler. A failed cycle is logged (and notifies, if configured) and waits for the next trigger rather than crashing. Shuts down gracefully on `SIGTERM` (`docker stop`) and `SIGINT` (`Ctrl-C`), always exiting `0` on clean shutdown regardless of the last cycle's outcome — monitor `/healthz` or notifications instead.

Two scheduling strategies are available for application mode (mutually exclusive — setting both is a config error):

- **`run_interval`** (seconds): sleeps a fixed number of seconds between cycles. Simple but drifts over time — the effective period is `run_interval` + cycle runtime.
- **`run_schedule`** (cron expression): fires at wall-clock times. Standard 5-field cron syntax (e.g. `"0 2 * * *"` = 2 am daily). croniter also accepts 6/7-field extended forms. Cron is evaluated in container-local time — set the `TZ` environment variable to control the timezone (default: `UTC`). Note: if a cycle runs past its scheduled tick, the missed tick is skipped (no catch-up). During a DST spring-forward, a scheduled time that falls inside the skipped hour will not fire that day.

Pass `--run-once` to force a single run regardless of `run_interval` or `run_schedule`.

## Run Outcomes And Exit Codes

Every run resolves to one of three outcomes, which determines the process exit code (in one-shot mode) and the notification sent:

| Outcome | When | Exit code | Notification |
|---|---|---|---|
| Success | all content exported and every configured upload target succeeded | `0` | "Success" (`on_success`) |
| Partial | some content failed to export (pages/books/chapters or assets), some upload targets failed, a retention cleanup failed, **or** all uploads failed but a local copy is kept (`keep_last >= 0`) | `3` | "Partial" (`on_failure`) |
| Failure | the export itself failed (including when no document content was archived at all), **or** all uploads failed with no local copy kept (`keep_last < 0`) | `1` | "Failed" (`on_failure`) |

A *partial* run means the run finished but its result is degraded — the archive is missing
content, or fewer durable copies exist than configured (for upload failures: at least one copy
survived, a remote target or the local `.tgz` when `keep_last >= 0`). It is reported via the
`on_failure` notification so it is not silently treated as a clean success. When `keep_last < 0`
(local archive deleted) AND every upload fails, the run is a hard failure — the local archive is
preserved so the run can be retried.

Content loss — a page export or asset download that failed after retries — also yields a
**Partial** run; the notification carries the failure counts, and per-path detail is in the run
logs. In the extreme case where fetches failed and not a single page/book/chapter export
succeeded, no restorable backup exists — even if assets or metadata were written — so the run is
a hard **Failure** (exit `1`), not Partial.

A retention cleanup that fails after a successful export also yields a **Partial** run — the backup
is safely stored, but the failed cleanup is surfaced (exit `3` / `on_failure` / `degraded` health) so
unbounded archive growth is noticed. This applies both to local pruning (top-level `keep_last`) and
to any `object_storage` target's own `keep_last`; stale files are left for the next run to prune.

Retention itself runs the same way regardless of run outcome: scoped to the run's `export_level`,
with complete and `*_partial.tgz` archives kept as independent `keep_last` groups, so a partial
run's archive can never evict a complete backup — see [Backup Behavior](backup-behavior.md#format).

In scheduled mode the exit code always reflects clean process shutdown, not the last cycle's
outcome — monitor the [Health Endpoint](#health-endpoint)'s `last_run.status` (`degraded` for a
partial run) or notifications instead. Interrupt exit codes (`130`/`143`) are covered under
[Graceful Shutdown](#graceful-shutdown-and-grace-periods).

## Graceful Shutdown And Grace Periods

Both modes handle `SIGTERM`/`SIGINT` the same cooperative way: the exporter stops at the
next asset/format/node boundary and discards any incomplete archive. A second signal
force-kills immediately (`130` for SIGINT, `143` for SIGTERM) in both modes.

Where they differ is the exit code. Scheduled mode exits `0` on a clean shutdown — that
means the process stopped cleanly, **not** that the last cycle succeeded; alert on
notifications or `/healthz`, not on the exit code. One-shot mode has no next cycle to
fall back on, so an interrupted run exits `130`/`143` (128+signal) instead. A signal that
lands after archiving finishes, during archive finalize/upload/cleanup (no checkpoints there), lets
the run complete and the exit code reflects its actual outcome in either mode.

A single in-flight export call (e.g. a large-book PDF render) cannot be interrupted
mid-request, so give the container time to drain:

- Docker: `docker stop -t 60 <container>` (default is 10s).
- Compose: set `stop_grace_period: 60s` (raise for large instances).
- Kubernetes: set `terminationGracePeriodSeconds: 60`.

If the grace window elapses the orchestrator sends an uncatchable SIGKILL, which can
strand an incomplete archive. The next run sweeps leftover `.tar`/`.tgz.incomplete` files (at
any export level) before it writes anything; a finished `.tgz` is never touched.

## Health Endpoint

In scheduled mode (`run_interval` or `run_schedule`), set `health_port` to expose an
opt-in `GET /healthz` endpoint. No server is started unless `health_port` is set, and
it is ignored in one-shot mode.

```yaml
health_port: 8080          # opt-in; no server unless set
health_host: "0.0.0.0"     # optional bind address (default 0.0.0.0)
```

`GET /healthz` returns `200` with a JSON body while the daemon is alive:

```json
{
  "status": "healthy",
  "last_run": {
    "status": "success",
    "started_at": "2026-06-21T02:00:00Z",
    "finished_at": "2026-06-21T02:03:11Z",
    "duration_seconds": 191,
    "archive_file": "bookstack_export_2026-06-21_02-00-00.tgz",
    "error": null
  },
  "next_run": "2026-06-22T02:00:00Z",
  "run_count": 5,
  "failure_count": 0
}
```

This is a **liveness** signal: it stays `200` even after a failed export cycle
(the scheduled loop logs and continues), so probes do not flap on transient
BookStack outages. Use `last_run.status` (`never` → `running` → `success` |
`degraded` | `failed`) and `failure_count` for scrape-based alerting. Any path
other than `/healthz` returns `404`.

`degraded` is a **partial success**: a local/remote copy survived but at least
one remote target failed. It counts as a completed run and does **not** increment
`failure_count`, so alert on `last_run.status == "degraded"` separately — watching
`failure_count` alone will miss partial upload failures.

Kubernetes liveness probe:

```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 30
```

Docker healthcheck:

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz').status==200 else 1)"
```
