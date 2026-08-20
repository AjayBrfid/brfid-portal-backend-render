from fastapi import APIRouter, Depends, UploadFile

from app.dependencies.vendor import get_catalog_service, get_current_vendor
from app.models.vendor import Vendor
from app.schemas.common import ApiResponse, PaginationParams, build_meta
from app.schemas.vendor.vendor_schemas import CatalogCreateRequest, CatalogUpdateRequest
from app.services.vendor.catalog_service import CatalogService

router = APIRouter(prefix="/catalog", tags=["vendor-catalog"])


@router.get("", response_model=ApiResponse[list[dict]])
def list_catalog(params: PaginationParams = Depends(), service: CatalogService = Depends(get_catalog_service), vendor: Vendor = Depends(get_current_vendor)):
    items, total = service.list_for_vendor(vendor.id, params)
    return ApiResponse(data=[service.to_out(r) for r in items], meta=build_meta(params.page, params.limit, total))


@router.get("/{submission_id}", response_model=ApiResponse[dict])
def get_catalog_item(submission_id: str, service: CatalogService = Depends(get_catalog_service), vendor: Vendor = Depends(get_current_vendor)):
    return ApiResponse(data=service.to_out(service.get_for_vendor(vendor.id, submission_id)))


@router.post("", response_model=ApiResponse[dict], status_code=201)
def create_catalog_item(body: CatalogCreateRequest, service: CatalogService = Depends(get_catalog_service), vendor: Vendor = Depends(get_current_vendor)):
    row = service.create(vendor.id, body.goods_id, body.name, body.product_type, body.gender, body.fabric, body.colour, body.size, body.gsm, body.description)
    return ApiResponse(data=service.to_out(row))


@router.patch("/{submission_id}", response_model=ApiResponse[dict])
def update_catalog_item(submission_id: str, body: CatalogUpdateRequest, service: CatalogService = Depends(get_catalog_service), vendor: Vendor = Depends(get_current_vendor)):
    row = service.update(vendor.id, submission_id, **body.model_dump())
    return ApiResponse(data=service.to_out(row))


@router.post("/{submission_id}/documents", response_model=ApiResponse[list[dict]], status_code=201)
def upload_catalog_documents(submission_id: str, files: list[UploadFile], service: CatalogService = Depends(get_catalog_service), vendor: Vendor = Depends(get_current_vendor)):
    docs = service.upload_documents(vendor.id, submission_id, files)
    return ApiResponse(data=[{"id": d.id, "file_name": d.file_name, "url": d.url} for d in docs])
