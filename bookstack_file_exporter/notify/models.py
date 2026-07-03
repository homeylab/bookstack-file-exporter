from dataclasses import dataclass, field
from enum import Enum


class ExportStatus(Enum):
    """Terminal run outcome. Hard failure is a raised exception, never a value here."""
    SUCCESS = "success"
    PARTIAL = "partial"


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
