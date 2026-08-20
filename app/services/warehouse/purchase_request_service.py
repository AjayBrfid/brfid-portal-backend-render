import uuid
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.models.fulfillment import InventoryReservation, PurchaseRequest
from app.repositories.fulfillment_repository import PurchaseRequestRepository
from app.services.warehouse.inventory_service import InventoryService
from app.services.warehouse.transfer_order_service import TransferOrderService
from app.utils.pagination import PaginationParams


def _derive_status(session: Session, pr: PurchaseRequest) -> str:
    if pr.approval_status.value == "declined":
        return "declined"
    if pr.fulfilment_ref_type and pr.fulfilment_ref_type.value == "transfer_order":
        from app.models.fulfillment import TransferOrder

        to = session.get(TransferOrder, pr.fulfilment_ref_id)
        if to and to.status.value in ("Delivered", "Completed"):
            return "completed"
        return "fulfilled"
    if pr.fulfilment_ref_type and pr.fulfilment_ref_type.value == "rfq":
        return "forwarded"
    return "pending"


# Order Tracking is the same PR fulfilment state machine as _derive_status above, relabelled
# for that screen's own vocabulary (see WhOrderTracking.jsx's STATUS_OPTIONS).
ORDER_TRACKING_STATUS_LABELS = {
    "pending": "Pending Stock Check",
    "forwarded": "Awaiting Vendor Delivery",
    "fulfilled": "In Transit to Retail",
    "completed": "Delivered to Retail",
    "declined": "Vendor Declined",
}


class PurchaseRequestService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = PurchaseRequestRepository(session)
        self.inventory = InventoryService(session)
        self.transfer_orders = TransferOrderService(session)

    def create_purchase_request(self, store_id: uuid.UUID, warehouse_id: uuid.UUID, sku_variant_id: uuid.UUID, qty: int, required_by: date | None = None, priority: str = "Medium") -> PurchaseRequest:
        pr = self.repo.add(
            PurchaseRequest(
                ref_code=self.repo.next_ref_code(),
                store_id=store_id,
                warehouse_id=warehouse_id,
                sku_variant_id=sku_variant_id,
                requested_qty=qty,
                required_by=required_by,
                priority=priority,
                approval_status="pending",
            )
        )
        self.session.commit()

        from app.models.retail import Store
        from app.services.auth.notification_service import NotificationService

        store = self.session.get(Store, store_id)
        NotificationService(self.session).create_for_roles(
            "warehouse", warehouse_id, ["wh-admin", "wh-manager", "wh-inbound-manager", "wh-outbound-manager", "wh-inventory-manager"],
            "New purchase request from a store", f"{store.name if store else 'A store'} requested {qty} unit(s) ({pr.ref_code}).",
            "pr", "purchase_request", pr.id,
        )
        return pr

    def _to_list_item(self, pr: PurchaseRequest) -> dict:
        from app.models.catalog import Sku, SkuVariant
        from app.models.retail import Store

        store = self.session.get(Store, pr.store_id)
        variant = self.session.get(SkuVariant, pr.sku_variant_id)
        sku = self.session.get(Sku, variant.sku_id) if variant else None
        return {
            "ref": pr.ref_code, "store": store.name if store else None, "product": sku.name if sku else None,
            "sku": variant.variant_code if variant else None, "requested_qty": pr.requested_qty, "requested_at": pr.requested_at,
            "required_by": pr.required_by, "status": _derive_status(self.session, pr),
            "fulfilment": {"type": pr.fulfilment_ref_type.value, "ref_id": pr.fulfilment_ref_id} if pr.fulfilment_ref_type else None,
        }

    def list_purchase_requests(self, warehouse_id: uuid.UUID, params: PaginationParams, search: str | None, status: str | None, date_from: date | None = None, date_to: date | None = None):
        rows, total = self.repo.list_for_warehouse(warehouse_id, params, search, date_from, date_to)
        items = [self._to_list_item(pr) for pr in rows]
        if status:
            items = [i for i in items if i["status"] == status]
        return items, total

    def list_order_tracking(self, warehouse_id: uuid.UUID, params: PaginationParams, search: str | None, status: str | None, date_from: date | None = None, date_to: date | None = None):
        """The end-to-end status of every store request against this warehouse — a genuine
        aggregation over PurchaseRequest -> RFQ/TransferOrder, not its own stored entity."""
        rows, total = self.repo.list_for_warehouse(warehouse_id, params, search, date_from, date_to)
        items = []
        for pr in rows:
            detail = self._to_list_item(pr)
            items.append({
                "pr_ref": detail["ref"], "store": detail["store"], "product": detail["product"], "sku": detail["sku"],
                "requested_at": detail["requested_at"], "status": ORDER_TRACKING_STATUS_LABELS[detail["status"]],
            })
        if status:
            items = [i for i in items if i["status"] == status]
        return items, total

    def get_pr(self, warehouse_id: uuid.UUID, ref: str) -> PurchaseRequest:
        pr = self.repo.get_by_ref(warehouse_id, ref)
        if not pr:
            raise NotFoundException("Purchase request not found")
        return pr

    def get_pr_detail(self, warehouse_id: uuid.UUID, ref: str) -> dict:
        return self._to_list_item(self.get_pr(warehouse_id, ref))

    def fulfil_from_stock(self, warehouse_id: uuid.UUID, ref: str, user_id: uuid.UUID | None = None) -> dict:
        pr = self.get_pr(warehouse_id, ref)
        self.inventory.reserve_stock(warehouse_id, pr.sku_variant_id, pr.requested_qty)  # raises ConflictException (409) if insufficient
        to = self.transfer_orders.create_transfer_order(warehouse_id, pr.store_id, pr.sku_variant_id, pr.requested_qty, "Warehouse Stock", pr_id=pr.id)
        pr.approval_status = "approved"
        pr.fulfilment_type = "stock"
        pr.fulfilment_ref_type = "transfer_order"
        pr.fulfilment_ref_id = to.id
        self.session.commit()
        if user_id:
            from app.services.audit_service import AuditService

            AuditService(self.session).log(user_id, "warehouse", "Request Fulfilled", f"{pr.ref_code} fulfilled from stock ({to.ref_code})", "purchase_request", pr.id)
        return self.transfer_orders.get_transfer_order_detail(warehouse_id, to.id)

    def split_fulfil(self, warehouse_id: uuid.UUID, ref: str, invited_vendor_ids: list[uuid.UUID], user_id: uuid.UUID | None = None) -> dict:
        from app.services.vendor.rfq_service import RfqService  # Phase 4

        pr = self.get_pr(warehouse_id, ref)
        inv = self.inventory.get_or_create_inventory(warehouse_id, pr.sku_variant_id)
        available_qty = inv.available
        shortfall = pr.requested_qty - available_qty
        self.inventory.reserve_stock(warehouse_id, pr.sku_variant_id, available_qty)
        self.session.add(
            InventoryReservation(
                warehouse_id=warehouse_id, sku_variant_id=pr.sku_variant_id, pr_id=pr.id,
                reserved_qty=available_qty, total_qty=pr.requested_qty, vendor_qty=shortfall,
            )
        )
        rfq = RfqService(self.session).create_rfq(warehouse_id, pr.id, pr.sku_variant_id, shortfall, pr.required_by, invited_vendor_ids, user_id=user_id)
        pr.approval_status = "approved"
        pr.fulfilment_type = "split"
        pr.fulfilment_ref_type = "rfq"
        pr.fulfilment_ref_id = rfq.id
        self.session.commit()
        return {"reserved_qty": available_qty, "vendor_qty": shortfall, "rfq_id": rfq.id, "rfq_ref": rfq.ref_code}

    def raise_rfq(self, warehouse_id: uuid.UUID, ref: str, invited_vendor_ids: list[uuid.UUID], user_id: uuid.UUID | None = None) -> dict:
        from app.services.vendor.rfq_service import RfqService  # Phase 4

        pr = self.get_pr(warehouse_id, ref)
        rfq = RfqService(self.session).create_rfq(warehouse_id, pr.id, pr.sku_variant_id, pr.requested_qty, pr.required_by, invited_vendor_ids, user_id=user_id)
        # No reservation here — this is the zero-stock path, nothing is ever held back from
        # available. The ASN dispatch-on-delivery flow (Phase 4) ships the full delivered
        # quantity to this PR's store once the PO is fully in, with no reservation row needed.
        pr.approval_status = "approved"
        pr.fulfilment_type = "rfq"
        pr.fulfilment_ref_type = "rfq"
        pr.fulfilment_ref_id = rfq.id
        self.session.commit()
        return RfqService(self.session).get_rfq_detail(warehouse_id, rfq.id)
