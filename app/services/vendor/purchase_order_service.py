import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.procurement import PurchaseOrder, PurchaseOrderStatus, Quotation, Rfq
from app.repositories.procurement_repository import PurchaseOrderRepository
from app.utils.pagination import PaginationParams


class PurchaseOrderService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = PurchaseOrderRepository(session)

    def create_po_from_quotation(self, rfq: Rfq, quotation: Quotation) -> PurchaseOrder:
        from app.models.warehouse import Warehouse

        grand_total = quotation.unit_price * rfq.quantity * (1 - quotation.discount_percent / 100) * (1 + quotation.tax_percent / 100)
        # A PO always ships to the warehouse that raised the RFQ — that warehouse's own address
        # IS the delivery address, and was never populated before (permanently null column).
        warehouse = self.session.get(Warehouse, rfq.warehouse_id)
        delivery_address = ", ".join(filter(None, [warehouse.address, warehouse.city, warehouse.state, warehouse.pincode])) if warehouse else None
        po = self.repo.add(
            PurchaseOrder(
                ref_code=self.repo.next_ref_code(),
                rfq_id=rfq.id,
                quotation_id=quotation.id,
                vendor_id=quotation.vendor_id,
                warehouse_id=rfq.warehouse_id,
                sku_variant_id=rfq.sku_variant_id,
                quantity=rfq.quantity,
                unit_price=quotation.unit_price,
                tax_percent=quotation.tax_percent,
                discount_percent=quotation.discount_percent,
                grand_total=round(grand_total, 2),
                delivery_address=delivery_address,
                order_date=date.today(),
                delivery_date=date.today() + timedelta(days=quotation.delivery_days),
                status=PurchaseOrderStatus.PENDING_ACCEPTANCE,
            )
        )
        quotation.status = "Approved"

        from app.services.auth.notification_service import NotificationService
        from app.models.user import User
        from sqlalchemy import select

        recipients = self.session.scalars(select(User).where(User.portal_type == "vendor", User.entity_id == quotation.vendor_id)).all()
        for recipient in recipients:
            NotificationService(self.session).notify_user(recipient.id, "po", "New purchase order", f"You've received a new purchase order {po.ref_code}.", "purchase_order", po.id)
        return po

    def _to_out(self, po: PurchaseOrder) -> dict:
        from app.models.catalog import Sku, SkuVariant
        from app.models.vendor import Vendor
        from app.models.warehouse import Warehouse

        variant = self.session.get(SkuVariant, po.sku_variant_id)
        sku = self.session.get(Sku, variant.sku_id) if variant else None
        vendor = self.session.get(Vendor, po.vendor_id)
        warehouse = self.session.get(Warehouse, po.warehouse_id)
        rfq = self.session.get(Rfq, po.rfq_id)
        return {
            "id": po.id, "ref_code": po.ref_code, "rfq_ref": rfq.ref_code if rfq else None,
            # vendor/quantity are the original names; vendor_name/qty are duplicated aliases —
            # WhPrForwarded.jsx (warehouse "Raise PO" screen) reads vendor_name/qty/warehouse/
            # tax_percent/discount_percent/delivery_address, none of which this dict used to
            # carry at all, so those fields rendered blank throughout that whole screen.
            "vendor": vendor.name if vendor else None, "vendor_name": vendor.name if vendor else None,
            "warehouse": warehouse.name if warehouse else None,
            "sku": variant.variant_code if variant else None, "product": sku.name if sku else None,
            "quantity": po.quantity, "qty": po.quantity,
            "unit_price": float(po.unit_price), "tax_percent": float(po.tax_percent), "discount_percent": float(po.discount_percent),
            "grand_total": float(po.grand_total), "delivery_address": po.delivery_address,
            "order_date": po.order_date, "delivery_date": po.delivery_date, "received_qty": po.received_qty,
            "status": po.status.value, "created_at": po.created_at,
        }

    def list_for_warehouse(self, warehouse_id: uuid.UUID, params: PaginationParams, search: str | None = None, status: str | None = None):
        rows, total = self.repo.list_for_warehouse(warehouse_id, params, search, status)
        return [self._to_out(p) for p in rows], total

    def list_for_vendor(self, vendor_id: uuid.UUID, params: PaginationParams, status: str | None = None):
        rows, total = self.repo.list_for_vendor(vendor_id, params, status)
        return [self._to_out(p) for p in rows], total

    def get_for_warehouse(self, warehouse_id: uuid.UUID, po_id: uuid.UUID) -> PurchaseOrder:
        po = self.repo.get_for_warehouse(warehouse_id, po_id)
        if not po:
            raise NotFoundException("Purchase order not found")
        return po

    def get_for_vendor(self, vendor_id: uuid.UUID, po_id: uuid.UUID) -> PurchaseOrder:
        po = self.repo.get_for_vendor(vendor_id, po_id)
        if not po:
            raise NotFoundException("Purchase order not found")
        return po

    def get_detail_for_warehouse(self, warehouse_id: uuid.UUID, po_id: uuid.UUID) -> dict:
        return self._to_out(self.get_for_warehouse(warehouse_id, po_id))

    def get_detail_for_vendor(self, vendor_id: uuid.UUID, po_id: uuid.UUID) -> dict:
        return self._to_out(self.get_for_vendor(vendor_id, po_id))

    def accept(self, vendor_id: uuid.UUID, po_id: uuid.UUID, user_id: uuid.UUID | None = None) -> dict:
        po = self.get_for_vendor(vendor_id, po_id)
        if po.status != PurchaseOrderStatus.PENDING_ACCEPTANCE:
            raise ConflictException(f"Cannot accept a purchase order with status '{po.status.value}'")
        po.status = PurchaseOrderStatus.ACCEPTED
        self.session.commit()
        if user_id:
            from app.services.audit_service import AuditService

            AuditService(self.session).log(user_id, "vendor", "PO Accepted", f"Purchase Order {po.ref_code} accepted.", "purchase_order", po.id)
        return self._to_out(po)

    def reject(self, vendor_id: uuid.UUID, po_id: uuid.UUID, reason: str | None = None, user_id: uuid.UUID | None = None) -> dict:
        po = self.get_for_vendor(vendor_id, po_id)
        if po.status != PurchaseOrderStatus.PENDING_ACCEPTANCE:
            raise ConflictException(f"Cannot reject a purchase order with status '{po.status.value}'")
        po.status = PurchaseOrderStatus.REJECTED
        self.session.commit()
        if user_id:
            from app.services.audit_service import AuditService

            AuditService(self.session).log(user_id, "vendor", "PO Rejected", f"Purchase Order {po.ref_code} rejected" + (f" ({reason})." if reason else "."), "purchase_order", po.id)
        return self._to_out(po)
