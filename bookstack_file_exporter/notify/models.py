from dataclasses import dataclass, field
from enum import Enum


class ExportStatus(Enum):
    """Terminal run outcome. Hard failure is a raised exception, never a value here."""
    SUCCESS = "success"
    PARTIAL = "partial"


@dataclass
class UploadOutcome:
    """Per-target upload result. dest set on success, error set on failure."""
    label: str                  # provider_config.config.label
    dest: str | None = None     # "bucket/object" on success
    error: str | None = None    # str(exception) on failure


@dataclass
class NotifyResult:
    """What an export run produced, for notifications."""
    status: ExportStatus = ExportStatus.SUCCESS
    local: str | None = None                            # local .tgz path, None if no archive
    uploads: list[UploadOutcome] = field(default_factory=list)  # one per configured target
    removed: list[str] = field(default_factory=list)    # local files clean_up() deleted
