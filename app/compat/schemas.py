"""Shared base classes for the compat layer's request/response models. Every legacy frontend
(vms-react, vms-sa-react) speaks camelCase; the unified backend speaks snake_case everywhere
else. CamelModel lets compat schemas be written with normal snake_case Python field names while
transparently accepting and emitting camelCase JSON (FastAPI's default response serialization
already honors aliases, i.e. `response_model_by_alias=True`)."""
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


def vendor_meta(page: int, limit: int, total_items: int, **extra) -> dict:
    """vms-react's original meta shape: {page, limit, totalItems, totalPages, ...}."""
    total_pages = max(1, -(-total_items // limit)) if total_items else 1
    return {"page": page, "limit": limit, "totalItems": total_items, "totalPages": total_pages, **extra}


def admin_meta(page: int, limit: int, total_items: int) -> dict:
    """vms-sa-react's original meta shape: {page, limit, total, totalPages} — note "total", not
    "totalItems", unlike every other contract in this codebase."""
    total_pages = max(1, -(-total_items // limit)) if total_items else 1
    return {"page": page, "limit": limit, "total": total_items, "totalPages": total_pages}
