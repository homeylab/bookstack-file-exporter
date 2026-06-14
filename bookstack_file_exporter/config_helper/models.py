import re
from typing import Literal
# pylint: disable=import-error
from pydantic import BaseModel, Field, AliasChoices, ConfigDict, field_validator

# pylint: disable=too-few-public-methods
class ObjectStorageConfig(BaseModel):
    """YAML schema for minio configuration"""
    host: str | None = ""
    access_key: str | None = ""
    secret_key: str | None = ""
    bucket: str
    path: str | None = ""
    region: str
    keep_last: int | None = 0

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
    minio: ObjectStorageConfig | None = None
    keep_last: int | None = 0
    run_interval: int | None = 0
    http_config: HttpConfig | None = HttpConfig()
    notifications: Notifications | None = None
    filters: Filters | None = None
