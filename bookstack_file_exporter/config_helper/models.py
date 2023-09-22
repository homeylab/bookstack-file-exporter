from typing import Dict, Literal, List, Optional
from pydantic import BaseModel

class MinioConfig(BaseModel):
    host: str
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    bucket: str
    path: Optional[str] = None
    region: str

class BookstackAccess(BaseModel):
    token_id: str
    token_secret: str

class UserInput(BaseModel):
    host: str
    additional_headers: Optional[Dict[str, str]] = None
    credentials: Optional[BookstackAccess] = None
    formats: List[Literal["markdown", "html", "pdf", "plaintext"]]
    output_path: Optional[str] = None
    export_meta: Optional[bool] = None
    minio_config: Optional[MinioConfig] = None
    clean_up: Optional[bool] = None