import uuid
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenException, NotFoundException
from app.models.fulfillment import TransferOrder
from app.repositories.fulfillment_repository import TransferOrderRepository
from app.services.warehouse.inventory_service import InventoryService
from app.utils.pagination import PaginationParams


class TransferOrderService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = TransferOrderRepository(session)
        self.inventory = InventoryService(session)

    def create_transfer_order(
        self,
        warehouse_id: uuid.UUID,
        store_id: uuid.UUID,
        sku_variant_id: uuid.UUID,
        qty: int,
        source_type: str,
        pr_id: uuid.UUID | None = None,
        return_id: uuid.UUID | None = None,
    ) -> TransferOrder:
        # Every Transfer Order, regardless of source, means this qty is physically leaving the
        # warehouse for a store right now — so on_hand drops here, the one place every path
        # (stock, combined, vendor, return replenishment) funnels through.
        self.inventory.decrease_on_hand(warehouse_id, sku_variant_id, qty)
        to = self.repo.add(
            TransferOrder(
                ref_code=self.repo.next_ref_code(),
                pr_id=pr_id,
                return_id=return_id,
                warehouse_id=warehouse_id,
                store_id=store_id,
                sku_variant_id=sku_variant_id,
                quantity=qty,
                source_type=source_type,
                status="Pending",
            )
        )
        return to

    def dispatch_to_owner(self, warehouse_id: uuid.UUID, rfq, sku_variant_id: uuid.UUID, qty: int, source_type: str, user_id: uuid.UUID | None = None) -> TransferOrder:
        """Ships `qty` to whichever PR or Return this RFQ was raised for, and marks that
        PR/Return fulfilled. `rfq.pr_id`/`rfq.return_id` are mutually exclusive (Phase 4)."""
        if rfq.pr_id:
            from app.repositories.fulfillment_repository import PurchaseRequestRepository

            pr = PurchaseRequestRepository(self.session).get_by_id(rfq.pr_id)
            to = self.create_transfer_order(warehouse_id, pr.store_id, sku_variant_id, qty, source_type, pr_id=pr.id)
            pr.fulfilment_type = "stock"
            pr.fulfilment_ref_type = "transfer_order"
            pr.fulfilment_ref_id = to.id
            if user_id:
                from app.services.audit_service import AuditService

                AuditService(self.session).log(
                    user_id, "warehouse", "Request Fulfilled", f"{pr.ref_code} fulfilled via {to.ref_code} ({source_type})", "purchase_request", pr.id
                )
            return to

        from app.repositories.store_return_repository import StoreReturnRepository

        sr = StoreReturnRepository(self.session).get_by_id(rfq.return_id)
        to = self.create_transfer_order(warehouse_id, sr.store_id, sku_variant_id, qty, source_type, return_id=sr.id)
        sr.resolution_transfer_order_id = to.id
        return to

    def create_combined_transfer_order(self, warehouse_id: uuid.UUID, rfq, sku_variant_id: uuid.UUID, reservation, user_id: uuid.UUID | None = None) -> TransferOrder:
        total_qty = reservation.reserved_qty + reservation.vendor_qty
        to = self.dispatch_to_owner(warehouse_id, rfq, sku_variant_id, total_qty, "Combined Stock + Vendor", user_id=user_id)
        self.session.delete(reservation)
        return to

    def create_vendor_transfer_order(self, warehouse_id: uuid.UUID, rfq, sku_variant_id: uuid.UUID, qty: int, user_id: uuid.UUID | None = None) -> TransferOrder:
        return self.dispatch_to_owner(warehouse_id, rfq, sku_variant_id, qty, "Vendor Procurement", user_id=user_id)

    def _to_list_item(self, to: TransferOrder) -> dict:
        from app.models.catalog import Sku, SkuVariant
        from app.models.retail import Store

        store = self.session.get(Store, to.store_id)
        variant = self.session.get(SkuVariant, to.sku_variant_id)
        sku = self.session.get(Sku, variant.sku_id) if variant else None
        pr_ref = None
        if to.pr_id:
            from app.repositories.fulfillment_repository import PurchaseRequestRepository

            pr = PurchaseRequestRepository(self.session).get_by_id(to.pr_id)
            pr_ref = pr.ref_code if pr else None
        return {
            "id": to.id, "ref_code": to.ref_code, "pr_ref": pr_ref, "store": store.name if store else None,
            "sku": variant.variant_code if variant else None, "product": sku.name if sku else None, "qty": to.quantity,
            "source_type": to.source_type.value, "status": to.status.value, "created_at": to.created_at,
            "dispatched_at": to.dispatched_at, "delivered_at": to.delivered_at,
        }

    def list_transfer_orders(self, warehouse_id: uuid.UUID, params: PaginationParams, search: str | None, status: str | None, source_type: str | None, date_from: date | None = None, date_to: date | None = None):
        rows, total = self.repo.list_for_warehouse(warehouse_id, params, search, status, source_type, date_from, date_to)
        return [self._to_list_item(t) for t in rows], total

    def get_transfer_order(self, warehouse_id: uuid.UUID, to_id: uuid.UUID) -> TransferOrder:
        to = self.repo.get_for_warehouse(warehouse_id, to_id)
        if not to:
            raise NotFoundException("Transfer order not found")
        return to

    def get_transfer_order_detail(self, warehouse_id: uuid.UUID, to_id: uuid.UUID) -> dict:
        to = self.get_transfer_order(warehouse_id, to_id)
        detail = self._to_list_item(to)
        detail["shipment"] = (
            {"transporter": to.transporter, "vehicle_number": to.vehicle_number, "tracking_number": to.tracking_number,
             "packages": to.packages, "remarks": to.remarks, "dispatched_at": to.dispatched_at}
            if to.dispatched_at else None
        )
        return detail

    def dispatch_transfer_order(self, warehouse_id: uuid.UUID, to_id: uuid.UUID, transporter: str, vehicle_number: str, tracking_number: str | None, packages: int, remarks: str | None) -> dict:
        to = self.get_transfer_order(warehouse_id, to_id)
        to.transporter = transporter
        to.vehicle_number = vehicle_number
        to.tracking_number = tracking_number
        to.packages = packages
        to.remarks = remarks
        to.status = "Dispatched"
        to.dispatched_at = datetime.now(timezone.utc)
        if to.return_id:
            from app.repositories.store_return_repository import StoreReturnRepository

            store_return = StoreReturnRepository(self.session).get_by_id(to.return_id)
            if store_return:
                store_return.status = "dispatched"

        from app.services.retail.receiving_service import ReceivingService

        ReceivingService(self.session).create_receiving_item(to.id, to.sku_variant_id, to.quantity)
        self.session.commit()

        from app.services.auth.notification_service import NotificationService

        NotificationService(self.session).create_for_roles(
            "store", to.store_id, ["store-admin", "store-manager"],
            "Shipment dispatched", f"{to.ref_code} has been dispatched and is on its way — {to.quantity} unit(s) via {transporter}.",
            "transfer_order", "transfer_order", to.id,
        )
        return self.get_transfer_order_detail(warehouse_id, to_id)

    def update_status(self, warehouse_id: uuid.UUID, to_id: uuid.UUID, status: str) -> dict:
        if status == "Cancelled":
            # Deliberate business rule — transfer orders can never be cancelled once created.
            raise ForbiddenException("Transfer orders cannot be cancelled")
        to = self.get_transfer_order(warehouse_id, to_id)
        to.status = status
        if status == "Delivered":
            to.delivered_at = datetime.now(timezone.utc)
        self.session.commit()
        return self.get_transfer_order_detail(warehouse_id, to_id)
