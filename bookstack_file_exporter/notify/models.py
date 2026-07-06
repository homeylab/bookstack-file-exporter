from dataclasses import dataclass, field
from enum import Enum


class ExportStatus(Enum):
    """Terminal run outcome. Hard failure is a raised exception, never a value here.

    SUCCESS: archive produced and durable copies exist.
    PARTIAL: run finished but degraded (content loss, a failed upload, or a
        failed retention cleanup).
    EMPTY: run completed but found nothing to archive (empty instance / filters
        matched nothing) -- not a failure, not cancelled.
    """
    SUCCESS = "success"
    PARTIAL = "partial"
    EMPTY = "empty"


@dataclass(frozen=True)
class StatusEffects:
    """Everything a terminal ExportStatus drives, in one row."""
    exit_code: int          # one-shot process exit code
    health_degraded: bool   # scheduled mode: mark_degraded (True) vs mark_success
    title_suffix: str       # notification title: "Bookstack File Exporter " + suffix


# Single source for status -> observable-outcome mapping. run.py (exit code,
# health mark) and notifiers.py (title) consume this table; a new status or a
# changed exit code is edited here only. Exit codes follow the restic/borg
# convention: 0 success, 1 hard failure (raised exception, never a status
# value here), 3 partial/incomplete, 128+signum on signals.
STATUS_EFFECTS: dict[ExportStatus, StatusEffects] = {
    ExportStatus.SUCCESS: StatusEffects(
        exit_code=0, health_degraded=False, title_suffix="Success"),
    ExportStatus.PARTIAL: StatusEffects(
        exit_code=3, health_degraded=True, title_suffix="Partial"),
    # title stays "Success": operators' alerting rules match on title, and the
    # body carries the nothing-to-archive detail instead.
    ExportStatus.EMPTY: StatusEffects(
        exit_code=0, health_degraded=False, title_suffix="Success"),
}


@dataclass
class UploadOutcome:
    """Per-target upload result. dest set on success; error set on upload failure;
    warning set when the upload landed but post-upload retention cleanup failed."""
    label: str                  # provider_config.name
    dest: str | None = None     # "bucket/object" on success
    error: str | None = None    # str(exception) on upload failure
    warning: str | None = None  # str(exception) when upload OK but retention cleanup failed
    pruned: int = 0             # objects deleted by remote retention (0 when cleanup failed)


@dataclass
class NotifyResult:  # pylint: disable=too-many-instance-attributes
    """What an export run produced, for notifications."""
    status: ExportStatus = ExportStatus.SUCCESS
    local: str | None = None                            # local .tgz path, None if no archive
    uploads: list[UploadOutcome] = field(default_factory=list)  # one per configured target
    removed: list[str] = field(default_factory=list)    # local files clean_up() deleted
    cleanup_error: str | None = None    # str(exception) when local retention pruning failed
    # Content-loss ledger: names of node exports / asset downloads that were
    # skipped after fetch failures. Non-empty => status was downgraded to PARTIAL.
    failed_nodes: list[str] = field(default_factory=list)
    failed_assets: list[str] = field(default_factory=list)
    # which node kind this run exported ("pages" | "books" | "chapters") -- lets
    # the notifier say "2 page export(s) failed" instead of a generic "node"
    export_level: str = "pages"


# export_level -> singular noun for prose that reads "1 <thing> export(s) failed":
# the notifier body (notifiers.py) and the no-content error (run.py). The log
# summary uses the plural "<level>_failed" key form instead and needs no map.
# Explicit map (not export_level[:-1]) so an unexpected value degrades to a
# readable "node" fallback instead of a mangled slice.
LEVEL_SINGULAR = {"pages": "page", "books": "book", "chapters": "chapter"}


def format_run_summary(result: NotifyResult) -> str:
    """One-line plaintext run summary for the logs, mirroring the fields a
    notification carries. Distinct from the markdown notifier body: this is the
    outcome roll-up for operators reading stdout without notifications wired.
    Empty fields are omitted so a clean success stays short."""
    parts = [f"level={result.export_level}"]
    if result.local:
        parts.append(f"archive={result.local}")
    total = len(result.uploads)
    if total:
        ok = sum(1 for u in result.uploads if u.dest is not None)
        parts.append(f"uploads_ok={ok}/{total}")
        failed = [u.label for u in result.uploads if u.dest is None]
        if failed:
            parts.append(f"(failed: {', '.join(failed)})")
        warned = [u.label for u in result.uploads if u.dest is not None and u.warning]
        if warned:
            parts.append(f"(retention-warned: {', '.join(warned)})")
    if result.failed_nodes or result.failed_assets:
        # export_level is already plural (pages/books/chapters), so a
        # "<level>_failed" key needs no singular/plural handling and matches the
        # key=value shape of the rest of the line.
        parts.append(f"{result.export_level}_failed={len(result.failed_nodes)}")
        parts.append(f"assets_failed={len(result.failed_assets)}")
    if result.removed:
        parts.append(f"removed={len(result.removed)}")
    pruned = sum(u.pruned for u in result.uploads)
    if pruned:
        parts.append(f"pruned={pruned}")
    if result.cleanup_error:
        parts.append(f"cleanup_error={result.cleanup_error}")
    # Flatten any embedded newline so the summary stays a single grep-able line
    # (cleanup_error is a str(exception) and could otherwise carry a line break).
    return " ".join(parts).replace("\r", " ").replace("\n", " ")
