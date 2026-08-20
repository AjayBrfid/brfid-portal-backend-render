"""Generic API response envelope shared by every module, standardized on the
`{success, data, meta}` shape (2 of the 3 source projects already used it; Backend-WH-Retail's
`{data, total, page, page_size}` shape is retired — see the consolidation plan's breaking-change
note). `meta.totalItems` (not `total`) is the pagination key going forward.
"""
from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T
    meta: dict | None = None


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list | None = None


class ApiErrorResponse(BaseModel):
    success: bool = False
    error: ErrorBody


class PaginationParams:
    """Shared `?page=&limit=` query params for every list endpoint across all four portals."""

    # le=5000 (not 200) so vms-sa-react's createListResource() -- which always requests
    # limit=1000 to emulate "load the full collection" over its client-side table hooks --
    # doesn't 422. Existing callers requesting <=200 see no change.
    def __init__(self, page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=5000)):
        self.page = page
        self.limit = limit

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


def build_meta(page: int, limit: int, total_items: int) -> dict:
    total_pages = max(1, -(-total_items // limit)) if total_items else 1
    return {"page": page, "limit": limit, "totalItems": total_items, "totalPages": total_pages}
