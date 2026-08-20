import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.retail import StoreReturn
from app.repositories.store_return_repository import StoreReturnRepository
from app.services.warehouse.inventory_service import InventoryService
from app.services.warehouse.transfer_order_service import TransferOrderService
from app.utils.pagination import PaginationParams


class WarehouseStoreReturnService:
    """Warehouse-side listing/resolution of a StoreReturn — creation happens on the retail side
    (see app/services/retail/store_return_service.py, triggered by receiving's raise_issue)."""

    def __init__(self, session: Session):
        self.session = session
        self.repo = StoreReturnRepository(session)
        self.inventory = InventoryService(session)
        self.transfer_orders = TransferOrderService(session)

    def _to_list_item(self, sr: StoreReturn) -> dict:
        from app.models.catalog import Sku, SkuVariant
        from app.models.fulfillment import InventoryReservation, PurchaseRequest
        from app.models.retail import Store

        store = self.session.get(Store, sr.store_id)
        variant = self.session.get(SkuVariant, sr.sku_variant_id)
        sku = self.session.get(Sku, variant.sku_id) if variant else None
        pr = self.session.get(PurchaseRequest, sr.pr_id) if sr.pr_id else None
        resolution = None
        if sr.resolution_transfer_order_id or sr.resolution_rfq_id:
            reserved_qty = None
            if sr.resolution_rfq_id:
                resv = self.session.execute(select(InventoryReservation).where(InventoryReservation.return_id == sr.id)).scalar_one_or_none()
                reserved_qty = resv.reserved_qty if resv else 0
            resolution = {"reserved_qty": reserved_qty, "to_id": sr.resolution_transfer_order_id, "rfq_id": sr.resolution_rfq_id}
        return {
            "ref": sr.ref_code, "pr_ref": pr.ref_code if pr else None, "store": store.name if store else None,
            "product": sku.name if sku else None, "sku": variant.variant_code if variant else None, "qty": sr.qty,
            "reason": sr.reason, "requested_at": sr.requested_at, "decision": sr.decision.value, "status": sr.status.value,
            "resolution": resolution,
        }

    def list_store_returns(self, warehouse_id: uuid.UUID, params: PaginationParams, search: str | None, decision: str | None, status: str | None):
        rows, total = self.repo.list_for_warehouse(warehouse_id, params, search, decision, status)
        return [self._to_list_item(r) for r in rows], total

    def get_store_return(self, warehouse_id: uuid.UUID, ref: str) -> StoreReturn:
        sr = self.repo.get_for_warehouse(warehouse_id, ref)
        if not sr:
            raise NotFoundException("Store return not found")
        return sr

    def get_store_return_detail(self, warehouse_id: uuid.UUID, ref: str) -> dict:
        sr = self.get_store_return(warehouse_id, ref)
        detail = self._to_list_item(sr)
        detail["timeline"] = [
            {"label": "Return Requested", "at": sr.requested_at, "done": True},
            {"label": "Resolved", "at": None, "done": sr.status.value != "pending"},
        ]
        return detail

    def resolve_return(self, warehouse_id: uuid.UUID, ref: str, user_id: uuid.UUID | None = None) -> dict:
        """Server re-checks live available stock and acts on the return's own stored decision —
        never trusts a client-chosen outcome."""
        sr = self.get_store_return(warehouse_id, ref)

        if sr.decision.value == "writeoff":
            sr.status = "writtenoff"
            self.session.commit()
            if user_id:
                from app.services.audit_service import AuditService

                AuditService(self.session).log(user_id, "warehouse", "Return Received", f"{sr.ref_code} written off ({sr.qty} unit(s))", "store_return", sr.id)
            return self._to_list_item(sr)

        from app.services.vendor.rfq_service import RfqService  # Phase 4

        inv = self.inventory.get_or_create_inventory(warehouse_id, sr.sku_variant_id)
        available_qty = inv.available

        if available_qty >= sr.qty:
            self.inventory.reserve_stock(warehouse_id, sr.sku_variant_id, sr.qty)
            to = self.transfer_orders.create_transfer_order(warehouse_id, sr.store_id, sr.sku_variant_id, sr.qty, "Return Replenishment", return_id=sr.id)
            sr.resolution_transfer_order_id = to.id
            sr.status = "replenished"
        else:
            shortfall = sr.qty - available_qty
            eligible_vendor_ids = [v["id"] for v in RfqService(self.session).get_supplying_vendor_eligibility(warehouse_id, sr.sku_variant_id) if v["eligible"]]
            if not eligible_vendor_ids:
                raise ConflictException("No eligible vendor found for this SKU")

            if available_qty > 0:
                self.inventory.reserve_stock(warehouse_id, sr.sku_variant_id, available_qty)
                from app.models.fulfillment import InventoryReservation

                self.session.add(
                    InventoryReservation(
                        warehouse_id=warehouse_id, sku_variant_id=sr.sku_variant_id, return_id=sr.id,
                        reserved_qty=available_qty, total_qty=sr.qty, vendor_qty=shortfall,
                    )
                )
            rfq = RfqService(self.session).create_rfq(warehouse_id, None, sr.sku_variant_id, shortfall, None, eligible_vendor_ids, return_id=sr.id, user_id=user_id)
            sr.resolution_rfq_id = rfq.id
            sr.status = "replenished"

        self.session.commit()
        if user_id:
            from app.services.audit_service import AuditService

            AuditService(self.session).log(user_id, "warehouse", "Return Received", f"{sr.ref_code} resolved ({sr.qty} unit(s), {sr.decision.value})", "store_return", sr.id)
        return self._to_list_item(sr)
