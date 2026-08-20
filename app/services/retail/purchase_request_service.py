"""Thin retail-side wrapper creating/reading the SAME PurchaseRequest rows the warehouse
Purchase Requests screen consumes (see app/services/warehouse/purchase_request_service.py)."""
import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.catalog import Sku, SkuVariant
from app.models.fulfillment import PurchaseRequest
from app.models.warehouse import Warehouse, WarehouseStoreLink
from app.repositories.fulfillment_repository import PurchaseRequestRepository
from app.services.warehouse.purchase_request_service import PurchaseRequestService
from app.utils.pagination import PaginationParams

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def format_display_date(dt: datetime) -> str:
    return f"{dt.day} {MONTHS[dt.month - 1]} {dt.year}"


class RetailPurchaseRequestService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = PurchaseRequestRepository(session)
        self.warehouse_side = PurchaseRequestService(session)

    def _derive_retail_status(self, pr: PurchaseRequest) -> str:
        """Retail's own 4-stage view (Preparing/Dispatched/In Transit/Delivered) is coarser
        than the warehouse-side derivation — 'In Transit' isn't separately tracked by
        TransferOrder, so it collapses into 'Dispatched' here."""
        if pr.fulfilment_ref_type and pr.fulfilment_ref_type.value == "transfer_order":
            from app.models.fulfillment import TransferOrder

            to = self.session.get(TransferOrder, pr.fulfilment_ref_id)
            if to:
                if to.status.value in ("Delivered", "Completed"):
                    return "Delivered"
                if to.status.value == "Dispatched":
                    return "Dispatched"
        return "Preparing"

    def _resolve_warehouse(self, store_id, warehouse_name: str) -> Warehouse:
        stmt = (
            select(Warehouse)
            .join(WarehouseStoreLink, WarehouseStoreLink.warehouse_id == Warehouse.id)
            .where(WarehouseStoreLink.store_id == store_id, Warehouse.name == warehouse_name)
        )
        warehouse = self.session.execute(stmt).scalar_one_or_none()
        if not warehouse:
            raise ConflictException(f"Store is not linked to warehouse '{warehouse_name}'")
        return warehouse

    def _to_out(self, pr: PurchaseRequest) -> dict:
        warehouse = self.session.get(Warehouse, pr.warehouse_id)
        variant = self.session.get(SkuVariant, pr.sku_variant_id)
        sku = self.session.get(Sku, variant.sku_id) if variant else None
        return {
            "id": pr.ref_code, "date": format_display_date(pr.requested_at), "warehouse": warehouse.name if warehouse else None,
            "product": sku.name if sku else None, "sku": variant.variant_code if variant else None, "items": 1,
            "qty": pr.requested_qty, "status": self._derive_retail_status(pr),
        }

    def create_request(self, store_id, sku_code: str, warehouse_name: str, qty: int, expected_date: date | None, user_id: uuid.UUID | None = None) -> dict:
        warehouse = self._resolve_warehouse(store_id, warehouse_name)
        variant = self.session.execute(select(SkuVariant).where(SkuVariant.variant_code == sku_code)).scalar_one_or_none()
        if not variant:
            raise NotFoundException("SKU not found")
        pr = self.warehouse_side.create_purchase_request(store_id, warehouse.id, variant.id, qty, expected_date)
        if user_id:
            from app.services.audit_service import AuditService

            AuditService(self.session).log(user_id, "store", "Purchase Request Created", f"Purchase request {pr.ref_code} raised for {qty} unit(s) of {sku_code}.", "purchase_request", pr.id)
        return self._to_out(pr)

    def create_bulk(self, store_id, warehouse_name: str, expected_date: date | None, items: list[tuple[str, int]], user_id: uuid.UUID | None = None) -> list[dict]:
        warehouse = self._resolve_warehouse(store_id, warehouse_name)
        results = []
        for sku_code, qty in items:
            variant = self.session.execute(select(SkuVariant).where(SkuVariant.variant_code == sku_code)).scalar_one_or_none()
            if not variant:
                continue
            pr = self.warehouse_side.create_purchase_request(store_id, warehouse.id, variant.id, qty, expected_date)
            if user_id:
                from app.services.audit_service import AuditService

                AuditService(self.session).log(user_id, "store", "Purchase Request Created", f"Purchase request {pr.ref_code} raised for {qty} unit(s) of {sku_code}.", "purchase_request", pr.id)
            results.append({"id": pr.ref_code, "sku": sku_code, "qty": qty, "status": "Preparing"})
        return results

    def list_requests(self, store_id, params: PaginationParams, search: str | None, status: str | None):
        rows, total = self.repo.list_for_store(store_id, params, search)
        items = [self._to_out(pr) for pr in rows]
        if status:
            items = [i for i in items if i["status"] == status]
        return items, total

    def get_request(self, store_id, ref: str) -> dict:
        stmt = select(PurchaseRequest).where(PurchaseRequest.ref_code == ref, PurchaseRequest.store_id == store_id)
        pr = self.session.execute(stmt).scalar_one_or_none()
        if not pr:
            raise NotFoundException("Purchase request not found")
        return self._to_out(pr)

    def get_tracking(self, store_id, ref: str) -> dict:
        stmt = select(PurchaseRequest).where(PurchaseRequest.ref_code == ref, PurchaseRequest.store_id == store_id)
        pr = self.session.execute(stmt).scalar_one_or_none()
        if not pr:
            raise NotFoundException("Purchase request not found")
        status = self._derive_retail_status(pr)
        stages = ["Preparing", "Dispatched", "In Transit", "Delivered"]
        current_idx = stages.index(status) if status in stages else 0
        return {"steps": [{"label": stage, "done": i <= current_idx, "current": i == current_idx} for i, stage in enumerate(stages)]}
