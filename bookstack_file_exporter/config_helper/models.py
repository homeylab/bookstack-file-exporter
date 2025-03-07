from typing import Dict, Literal, List, Optional
# pylint: disable=import-error
from pydantic import BaseModel

# pylint: disable=too-few-public-methods
class ObjectStorageConfig(BaseModel):
    """YAML schema for minio configuration"""
    host: str
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    bucket: str
    path: Optional[str] = None
    region: str
    keep_last: Optional[int] = None

# pylint: disable=too-few-public-methods
class BookstackAccess(BaseModel):
    """YAML schema for bookstack access credentials"""
    token_id: str
    token_secret: str

# pylint: disable=too-few-public-methods
class Assets(BaseModel):
    """YAML schema for bookstack markdown asset(pages/images/attachments) configuration"""
    export_images: Optional[bool] = False
    export_attachments: Optional[bool] = False
    modify_markdown: Optional[bool] = False
    export_meta: Optional[bool] = False
    # verify_ssl: Optional[bool] = True

class HttpConfig(BaseModel):
    """YAML schema for user provided http settings"""
    verify_ssl: Optional[bool] = False
    timeout: Optional[int] = 30
    backoff_factor: Optional[float] = 2.5
    retry_codes: Optional[List[int]] = [413, 429, 500, 502, 503, 504]
    retry_count: Optional[int] = 5
    additional_headers: Optional[Dict[str, str]] = {}

# pylint: disable=too-few-public-methods
class UserInput(BaseModel):
    """YAML schema for user provided configuration file"""
    host: str
    credentials: Optional[BookstackAccess] = None
    formats: List[Literal["markdown", "html", "pdf", "plaintext"]]
    output_path: Optional[str] = None
    assets: Optional[Assets] = Assets()
    minio: Optional[ObjectStorageConfig] = None
    keep_last: Optional[int] = None
    run_interval: Optional[int] = 0
    http_config: Optional[HttpConfig] = HttpConfig()
