import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.fulfillment import TransferOrder
from app.models.retail import ReceivingItem
from app.utils.period import period_start

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _fmt_date(dt: datetime) -> str:
    return f"{dt.day} {MONTHS[dt.month - 1]} {dt.year}"


class ReceivingService:
    def __init__(self, session: Session):
        self.session = session

    def create_receiving_item(self, transfer_order_id: uuid.UUID, sku_variant_id: uuid.UUID, expected_qty: int) -> ReceivingItem:
        """Called when a transfer order is dispatched — one row per line item awaiting the
        store's physical verification."""
        item = ReceivingItem(transfer_order_id=transfer_order_id, sku_variant_id=sku_variant_id, expected_qty=expected_qty, status="Pending")
        self.session.add(item)
        self.session.flush()
        return item

    def _increase_store_stock(self, store_id: uuid.UUID, sku_variant_id: uuid.UUID, qty: int) -> None:
        if qty <= 0:
            return
        from app.models.retail import StoreInventory

        row = self.session.get(StoreInventory, (store_id, sku_variant_id))
        if not row:
            row = StoreInventory(store_id=store_id, sku_variant_id=sku_variant_id, quantity=0)
            self.session.add(row)
            self.session.flush()
        row.quantity += qty
        row.updated_at = datetime.now(timezone.utc)

    def _mark_delivered(self, to: TransferOrder) -> None:
        if to.status.value != "Delivered":
            to.status = "Delivered"
            to.delivered_at = datetime.now(timezone.utc)

    def _to_out(self, item: ReceivingItem) -> dict:
        from app.models.catalog import Sku, SkuVariant
        from app.models.warehouse import Warehouse

        to = self.session.get(TransferOrder, item.transfer_order_id)
        variant = self.session.get(SkuVariant, item.sku_variant_id)
        sku = self.session.get(Sku, variant.sku_id) if variant else None
        warehouse = self.session.get(Warehouse, to.warehouse_id) if to else None
        return {
            "id": item.id, "shipment": to.ref_code if to else None, "product": sku.name if sku else None,
            "warehouse": warehouse.name if warehouse else None, "expected": item.expected_qty, "received": item.received_qty,
            "status": item.status.value, "condition": item.condition.value if item.condition else None,
            "issue_type": item.issue_type, "issue_qty": item.issue_qty or 0, "issue_note": item.issue_note or "",
            "return_type": item.return_type.value if item.return_type else None,
        }

    def list_receiving(self, store_id: uuid.UUID) -> list[dict]:
        stmt = (
            select(ReceivingItem)
            .join(TransferOrder, TransferOrder.id == ReceivingItem.transfer_order_id)
            .where(TransferOrder.store_id == store_id)
            .order_by(ReceivingItem.created_at.desc())
        )
        rows = self.session.scalars(stmt).all()
        return [self._to_out(item) for item in rows]

    def _get_item(self, store_id: uuid.UUID, item_id: uuid.UUID) -> ReceivingItem:
        stmt = (
            select(ReceivingItem)
            .join(TransferOrder, TransferOrder.id == ReceivingItem.transfer_order_id)
            .where(ReceivingItem.id == item_id, TransferOrder.store_id == store_id)
        )
        row = self.session.execute(stmt).scalar_one_or_none()
        if not row:
            raise NotFoundException("Receiving item not found")
        return row

    def record_count(self, store_id: uuid.UUID, item_id: uuid.UUID, received: int, condition: str, user_id: uuid.UUID | None = None) -> dict:
        item = self._get_item(store_id, item_id)
        if received > item.expected_qty:
            raise ConflictException("Received quantity cannot exceed expected quantity")
        item.received_qty = received
        item.condition = condition
        if condition == "Good":
            item.status = "Verified"
            to = self.session.get(TransferOrder, item.transfer_order_id)
            self._mark_delivered(to)
            self._increase_store_stock(store_id, item.sku_variant_id, received)
        self.session.commit()
        if user_id:
            from app.services.audit_service import AuditService

            AuditService(self.session).log(user_id, "store", "Receiving Recorded", f"Recorded {received} unit(s) received for item {item_id} ({condition}).", "receiving_item", item.id)
        return self._to_out(item)

    def raise_issue(self, store_id: uuid.UUID, item_id: uuid.UUID, issue_type: str, issue_qty: int, issue_note: str, return_type: str, user_id: uuid.UUID | None = None) -> dict:
        from app.services.retail.store_return_service import StoreReturnService

        item = self._get_item(store_id, item_id)
        to = self.session.get(TransferOrder, item.transfer_order_id)
        item.issue_type = issue_type
        item.issue_qty = issue_qty
        item.issue_note = issue_note
        item.return_type = return_type
        item.status = "Return Requested" if return_type == "Replenishment" else "Written Off"

        self._mark_delivered(to)
        good_qty = (item.received_qty or 0) - issue_qty
        self._increase_store_stock(store_id, item.sku_variant_id, good_qty)

        decision = "replenish" if return_type == "Replenishment" else "writeoff"
        store_return = StoreReturnService(self.session).create_store_return(
            store_id, to.warehouse_id, to.pr_id, item.sku_variant_id, issue_qty, issue_note, decision, user_id
        )
        item.store_return_id = store_return.id
        self.session.commit()
        if user_id:
            from app.services.audit_service import AuditService

            AuditService(self.session).log(user_id, "store", "Receiving Issue Raised", f"Issue raised for item {item_id} ({issue_type}, {issue_qty} unit(s), {return_type}).", "receiving_item", item.id)

        out = self._to_out(item)
        result = {"receiving_item": out}
        if return_type == "Replenishment":
            result["replenishment"] = {
                "id": store_return.ref_code, "pr_id": to.pr_id, "source_shipment_id": to.ref_code,
                "product": out["product"], "qty": issue_qty, "warehouse": out["warehouse"],
                "requested": _fmt_date(store_return.requested_at), "status": "Requested",
            }
        else:
            result["write_off"] = {
                "id": f"WO-{store_return.ref_code.split('-')[-1]}", "shipment": to.ref_code, "product": out["product"],
                "warehouse": out["warehouse"], "qty": issue_qty, "issue_type": issue_type, "reason": issue_note,
                "date": _fmt_date(datetime.now(timezone.utc)),
            }
        return result

    def list_write_offs(self, store_id: uuid.UUID, period: str = "weekly") -> list[dict]:
        stmt = (
            select(ReceivingItem)
            .join(TransferOrder, TransferOrder.id == ReceivingItem.transfer_order_id)
            .where(
                TransferOrder.store_id == store_id, ReceivingItem.return_type == "Write-off",
                ReceivingItem.created_at >= period_start(period),
            )
        )
        rows = self.session.scalars(stmt).all()
        items = []
        for item in rows:
            out = self._to_out(item)
            items.append(
                {"id": f"WO-{str(item.id)[:4]}", "shipment": out["shipment"], "product": out["product"], "warehouse": out["warehouse"],
                 "qty": item.issue_qty or 0, "reason": item.issue_note or "", "date": _fmt_date(item.created_at)}
            )
        return items
