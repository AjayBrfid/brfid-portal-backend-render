"""Product Catalog compat. Confirmed against src/pages/CatalogPage.jsx: the frontend reads
`sku` as the actual SKU/variant code string (not a `sku_variant_id`), `goodsId`, `vendorId`, and
`documents: [{name, uploadedDate}]` -- built here from the same CatalogService already wired for
the real `/api/v1/vendor/catalog` routes.
"""
from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy import select

from app.compat.schemas import CamelModel
from app.compat.vendor.common import envelope, iso, paginate_list, vendor_meta
from app.dependencies.vendor import get_catalog_service, get_current_vendor
from app.models.catalog import SkuVariant
from app.models.vendor import Vendor, VendorCatalogDocument
from app.schemas.common import PaginationParams
from app.services.vendor.catalog_service import CatalogService

router = APIRouter(prefix="/catalog", tags=["vendor-compat-catalog"])

_ALL = PaginationParams(page=1, limit=100000)


def _catalog_out(session, service: CatalogService, row) -> dict:
    data = service.to_out(row)
    sku = None
    if data["sku_variant_id"]:
        variant = session.get(SkuVariant, data["sku_variant_id"])
        sku = variant.variant_code if variant else None
    documents = session.execute(
        select(VendorCatalogDocument).where(VendorCatalogDocument.submission_id == row.id).order_by(VendorCatalogDocument.uploaded_date)
    ).scalars().all()
    return {
        "id": str(data["id"]),
        "code": data["code"],
        "vendorId": str(row.vendor_id),
        "goodsId": str(row.goods_id) if row.goods_id else None,
        "name": data["name"],
        "productType": data["product_type"],
        "gender": data["gender"],
        "fabric": data["fabric"],
        "colour": data["colour"],
        "size": data["size"],
        "gsm": data["gsm"],
        "description": data["description"],
        "sku": sku,
        "createdDate": iso(row.created_date),
        "submittedDate": iso(data["submitted_date"]),
        "documents": [{"name": d.file_name, "uploadedDate": iso(d.uploaded_date)} for d in documents],
        "status": data["status"],
    }


class CatalogCreateRequest(CamelModel):
    goods_id: str | None = None
    product_type: str
    gender: str
    fabric: str
    colour: str
    size: str
    gsm: int
    description: str | None = None


class CatalogUpdateRequest(CamelModel):
    product_type: str | None = None
    gender: str | None = None
    fabric: str | None = None
    colour: str | None = None
    size: str | None = None
    gsm: int | None = None
    description: str | None = None


@router.get("")
def list_catalog(
    page: int = 1, limit: int = 20, search: str | None = None, goods_id: str | None = None,
    service: CatalogService = Depends(get_catalog_service), vendor: Vendor = Depends(get_current_vendor),
):
    # Not service.list_for_vendor() — that already runs rows through to_out() and returns
    # plain dicts, which _catalog_out() (expecting a raw VendorCatalogSubmission) can't re-read.
    rows, _ = service.repo.catalog_for_vendor(vendor.id, _ALL)
    items = [_catalog_out(service.session, service, r) for r in rows]
    if goods_id:
        items = [i for i in items if i["goodsId"] == goods_id]
    if search:
        q = search.lower()
        items = [i for i in items if q in (i["name"] or "").lower()]
    page_items, total = paginate_list(items, page, limit)
    return envelope(page_items, vendor_meta(page, limit, total))


@router.get("/{submission_id}")
def get_catalog_item(submission_id: str, service: CatalogService = Depends(get_catalog_service), vendor: Vendor = Depends(get_current_vendor)):
    row = service.get_for_vendor(vendor.id, submission_id)
    return envelope(_catalog_out(service.session, service, row))


@router.post("", status_code=201)
def create_catalog_item(body: CatalogCreateRequest, service: CatalogService = Depends(get_catalog_service), vendor: Vendor = Depends(get_current_vendor)):
    # CatalogPage.jsx submits from an existing Goods item and never sends a name of its own
    # (its "Product" field is just a disabled display of the good's name) — use that good's
    # real name rather than synthesizing one, so it matches what the vendor actually sees.
    good = service.repo.get_good(body.goods_id) if body.goods_id else None
    name = good.name if good else f"{body.product_type} - {body.colour}"
    row = service.create(vendor.id, body.goods_id, name, body.product_type, body.gender, body.fabric, body.colour, body.size, body.gsm, body.description)
    return envelope(_catalog_out(service.session, service, row))


@router.patch("/{submission_id}")
def update_catalog_item(submission_id: str, body: CatalogUpdateRequest, service: CatalogService = Depends(get_catalog_service), vendor: Vendor = Depends(get_current_vendor)):
    fields = body.model_dump(exclude_unset=True)
    row = service.update(vendor.id, submission_id, **fields)
    return envelope(_catalog_out(service.session, service, row))


@router.post("/{submission_id}/documents", status_code=201)
def upload_catalog_documents(submission_id: str, files: list[UploadFile], service: CatalogService = Depends(get_catalog_service), vendor: Vendor = Depends(get_current_vendor)):
    docs = service.upload_documents(vendor.id, submission_id, files)
    return envelope([{"name": d.file_name, "uploadedDate": iso(d.uploaded_date)} for d in docs])
