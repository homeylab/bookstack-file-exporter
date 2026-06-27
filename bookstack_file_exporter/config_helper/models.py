import logging
import re
from datetime import datetime
from typing import Literal
# pylint: disable=import-error
from pydantic import BaseModel, Field, AliasChoices, ConfigDict, field_validator, model_validator
from croniter import croniter, CroniterError

log = logging.getLogger(__name__)

# pylint: disable=too-few-public-methods
class BaseStorageConfig(BaseModel):
    """YAML schema for one object_storage entry (minio or s3).

    Permissive model: per-type required-ness (minio->host, s3->region) is checked at
    runtime in remote.py is_valid(); only the always-true cred-pair invariant is enforced
    here. Separate per-type models are deferred until fields genuinely diverge (YAGNI).
    """
    type: Literal["minio", "s3"]
    host: str | None = ""
    bucket: str
    region: str | None = None
    path: str | None = ""
    secure: bool = True
    keep_last: int | None = 0
    access_key: str | None = ""
    secret_key: str | None = ""
    access_key_env: str | None = None
    secret_key_env: str | None = None
    name: str | None = None

    @property
    def label(self) -> str:
        """Identity for logs/notifications. Excludes creds (secrets) and host/region by
        design, so a bare type/bucket collision forces the user to set a distinct name."""
        return self.name or f"{self.type}/{self.bucket}"

    @model_validator(mode="after")
    def _check_cred_pairs(self):
        """A half cred pair is always a mistake, regardless of the fallback chain."""
        if bool(self.access_key) != bool(self.secret_key):
            raise ValueError(
                "access_key and secret_key must be set together (or both omitted)")
        if bool(self.access_key_env) != bool(self.secret_key_env):
            raise ValueError(
                "access_key_env and secret_key_env must be set together (or both omitted)")
        return self

# pylint: disable=too-few-public-methods
class BookstackAccess(BaseModel):
    """YAML schema for bookstack access credentials"""
    token_id: str | None = ""
    token_secret: str | None = ""

# pylint: disable=too-few-public-methods
class Assets(BaseModel):
    """YAML schema for bookstack markdown asset(pages/images/attachments) configuration"""
    # Allow Pydantic to populate this field by Python name and by alias
    # so legacy config key `modify_markdown` can still be accepted.
    model_config = ConfigDict(populate_by_name=True)

    export_images: bool | None = False
    export_attachments: bool | None = False
    modify_links: bool | None = Field(
        default=False,
        validation_alias=AliasChoices("modify_links", "modify_markdown"),
    )
    export_meta: bool | None = False

    @model_validator(mode="before")
    @classmethod
    def _warn_deprecated_keys(cls, raw):
        """Nudge on the deprecated 'modify_markdown' key. The value is still honored
        via the validation_alias above; this only logs a rename reminder."""
        if isinstance(raw, dict) and "modify_markdown" in raw:
            log.warning(
                "DEPRECATED: 'assets.modify_markdown' is deprecated, use "
                "'assets.modify_links' instead. It will be removed in a future version.")
        return raw

class HttpConfig(BaseModel):
    """YAML schema for user provided http settings"""
    verify_ssl: bool | None = False
    timeout: int | None = 30
    backoff_factor: float | None = 2.5
    retry_codes: list[int] | None = [413, 429, 500, 502, 503, 504]
    retry_count: int | None = 5
    additional_headers: dict[str, str] | None = {}

class AppRiseNotifyConfig(BaseModel):
    """YAML schema for user provided app rise settings"""
    service_urls: list[str] | None = []
    config_path: str | None = ""
    plugin_paths: list[str] | None = []
    storage_path: str | None = ""
    custom_title: str | None = ""
    custom_attachment_path: str | None = ""
    on_success: bool | None = False
    on_failure: bool | None = True

class Notifications(BaseModel):
    """YAML schema for user provided notification settings"""
    apprise: AppRiseNotifyConfig | None = None

def _validate_pattern_list(patterns: list[str] | None) -> list[str] | None:
    """Compile each pattern string and reject empty strings.

    Iterate-and-dispatch shape: each item is dispatched to its own check
    so a future union type (str | PatternSpec) can widen cleanly.
    """
    if patterns is None:
        return patterns
    for pattern in patterns:
        if pattern == "":
            raise ValueError(
                '"" is not allowed (empty string matches empty names unexpectedly)'
            )
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f'invalid regex pattern "{pattern}": {exc}') from exc
    return patterns


class ResourceFilter(BaseModel):
    """Include/exclude pattern lists for one resource type."""
    include: list[str] | None = None
    exclude: list[str] | None = None

    @field_validator("include", "exclude", mode="before")
    @classmethod
    def validate_patterns(cls, value):
        """Compile each pattern and reject empty strings."""
        return _validate_pattern_list(value)


class Filters(BaseModel):
    """Per-resource-type regex filter configuration."""
    shelves: ResourceFilter | None = None
    books: ResourceFilter | None = None
    chapters: ResourceFilter | None = None
    pages: ResourceFilter | None = None
    # Structural toggle (not a regex filter): when true, drop ALL books with no
    # shelf assignment, regardless of the books include/exclude patterns.
    exclude_unassigned_books: bool = False


# pylint: disable=too-few-public-methods
class UserInput(BaseModel):
    """YAML schema for user provided configuration file"""
    host: str
    credentials: BookstackAccess | None = BookstackAccess()
    formats: list[Literal["markdown", "html", "pdf", "plaintext", "zip"]]
    output_path: str | None = ""
    # Export granularity: "pages" = one file per page (default),
    # "books" = one combined file per book, "chapters" = one combined file per chapter.
    # Note: assets.export_images/attachments/modify_links apply at all levels;
    # for book/chapter, modify_links localizes assets in markdown exports
    # (html/pdf embed assets server-side and are not rewritten at these levels).
    export_level: Literal["pages", "books", "chapters"] = "pages"
    assets: Assets | None = Assets()
    object_storage: list[BaseStorageConfig] | None = None
    keep_last: int | None = 0
    # Opt-in node-level parallel fetch. Default 1 = today's exact serial behavior.
    # ge=1 because ThreadPoolExecutor(max_workers=0) raises ValueError — reject
    # nonsense at config-parse time, not mid-run. No hard upper bound: huge values
    # are self-correcting via 429 backoff / server saturation. Raising this increases
    # concurrent API requests; BookStack rate-limits (API_REQUESTS_PER_MIN, default
    # 180/min/user -> HTTP 429). If you raise it and see 429s, raise that .env value.
    export_workers: int = Field(default=1, ge=1)
    run_interval: int | None = 0
    run_schedule: str | None = None
    # opt-in scheduled-mode health endpoint; no server unless health_port is set
    health_port: int | None = None
    health_host: str | None = "0.0.0.0"
    http_config: HttpConfig | None = HttpConfig()
    notifications: Notifications | None = None
    filters: Filters | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_removed_keys(cls, raw):
        """Hard-fail on removed v2 keys that pydantic would otherwise silently drop
        (extra='ignore'). 'minio:' was REMOVED in v3 (not deprecated -- it no longer
        does anything), so ANY presence is an error: a backup tool must never run on a
        stale config that silently produces no uploads. v3.0.0 is the expected break."""
        if isinstance(raw, dict) and "minio" in raw:
            raise ValueError(
                "'minio' was removed in v3.0.0; migrate to 'object_storage'. "
                "See the 'Migrating from v2' section in the README.")
        return raw

    @model_validator(mode="after")
    def _check_unique_object_storage_labels(self):
        """Enforce distinct labels across all object_storage entries."""
        if not self.object_storage:
            return self
        seen: set[str] = set()
        # pylint: disable-next=not-an-iterable
        for entry in self.object_storage:
            lbl = entry.label
            if lbl in seen:
                raise ValueError(
                    f"Duplicate object_storage label {lbl!r}. "
                    "Two entries share the same type/bucket; set a distinct 'name' on each.")
            seen.add(lbl)
        return self

    @model_validator(mode="after")
    def _check_schedule_config(self):
        if self.run_schedule:
            if self.run_interval:
                raise ValueError(
                    "run_interval and run_schedule are mutually exclusive; set only one")
            if not croniter.is_valid(self.run_schedule):
                raise ValueError(f"Invalid run_schedule cron expression: {self.run_schedule!r}")
            try:
                croniter(self.run_schedule, datetime(2000, 1, 1)).get_next(datetime)
            except CroniterError as err:
                raise ValueError(
                    f"run_schedule cron expression never fires: {self.run_schedule!r}") from err
        return self
