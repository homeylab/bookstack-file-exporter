from typing import Dict, Literal, List, Optional
from pydantic import BaseModel

# pylint: disable=R0903

class MinioConfig(BaseModel):
    """YAML schema for minio configuration"""
    host: str
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    bucket: str
    path: Optional[str] = None
    region: str

class BookstackAccess(BaseModel):
    """YAML schema for bookstack access credentials"""
    token_id: str
    token_secret: str

class UserInput(BaseModel):
    """YAML schema for user provided configuration file"""
    host: str
    additional_headers: Optional[Dict[str, str]] = None
    credentials: Optional[BookstackAccess] = None
    formats: List[Literal["markdown", "html", "pdf", "plaintext"]]
    output_path: Optional[str] = None
    export_meta: Optional[bool] = None
    minio_config: Optional[MinioConfig] = None
    clean_up: Optional[bool] = None
