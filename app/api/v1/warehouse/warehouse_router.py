from fastapi import APIRouter, Depends

from app.dependencies.auth import require_portal
from app.dependencies.warehouse import get_warehouse_service
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.schemas.warehouse.warehouse_schemas import (
    OnboardVendorRequest,
    RegisterWarehouseRequest,
    RegisterWarehouseResponse,
    StoreStatusUpdate,
    VendorStatusUpdate,
    WarehouseSettingsUpdate,
)
from app.services.warehouse.warehouse_service import WarehouseService

router = APIRouter(tags=["warehouse-warehouses"])
_portal = require_portal("warehouse")


@router.post("/warehouses/register", response_model=ApiResponse[RegisterWarehouseResponse], status_code=201)
def register(body: RegisterWarehouseRequest, service: WarehouseService = Depends(get_warehouse_service)):
    warehouse = service.register_warehouse(
        body.business_type, body.company_name, body.pan, body.gstin, body.cin, body.state, body.city,
        body.address, body.pincode, body.warehouse_name, body.admin_name, f"{body.country_code} {body.phone}",
        body.email, body.temporary_password,
    )
    return ApiResponse(data=RegisterWarehouseResponse(warehouse_id=warehouse.id, status=warehouse.status.value.lower().replace(" ", "_")))


@router.get("/vendors", response_model=ApiResponse[list[dict]])
def list_vendors(
    search: str | None = None, status: str | None = None, linked: bool | None = None,
    params: PaginationParams = Depends(), service: WarehouseService = Depends(get_warehouse_service), user: User = Depends(_portal),
):
    items, total = service.list_vendor_roster(user.entity_id, params, search, status, linked)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.post("/vendors", status_code=201, response_model=ApiResponse[dict])
def onboard_vendor(body: OnboardVendorRequest, service: WarehouseService = Depends(get_warehouse_service), _: User = Depends(_portal)):
    vendor = service.onboard_vendor(body.name, body.code, body.gstin, body.city, body.rating, body.lead_time_days)
    return ApiResponse(data={"id": vendor.id, "code": vendor.code, "status": vendor.status.value})


@router.get("/vendors/{vendor_id}", response_model=ApiResponse[dict])
def get_vendor(vendor_id: str, service: WarehouseService = Depends(get_warehouse_service), _: User = Depends(_portal)):
    vendor = service.get_vendor_detail(vendor_id)
    return ApiResponse(data={"id": vendor.id, "code": vendor.code, "name": vendor.name, "status": vendor.status.value})


@router.post("/vendors/{vendor_id}/link", response_model=ApiResponse[dict])
def link_vendor(vendor_id: str, service: WarehouseService = Depends(get_warehouse_service), user: User = Depends(_portal)):
    link = service.link_vendor(user.entity_id, vendor_id, user.id)
    return ApiResponse(data={"vendor_id": link.vendor_id, "status": link.status.value})


@router.post("/vendors/{vendor_id}/unlink", response_model=ApiResponse[dict])
def unlink_vendor(vendor_id: str, service: WarehouseService = Depends(get_warehouse_service), user: User = Depends(_portal)):
    link = service.unlink_vendor(user.entity_id, vendor_id)
    return ApiResponse(data={"vendor_id": link.vendor_id, "unlinked_at": link.unlinked_at})


@router.patch("/vendors/{vendor_id}/status", response_model=ApiResponse[dict])
def update_vendor_status(vendor_id: str, body: VendorStatusUpdate, service: WarehouseService = Depends(get_warehouse_service), user: User = Depends(_portal)):
    link = service.update_vendor_status(user.entity_id, vendor_id, body.status)
    return ApiResponse(data={"vendor_id": link.vendor_id, "status": link.status.value})


@router.get("/stores", response_model=ApiResponse[list[dict]])
def list_stores(
    search: str | None = None, status: str | None = None, region: str | None = None, linked: bool | None = None,
    params: PaginationParams = Depends(), service: WarehouseService = Depends(get_warehouse_service), user: User = Depends(_portal),
):
    items, total = service.list_store_roster(user.entity_id, params, search, status, region, linked)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.get("/stores/{store_id}", response_model=ApiResponse[dict])
def get_store(store_id: str, service: WarehouseService = Depends(get_warehouse_service), _: User = Depends(_portal)):
    store = service.get_store_detail(store_id)
    return ApiResponse(data={"id": store.id, "code": store.code, "name": store.name, "status": store.status.value})


@router.post("/stores/{store_id}/link", response_model=ApiResponse[dict])
def link_store(store_id: str, service: WarehouseService = Depends(get_warehouse_service), user: User = Depends(_portal)):
    link = service.link_store(user.entity_id, store_id, user.id)
    return ApiResponse(data={"store_id": link.store_id, "status": link.status.value})


@router.post("/stores/{store_id}/unlink", response_model=ApiResponse[dict])
def unlink_store(store_id: str, service: WarehouseService = Depends(get_warehouse_service), user: User = Depends(_portal)):
    link = service.unlink_store(user.entity_id, store_id)
    return ApiResponse(data={"store_id": link.store_id, "unlinked_at": link.unlinked_at})


@router.patch("/stores/{store_id}/status", response_model=ApiResponse[dict])
def update_store_status(store_id: str, body: StoreStatusUpdate, service: WarehouseService = Depends(get_warehouse_service), user: User = Depends(_portal)):
    link = service.update_store_status(user.entity_id, store_id, body.status)
    return ApiResponse(data={"store_id": link.store_id, "status": link.status.value})


@router.get("/settings/warehouse", response_model=ApiResponse[dict])
def get_settings(service: WarehouseService = Depends(get_warehouse_service), user: User = Depends(_portal)):
    warehouse = service.get_warehouse(user.entity_id)
    return ApiResponse(data={
        "code": warehouse.code,
        "name": warehouse.name,
        "business_type": warehouse.business_type,
        "company_name": warehouse.company_name,
        "pan": warehouse.pan,
        "cin": warehouse.cin,
        "gstin": warehouse.gstin,
        "tax_jurisdiction": warehouse.tax_jurisdiction,
        "state": warehouse.state,
        "city": warehouse.city,
        "address": warehouse.address,
        "pincode": warehouse.pincode,
        "license_no": warehouse.license_no,
        "capacity_sqft": warehouse.capacity_sqft,
        "contact_phone": warehouse.contact_phone,
        "contact_email": warehouse.contact_email,
        "manager_id": warehouse.manager_id,
        "working_days": warehouse.working_days,
        "low_stock_warning_units": warehouse.low_stock_warning_units,
        "critical_stock_warning_units": warehouse.critical_stock_warning_units,
        "operating_hours_from": warehouse.operating_hours_from,
        "operating_hours_to": warehouse.operating_hours_to,
    })


@router.patch("/settings/warehouse", response_model=ApiResponse[dict])
def update_settings(body: WarehouseSettingsUpdate, service: WarehouseService = Depends(get_warehouse_service), user: User = Depends(_portal)):
    warehouse = service.update_settings(user.entity_id, **body.model_dump())
    return ApiResponse(data={"working_days": warehouse.working_days, "low_stock_warning_units": warehouse.low_stock_warning_units, "critical_stock_warning_units": warehouse.critical_stock_warning_units})
