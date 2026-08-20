from fastapi import APIRouter, Depends

from app.dependencies.vendor import get_current_vendor, get_shipment_service
from app.models.vendor import Vendor
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.schemas.vendor.vendor_schemas import ShipmentCreateRequest, ShipmentStatusUpdateRequest
from app.services.vendor.shipment_service import ShipmentService

router = APIRouter(prefix="/shipments", tags=["vendor-shipments"])


@router.get("", response_model=ApiResponse[list[dict]])
def list_shipments(params: PaginationParams = Depends(), service: ShipmentService = Depends(get_shipment_service), vendor: Vendor = Depends(get_current_vendor)):
    items, total = service.list_for_vendor(vendor.id, params)
    return ApiResponse(data=items, meta=build_meta(params.page, params.limit, total))


@router.get("/{shipment_id}", response_model=ApiResponse[dict])
def get_shipment(shipment_id: str, service: ShipmentService = Depends(get_shipment_service), vendor: Vendor = Depends(get_current_vendor)):
    return ApiResponse(data=service.get_for_vendor(vendor.id, shipment_id))


@router.post("", response_model=ApiResponse[dict], status_code=201)
def create_shipment(body: ShipmentCreateRequest, service: ShipmentService = Depends(get_shipment_service), vendor: Vendor = Depends(get_current_vendor)):
    shipment = service.create_shipment(
        vendor.id, body.asn_id, body.dispatch_date, body.expected_delivery, body.transporter, body.driver_name,
        body.driver_contact, body.vehicle_no, body.tracking_no, body.weight, body.packages, body.notes,
    )
    return ApiResponse(data=service.get_for_vendor(vendor.id, shipment.id))


@router.patch("/{shipment_id}/status", response_model=ApiResponse[dict])
def update_shipment_status(shipment_id: str, body: ShipmentStatusUpdateRequest, service: ShipmentService = Depends(get_shipment_service), vendor: Vendor = Depends(get_current_vendor)):
    return ApiResponse(data=service.update_status(vendor.id, shipment_id, body.status, body.remarks))
