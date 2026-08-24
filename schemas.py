from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DeveloperMeta(BaseModel):
    developer: str = Field(default="Tronn", description="API Product Developer")


class ServiceInfoResponse(BaseModel):
    status: str = "healthy"
    service: str = "Tronn Data Sync API"
    developer: str = "Tronn"
    version: str = "1.0.0"
    docs_url: str = "/docs"
    endpoints: Dict[str, str]


class RecordResponse(BaseModel):
    status: str = "success"
    developer: str = "Tronn"
    data: Dict[str, Any]


class SyncResponse(BaseModel):
    status: str = "success"
    developer: str = "Tronn"
    count: int = Field(..., description="Number of items returned in this page/sync")
    total: int = Field(..., description="Total matching items before pagination")
    data: List[Dict[str, Any]] = Field(..., description="List of synchronized records")


class DeleteResponse(BaseModel):
    status: str = "success"
    developer: str = "Tronn"
    message: str
    deleted_count: int = Field(..., description="Number of records deleted")


class ErrorResponse(BaseModel):
    status: str = "error"
    developer: str = "Tronn"
    detail: str
