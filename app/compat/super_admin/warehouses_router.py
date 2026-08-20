"""vms-sa-react's original Warehouse Approval + Zones + Stock Movements contract
(`/warehouses...`, plus `/zones/:id` mounted flat per the old spec). Approve/reject/block/unblock
and the zone/movement listings all call straight through to AdminWarehouseService — the same
service the real `/api/v1/super-admin/warehouses...` routes use. The only new code is pulling
`capacitySqft`/`establishedYear`/`contact` directly off the Warehouse row (AdminWarehouseService's
own `_to_out` never exposed them) and renaming a couple of keys to match the old field names.
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.compat.schemas import admin_meta
from app.compat.super_admin.schemas import MovementOut, RejectBody, WarehouseInventoryOut, WarehouseOut, ZoneOut
from app.core.exceptions import NotFoundException
from app.dependencies.auth import require_portal
from app.dependencies.database import get_db
from app.dependencies.super_admin import get_admin_warehouse_service
from app.models.user import User
from app.models.warehouse import Warehouse
from app.schemas.common import ApiResponse, PaginationParams
from app.services.super_admin.warehouse_admin_service import AdminWarehouseService
from app.services.warehouse.inventory_service import InventoryService

router = APIRouter(prefix="/warehouses", tags=["super-admin-compat-warehouses"])
zone_router = APIRouter(prefix="/zones", tags=["super-admin-compat-zones"])
_portal = require_portal("super_admin")


def _warehouse_to_out(service: AdminWarehouseService, warehouse: Warehouse) -> dict:
    base = service._to_out(warehouse)
    return {
        "id": base["id"], "name": base["name"], "code": base["id"], "city": base["city"], "state": base["state"],
        "manager": base["manager"], "email": warehouse.contact_email, "contact": warehouse.contact_phone,
        "business_type": warehouse.business_type, "company_name": warehouse.company_name, "pan": warehouse.pan,
        "gstin": warehouse.gstin, "cin": warehouse.cin, "tax_jurisdiction": warehouse.tax_jurisdiction,
        "address": warehouse.address, "pincode": warehouse.pincode, "license_no": warehouse.license_no,
        "capacity_sqft": warehouse.capacity_sqft,
        "utilized_pct": base["utilized_pct"], "zone_count": base["zone_count"], "status": base["status"],
        "registered_on": base["registered_on"].date(), "established_year": warehouse.established_year,
    }


def _zone_to_compat(zone: dict) -> dict:
    return {
        "id": zone["id"], "warehouse_id": zone["warehouse_code"], "warehouse_name": zone["warehouse_name"],
        "name": zone["name"], "capacity": zone["capacity"], "utilized_pct": zone["utilized_pct"],
        "product_count": zone["product_count"], "status": zone["status"],
    }


def _movement_to_compat(movement: dict) -> dict:
    return {
        "id": movement["id"], "type": movement["type"], "product_name": movement["product_name"],
        "unit": movement["unit"], "quantity": movement["quantity"], "warehouse_id": movement["warehouse_code"],
        "warehouse_name": movement["warehouse_name"], "from_location": movement["from_location"],
        "to_location": movement["to_location"], "date": movement["occurred_at"].date(),
        "reference_id": movement["reference_id"], "performed_by": movement["performed_by"],
    }


@router.get("", response_model=ApiResponse[list[WarehouseOut]])
def list_warehouses(
    search: str | None = None, status: str | None = None, params: PaginationParams = Depends(),
    service: AdminWarehouseService = Depends(get_admin_warehouse_service), _: User = Depends(_portal),
):
    rows, total = service.repo.list_all(params, search, status)
    items = [_warehouse_to_out(service, w) for w in rows]
    return ApiResponse(data=items, meta=admin_meta(params.page, params.limit, total))


@router.get("/stats", response_model=ApiResponse[dict])
def warehouse_stats(service: AdminWarehouseService = Depends(get_admin_warehouse_service), _: User = Depends(_portal)):
    return ApiResponse(data=service.stats())


@router.get("/{warehouse_id}", response_model=ApiResponse[WarehouseOut])
def get_warehouse(warehouse_id: str, service: AdminWarehouseService = Depends(get_admin_warehouse_service), _: User = Depends(_portal)):
    warehouse = service.repo.get_by_code(warehouse_id)
    if not warehouse:
        raise NotFoundException(f"Warehouse '{warehouse_id}' not found")
    return ApiResponse(data=_warehouse_to_out(service, warehouse))


@router.get("/{warehouse_id}/inventory", response_model=ApiResponse[list[WarehouseInventoryOut]])
def list_warehouse_inventory(
    warehouse_id: str, search: str | None = None, category: str | None = None, status: str | None = None,
    params: PaginationParams = Depends(), session: Session = Depends(get_db),
    service: AdminWarehouseService = Depends(get_admin_warehouse_service), _: User = Depends(_portal),
):
    # The Warehouse Profile "Stock" tab used to read from vendor-stock data filtered by
    # warehouseId — a field VendorGood doesn't actually have (see vendor_stock_router.py's
    # docstring), so it silently always showed nothing. This is the same real per-SKU inventory
    # the warehouse portal's own Inventory tab reads (InventoryService.list_inventory), just
    # exposed here for a super admin looking at one specific warehouse.
    warehouse = service.repo.get_by_code(warehouse_id)
    if not warehouse:
        raise NotFoundException(f"Warehouse '{warehouse_id}' not found")
    items, total = InventoryService(session).list_inventory(warehouse.id, params, search, category, status)
    return ApiResponse(data=items, meta=admin_meta(params.page, params.limit, total))


@router.post("/{warehouse_id}/approve", response_model=ApiResponse[dict])
def approve_warehouse(warehouse_id: str, service: AdminWarehouseService = Depends(get_admin_warehouse_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.approve(warehouse_id, admin))


@router.post("/{warehouse_id}/reject", response_model=ApiResponse[dict])
def reject_warehouse(warehouse_id: str, body: RejectBody, service: AdminWarehouseService = Depends(get_admin_warehouse_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.reject(warehouse_id, admin, body.reason))


@router.post("/{warehouse_id}/block", response_model=ApiResponse[dict])
def block_warehouse(warehouse_id: str, service: AdminWarehouseService = Depends(get_admin_warehouse_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.block(warehouse_id, admin))


@router.post("/{warehouse_id}/unblock", response_model=ApiResponse[dict])
def unblock_warehouse(warehouse_id: str, service: AdminWarehouseService = Depends(get_admin_warehouse_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.unblock(warehouse_id, admin))


@router.get("/{warehouse_id}/zones", response_model=ApiResponse[list[ZoneOut]])
def list_warehouse_zones(warehouse_id: str, service: AdminWarehouseService = Depends(get_admin_warehouse_service), _: User = Depends(_portal)):
    zones = service.list_zones(warehouse_id)
    return ApiResponse(data=[_zone_to_compat(z) for z in zones])


@router.get("/{warehouse_id}/movements", response_model=ApiResponse[list[MovementOut]])
def list_warehouse_movements(
    warehouse_id: str, search: str | None = None, params: PaginationParams = Depends(),
    service: AdminWarehouseService = Depends(get_admin_warehouse_service), _: User = Depends(_portal),
):
    items, total = service.list_movements(warehouse_id, search, params)
    return ApiResponse(data=[_movement_to_compat(m) for m in items], meta=admin_meta(params.page, params.limit, total))


@zone_router.get("/{zone_id}", response_model=ApiResponse[ZoneOut])
def get_zone(zone_id: uuid.UUID, service: AdminWarehouseService = Depends(get_admin_warehouse_service), _: User = Depends(_portal)):
    zone = service.get_zone(zone_id)
    return ApiResponse(data=_zone_to_compat(zone))
