import logging
import re
from datetime import datetime
from typing import Literal
# pylint: disable=import-error
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from croniter import croniter, CroniterError

log = logging.getLogger(__name__)

# pylint: disable=too-few-public-methods
class StrictModel(BaseModel):
    """Config base: reject unknown keys. pydantic's default extra='ignore' silently
    drops a typo'd key and leaves its field at default — for a backup tool that can
    mean no retention ('keeplast'), ignored http settings ('timout'), or a target
    silently rerouted to AWS ('endpont'). The removed/renamed-key before-validators
    still run first, so 'minio:'/'host:'/'path:' keep their targeted migration hints."""
    model_config = ConfigDict(extra="forbid")

# pylint: disable=too-few-public-methods
class S3StorageConfig(StrictModel):
    """YAML schema for one object_storage entry (flat S3-compatible config).

    No 'type' field: behavior is driven by fields. 'endpoint' presence selects
    custom-store vs AWS and infers path-style; 'ambient_auth' opts into the boto3
    SDK credential chain (env / IRSA / IMDS / assume-role); 'region' defaults to
    us-east-1 when an endpoint is set.
    """
    name: str
    endpoint: str | None = None
    bucket: str
    prefix: str | None = ""
    region: str | None = None
    secure: bool = True
    addressing_style: Literal["path", "virtual", "auto"] | None = None  # None => inferred
    ambient_auth: bool = False
    keep_last: int | None = 0
    access_key: str | None = ""
    secret_key: str | None = ""
    access_key_env: str | None = None
    secret_key_env: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_removed_or_renamed_keys(cls, raw):
        """Reject renamed keys loudly. pydantic's default extra='ignore' would SILENTLY
        drop them — for a backup tool that means a v2.3.0 config moved into an
        object_storage list but keeping a leftover 'host:'/'path:' would parse as
        endpoint=None and quietly become an AWS target. Same fail-loud principle as
        UserInput._reject_removed_keys. 'host'/'path' were the v2.3.0 field names, renamed
        to 'endpoint'/'prefix'."""
        if not isinstance(raw, dict):
            return raw
        hints = {
            "host": "'host' was renamed to 'endpoint'.",
            "path": "'path' was renamed to 'prefix'.",
        }
        for key, hint in hints.items():
            if key in raw:
                raise ValueError(f"object_storage: {hint} Update your config (see v3 migration).")
        return raw

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

    @model_validator(mode="after")
    def _check_endpoint_no_scheme(self):
        """'endpoint' is host[:port], not a URL — the scheme is derived from 'secure'. A
        pasted 'https://minio.local' would otherwise become 'http://https://minio.local'."""
        # astroid FP: won't narrow the str|None 'endpoint' attr through the guard (E1135);
        # the truthiness check makes the membership test safe.
        if self.endpoint and "://" in self.endpoint:  # pylint: disable=unsupported-membership-test
            raise ValueError(
                f"endpoint {self.endpoint!r} must be host[:port] without a scheme; "
                "use 'secure: true|false' to control TLS.")
        return self

    @model_validator(mode="after")
    def _check_credentials_present(self):
        """Fail-closed: an entry MUST carry explicit creds (env NAMES or inline) OR opt
        into the ambient chain via ambient_auth. Never silently fall through to ambient."""
        has_env = bool(self.access_key_env and self.secret_key_env)
        has_inline = bool(self.access_key and self.secret_key)
        if not (has_env or has_inline or self.ambient_auth):
            raise ValueError(
                f"object_storage target {self.name!r} has no credentials: set access_key_env"
                "+secret_key_env, or access_key+secret_key, or ambient_auth: true (env / IAM "
                "role / IRSA).")
        return self

    @model_validator(mode="after")
    def _check_region_for_aws(self):
        """A no-endpoint target is AWS S3, which needs a region for signing/endpoint. Require
        it unless ambient_auth is on (botocore can resolve region from env/profile)."""
        if not self.endpoint and not self.region and not self.ambient_auth:
            raise ValueError(
                f"object_storage target {self.name!r}: 'region' is required for AWS S3 "
                "targets (no 'endpoint') unless ambient_auth resolves it.")
        return self

# pylint: disable=too-few-public-methods
class BookstackAccess(StrictModel):
    """YAML schema for bookstack access credentials"""
    token_id: str | None = ""
    token_secret: str | None = ""

# pylint: disable=too-few-public-methods
class Assets(StrictModel):
    """YAML schema for bookstack markdown asset(pages/images/attachments) configuration"""
    export_images: bool | None = False
    export_attachments: bool | None = False
    modify_links: bool | None = False
    export_meta: bool | None = False

    @model_validator(mode="before")
    @classmethod
    def _warn_deprecated_keys(cls, raw):
        """Honor and normalize the deprecated 'modify_markdown' key here (not via a
        validation_alias) so a leftover copy doesn't trip extra='forbid' when both keys
        are supplied. 'modify_links' wins when present; otherwise 'modify_markdown'
        provides the value. Then drop it and nudge toward the rename."""
        if isinstance(raw, dict) and "modify_markdown" in raw:
            log.warning(
                "DEPRECATED: 'assets.modify_markdown' is deprecated, use "
                "'assets.modify_links' instead. It will be removed in a future version.")
            raw = dict(raw)  # don't mutate the caller's dict in place
            legacy = raw.pop("modify_markdown")
            raw.setdefault("modify_links", legacy)
        return raw

class HttpConfig(StrictModel):
    """YAML schema for user provided http settings"""
    verify_ssl: bool | None = False
    timeout: int | None = 30
    backoff_factor: float | None = 2.5
    retry_codes: list[int] | None = [413, 429, 500, 502, 503, 504]
    retry_count: int | None = 5
    additional_headers: dict[str, str] | None = {}

class AppRiseNotifyConfig(StrictModel):
    """YAML schema for user provided app rise settings"""
    service_urls: list[str] | None = []
    config_path: str | None = ""
    plugin_paths: list[str] | None = []
    storage_path: str | None = ""
    custom_title: str | None = ""
    custom_attachment_path: str | None = ""
    on_success: bool | None = False
    on_failure: bool | None = True

class Notifications(StrictModel):
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


class ResourceFilter(StrictModel):
    """Include/exclude pattern lists for one resource type."""
    include: list[str] | None = None
    exclude: list[str] | None = None

    @field_validator("include", "exclude", mode="before")
    @classmethod
    def validate_patterns(cls, value):
        """Compile each pattern and reject empty strings."""
        return _validate_pattern_list(value)


class Filters(StrictModel):
    """Per-resource-type regex filter configuration."""
    shelves: ResourceFilter | None = None
    books: ResourceFilter | None = None
    chapters: ResourceFilter | None = None
    pages: ResourceFilter | None = None
    # Structural toggle (not a regex filter): when true, drop ALL books with no
    # shelf assignment, regardless of the books include/exclude patterns.
    exclude_unassigned_books: bool = False


# pylint: disable=too-few-public-methods
class UserInput(StrictModel):
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
    object_storage: list[S3StorageConfig] | None = None
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
    def _check_unique_object_storage_names(self):
        """Enforce a distinct 'name' across all object_storage entries — it is the
        target identity used in logs and notifications."""
        if not self.object_storage:
            return self
        seen: set[str] = set()
        # pylint: disable-next=not-an-iterable
        for entry in self.object_storage:
            if entry.name in seen:
                raise ValueError(
                    f"Duplicate object_storage name {entry.name!r}; "
                    "each entry needs a distinct 'name'.")
            seen.add(entry.name)
        return self

    @model_validator(mode="after")
    def _warn_duplicate_destinations(self):
        """Two entries pointing at the same endpoint/bucket/prefix write and prune the
        same object keys (upload collisions; retention double-prunes with each entry's
        keep_last). Distinct names make this legal, so warn rather than reject."""
        if not self.object_storage:
            return self
        seen: dict[tuple[str | None, str, str], str] = {}
        # pylint: disable-next=not-an-iterable
        for entry in self.object_storage:
            dest = (entry.endpoint, entry.bucket, (entry.prefix or "").strip("/"))
            if dest in seen:
                log.warning(
                    "object_storage targets %r and %r resolve to the same destination "
                    "(endpoint=%s bucket=%s prefix=%r): uploads collide and retention "
                    "will prune the same objects under both entries",
                    seen[dest], entry.name, entry.endpoint or "aws", dest[1], dest[2])
            else:
                seen[dest] = entry.name
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
