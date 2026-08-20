import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.models.retail import StoreReturn
from app.repositories.store_return_repository import StoreReturnRepository
from app.utils.pagination import PaginationParams

_RPL_STEPS = ['Requested', 'Warehouse Processing', 'Dispatched', 'In Transit', 'Delivered']


class StoreReturnService:
    """Retail-side creation of a StoreReturn (from receiving's raise_issue), plus a store's
    read-only view of its own returns. Warehouse-side listing/resolution lives in
    app/services/warehouse/store_return_service.py."""

    def __init__(self, session: Session):
        self.session = session
        self.repo = StoreReturnRepository(session)

    def _derived_status(self, sr: StoreReturn) -> str:
        """StoreReturn.status only ever reaches "dispatched" and sticks there (see
        TransferOrderService.dispatch_transfer_order) — it's never flipped to reflect the
        linked TransferOrder actually being delivered. Re-derive the live status from that
        TransferOrder instead of trusting the stale stored value, the same way PurchaseRequest's
        own status is derived rather than stored."""
        if sr.decision.value == "writeoff":
            return "Written Off" if sr.status.value == "writtenoff" else "Requested"
        if sr.resolution_transfer_order_id:
            from app.models.fulfillment import TransferOrder

            to = self.session.get(TransferOrder, sr.resolution_transfer_order_id)
            if to:
                return {"Pending": "Warehouse Processing", "Dispatched": "Dispatched", "Delivered": "Delivered", "Completed": "Delivered"}.get(to.status.value, "Warehouse Processing")
        if sr.resolution_rfq_id:
            return "Warehouse Processing"
        return "Requested"

    def to_out(self, sr: StoreReturn) -> dict:
        from app.models.catalog import Sku, SkuVariant
        from app.models.fulfillment import PurchaseRequest, TransferOrder
        from app.models.warehouse import Warehouse

        variant = self.session.get(SkuVariant, sr.sku_variant_id)
        sku = self.session.get(Sku, variant.sku_id) if variant else None
        pr = self.session.get(PurchaseRequest, sr.pr_id) if sr.pr_id else None
        warehouse = self.session.get(Warehouse, sr.warehouse_id)
        to = self.session.get(TransferOrder, sr.resolution_transfer_order_id) if sr.resolution_transfer_order_id else None
        return {
            "id": sr.ref_code, "source_shipment_id": to.ref_code if to else None,
            "pr_id": pr.ref_code if pr else None, "product": sku.name if sku else None,
            "sku": variant.variant_code if variant else None, "qty": sr.qty,
            "warehouse": warehouse.name if warehouse else None,
            "requested": sr.requested_at.date().isoformat(), "status": self._derived_status(sr),
        }

    def get_for_store(self, store_id: uuid.UUID, ref: str) -> StoreReturn:
        sr = self.repo.get_for_store(store_id, ref)
        if not sr:
            raise NotFoundException("Replenishment request not found")
        return sr

    def get_tracking_for_store(self, store_id: uuid.UUID, ref: str) -> dict:
        status = self._derived_status(self.get_for_store(store_id, ref))
        if status == "Written Off":
            return {"steps": [{"label": "Requested", "done": True, "current": False}, {"label": "Written Off", "done": True, "current": True}]}
        current_idx = _RPL_STEPS.index(status) if status in _RPL_STEPS else 0
        return {"steps": [{"label": label, "done": i <= current_idx, "current": i == current_idx} for i, label in enumerate(_RPL_STEPS)]}

    def create_store_return(
        self, store_id: uuid.UUID, warehouse_id: uuid.UUID, pr_id: uuid.UUID | None, sku_variant_id: uuid.UUID,
        qty: int, reason: str, decision: str, user_id: uuid.UUID | None = None,
    ) -> StoreReturn:
        sr = self.repo.add(
            StoreReturn(
                ref_code=self.repo.next_ref_code(),
                pr_id=pr_id,
                store_id=store_id,
                warehouse_id=warehouse_id,
                sku_variant_id=sku_variant_id,
                qty=qty,
                reason=reason,
                decision=decision,
                status="pending",
            )
        )
        self.session.commit()
        if user_id:
            from app.services.audit_service import AuditService

            AuditService(self.session).log(user_id, "store", "Store Return Raised", f"Store return {sr.ref_code} raised for {qty} unit(s) ({decision}).", "store_return", sr.id)

        from app.services.auth.notification_service import NotificationService
        from app.models.retail import Store

        store = self.session.get(Store, store_id)
        NotificationService(self.session).create_for_roles(
            "warehouse", warehouse_id, ["wh-admin", "wh-manager", "wh-inbound-manager", "wh-outbound-manager", "wh-inventory-manager"],
            "Store submitted a return", f"{store.name if store else 'A store'} reported an issue with {qty} unit(s) ({sr.ref_code}).",
            "return", "store_return", sr.id,
        )
        return sr

    def list_for_store(self, store_id: uuid.UUID, params: PaginationParams, search: str | None = None):
        rows, total = self.repo.list_for_store(store_id, params, search)
        return [self.to_out(r) for r in rows], total
