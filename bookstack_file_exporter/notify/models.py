from dataclasses import dataclass, field


@dataclass
class NotifyResult:
    """What an export run produced, for the success notification."""
    local: str | None = None          # full local .tgz path, None if no archive made
    remote: list[str] = field(default_factory=list)   # remote destinations, one per target
    removed: list[str] = field(default_factory=list)   # local files clean_up() actually deleted
