from typing import Dict, Literal, List, Optional
# pylint: disable=import-error
from pydantic import BaseModel

# pylint: disable=too-few-public-methods
class MinioConfig(BaseModel):
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
    """YAML schema for bookstack markdown asset(images/attachments) configuration"""
    export_images: Optional[bool] = None
    modify_markdown: Optional[bool] = None

# pylint: disable=too-few-public-methods
class UserInput(BaseModel):
    """YAML schema for user provided configuration file"""
    host: str
    additional_headers: Optional[Dict[str, str]] = None
    credentials: Optional[BookstackAccess] = None
    formats: List[Literal["markdown", "html", "pdf", "plaintext"]]
    output_path: Optional[str] = None
    export_meta: Optional[bool] = None
    assets: Optional[Assets] = None
    # export_images: Optional[bool] = None
    minio_config: Optional[MinioConfig] = None
    keep_last: Optional[int] = None
