from fastapi import APIRouter, Depends

from app.dependencies.auth import require_portal
from app.dependencies.retail import get_product_service
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.schemas.retail.retail_schemas import ApplyDiscountRequest, UpdateThresholdRequest, UpdateVisibilityRequest
from app.services.retail.product_service import ProductService

_portal = require_portal("store")

products_router = APIRouter(prefix="/products", tags=["retail-products"])


@products_router.get("", response_model=ApiResponse[list[dict]])
def list_products(
    category: str | None = None, q: str | None = None, visible_only: bool = False,
    params: PaginationParams = Depends(), service: ProductService = Depends(get_product_service), user: User = Depends(_portal),
):
    items, total = service.list_products(user.entity_id, params, category, q, visible_only)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@products_router.get("/categories", response_model=ApiResponse[list[str]])
def list_categories(service: ProductService = Depends(get_product_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.list_categories(user.entity_id))


@products_router.get("/removed", response_model=ApiResponse[list[dict]])
def list_removed(service: ProductService = Depends(get_product_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.list_removed(user.entity_id))


@products_router.put("/visibility", response_model=ApiResponse[dict])
def update_visibility(body: UpdateVisibilityRequest, service: ProductService = Depends(get_product_service), user: User = Depends(_portal)):
    updated = service.update_visibility(user.entity_id, [(u.sku, u.visible) for u in body.updates], user.id)
    return ApiResponse(data={"updated": updated})


@products_router.get("/{sku}", response_model=ApiResponse[dict])
def get_product(sku: str, service: ProductService = Depends(get_product_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.get_product(user.entity_id, sku))


@products_router.post("/{sku}/restore", response_model=ApiResponse[dict])
def restore_product(sku: str, service: ProductService = Depends(get_product_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.restore_product(user.entity_id, sku))


stock_router = APIRouter(prefix="/stock", tags=["retail-stock"])


@stock_router.get("/summary", response_model=ApiResponse[dict])
def get_summary(service: ProductService = Depends(get_product_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.get_stock_summary(user.entity_id))


@stock_router.get("/low", response_model=ApiResponse[list[dict]])
def list_low(service: ProductService = Depends(get_product_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.list_stock_rows(user.entity_id, "low"))


@stock_router.get("/out", response_model=ApiResponse[list[dict]])
def list_out(service: ProductService = Depends(get_product_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.list_stock_rows(user.entity_id, "out"))


@stock_router.get("/settings/low-threshold", response_model=ApiResponse[dict])
def get_threshold(service: ProductService = Depends(get_product_service), user: User = Depends(_portal)):
    return ApiResponse(data={"threshold": service.get_low_stock_threshold(user.entity_id)})


@stock_router.put("/settings/low-threshold", status_code=204)
def set_threshold(body: UpdateThresholdRequest, service: ProductService = Depends(get_product_service), user: User = Depends(_portal)):
    service.set_low_stock_threshold(user.entity_id, body.threshold)


discounts_router = APIRouter(prefix="/discounts", tags=["retail-discounts"])


@discounts_router.get("", response_model=ApiResponse[list[dict]])
def list_discounts(service: ProductService = Depends(get_product_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.list_discounts(user.entity_id))


@discounts_router.post("", response_model=ApiResponse[dict], status_code=201)
def apply_discount(body: ApplyDiscountRequest, service: ProductService = Depends(get_product_service), user: User = Depends(_portal)):
    return ApiResponse(data=service.apply_discount(user.entity_id, body.sku, body.pct))


@discounts_router.delete("/{sku}", status_code=204)
def delete_discount(sku: str, service: ProductService = Depends(get_product_service), user: User = Depends(_portal)):
    service.delete_discount(user.entity_id, sku)
