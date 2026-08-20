"""vms-sa-react's original Store Approval + Store Detail contract (`/stores...`).
Approve/reject/block/unblock call straight through to AdminStoreService — the same service the
real `/api/v1/super-admin/stores...` routes use. `manager`/`contact` are pulled directly off the
Store row (a plain User lookup by manager_user_id, not a new business rule). `documents` mirrors
the vendor compat router's `compliance` dict pattern -- the registration-time uploads (see
StoreService.upload_store_document) land in Store.documents (a plain {doc_type: storage_key}
JSON column, not a separate table like vendor's), but the Super Admin profile page never
surfaced them or most of the other registration fields (PAN/GSTIN/CIN/business type/etc.)."""
import mimetypes

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compat.schemas import admin_meta
from app.compat.super_admin.schemas import RejectBody, StoreOut
from app.core.exceptions import NotFoundException
from app.dependencies.auth import require_portal
from app.dependencies.database import get_db
from app.dependencies.super_admin import get_admin_store_service
from app.models.retail import Store
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams
from app.services.retail.store_service import ALLOWED_DOC_TYPES
from app.services.super_admin.store_admin_service import AdminStoreService
from app.utils.storage import get_storage_client

router = APIRouter(prefix="/stores", tags=["super-admin-compat-stores"])
_portal = require_portal("super_admin")


def _store_to_out(session: Session, store: Store) -> dict:
    # manager_user_id is never actually assigned anywhere in the codebase (no "add a store
    # manager" flow exists) -- it's always null, so it looked up nothing. The one real person
    # on file for a store is whoever registered it (the store-admin user), so that's who
    # "Manager"/"Email" now show instead of a permanently-empty lookup.
    admin_user = session.execute(
        select(User).where(User.entity_id == store.id, User.portal_type == "store")
    ).scalars().first()
    docs = store.documents or {}
    documents = {
        doc_type: {"uploaded": doc_type in docs, "url": f"/stores/{store.code}/compliance-documents/{doc_type}" if doc_type in docs else None}
        for doc_type in ALLOWED_DOC_TYPES
    }
    return {
        "id": store.code, "name": store.name, "code": store.code, "city": store.city, "state": store.state,
        "region": store.region, "manager": admin_user.name if admin_user else None, "email": admin_user.email if admin_user else None,
        "contact": store.contact_phone, "store_type": store.store_type.value, "business_type": store.business_type,
        "pan": store.pan, "gstin": store.gstin, "cin": store.cin, "years_in_operation": store.years_in_operation,
        "address": store.address, "pincode": store.pincode,
        "status": store.status.value, "opened_on": store.opened_on.date(), "documents": documents,
    }


def _get_store_or_404(service: AdminStoreService, store_id: str) -> Store:
    store = service.repo.get_by_code(store_id)
    if not store:
        raise NotFoundException(f"Store '{store_id}' not found")
    return store


@router.get("", response_model=ApiResponse[list[StoreOut]])
def list_stores(
    search: str | None = None, status: str | None = None, params: PaginationParams = Depends(),
    session: Session = Depends(get_db), service: AdminStoreService = Depends(get_admin_store_service), _: User = Depends(_portal),
):
    rows, total = service.repo.list_all(params, search, status)
    items = [_store_to_out(session, s) for s in rows]
    return ApiResponse(data=items, meta=admin_meta(params.page, params.limit, total))


@router.get("/stats", response_model=ApiResponse[dict])
def store_stats(service: AdminStoreService = Depends(get_admin_store_service), _: User = Depends(_portal)):
    return ApiResponse(data=service.stats())


@router.get("/{store_id}", response_model=ApiResponse[StoreOut])
def get_store(
    store_id: str, session: Session = Depends(get_db),
    service: AdminStoreService = Depends(get_admin_store_service), _: User = Depends(_portal),
):
    store = _get_store_or_404(service, store_id)
    return ApiResponse(data=_store_to_out(session, store))


@router.get("/{store_id}/compliance-documents/{doc_type}")
def get_store_compliance_document(
    store_id: str, doc_type: str, service: AdminStoreService = Depends(get_admin_store_service), _: User = Depends(_portal),
):
    store = _get_store_or_404(service, store_id)
    stored_value = (store.documents or {}).get(doc_type)
    if doc_type not in ALLOWED_DOC_TYPES or not stored_value:
        raise NotFoundException("Compliance document not found")
    content_type = mimetypes.guess_type(stored_value)[0] or "application/octet-stream"
    return Response(content=get_storage_client().read(stored_value), media_type=content_type)


@router.post("/{store_id}/approve", response_model=ApiResponse[dict])
def approve_store(store_id: str, service: AdminStoreService = Depends(get_admin_store_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.approve(store_id, admin))


@router.post("/{store_id}/reject", response_model=ApiResponse[dict])
def reject_store(store_id: str, body: RejectBody, service: AdminStoreService = Depends(get_admin_store_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.reject(store_id, admin, body.reason))


@router.post("/{store_id}/block", response_model=ApiResponse[dict])
def block_store(store_id: str, service: AdminStoreService = Depends(get_admin_store_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.block(store_id, admin))


@router.post("/{store_id}/unblock", response_model=ApiResponse[dict])
def unblock_store(store_id: str, service: AdminStoreService = Depends(get_admin_store_service), admin: User = Depends(_portal)):
    return ApiResponse(data=service.unblock(store_id, admin))
