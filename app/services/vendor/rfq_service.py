import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.procurement import Rfq, RfqInvitedVendor, RfqStatus
from app.repositories.procurement_repository import RfqRepository
from app.utils.pagination import PaginationParams


class RfqService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = RfqRepository(session)

    def get_supplying_vendor_eligibility(self, warehouse_id: uuid.UUID, sku_variant_id: uuid.UUID) -> list[dict]:
        """A vendor is eligible to be invited to an RFQ for this SKU if it (a) supplies this
        SKU variant per the master catalog, and (b) is actively linked to this warehouse."""
        from app.models.catalog import SkuSupplyingVendor
        from app.models.vendor import Vendor
        from app.models.warehouse import WarehouseVendorLink

        supplying_ids = set(self.session.execute(select(SkuSupplyingVendor.vendor_id).where(SkuSupplyingVendor.sku_variant_id == sku_variant_id)).scalars().all())
        linked_ids = set(
            self.session.execute(
                select(WarehouseVendorLink.vendor_id).where(WarehouseVendorLink.warehouse_id == warehouse_id, WarehouseVendorLink.unlinked_at.is_(None))
            ).scalars().all()
        )
        vendors = self.session.scalars(select(Vendor).where(Vendor.id.in_(supplying_ids))).all() if supplying_ids else []
        return [{"id": v.id, "name": v.name, "eligible": v.id in linked_ids and v.status.value == "Active"} for v in vendors]

    def create_rfq(
        self,
        warehouse_id: uuid.UUID,
        pr_id: uuid.UUID | None,
        sku_variant_id: uuid.UUID,
        quantity: int,
        required_delivery_date: date | None,
        invited_vendor_ids: list[uuid.UUID],
        return_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> Rfq:
        from app.models.catalog import Sku, SkuVariant

        variant = self.session.get(SkuVariant, sku_variant_id)
        sku = self.session.get(Sku, variant.sku_id) if variant else None
        # unit was never populated either (permanently null) — "{quantity} {unit}" rendered as
        # "40 null" in the UI. It isn't its own concept here, just the SKU's own unit of sale.
        unit = (sku.unit if sku else None) or "Pcs"

        rfq = self.repo.add(
            Rfq(
                ref_code=self.repo.next_ref_code(),
                pr_id=pr_id,
                return_id=return_id,
                warehouse_id=warehouse_id,
                sku_variant_id=sku_variant_id,
                quantity=quantity,
                unit=unit,
                # Issue date is simply "today" (when the warehouse actually raised this RFQ);
                # closing date was never populated before (permanently null) — it's the same
                # expected/required date carried over from the triggering retail PR, not an
                # independent vendor-response deadline.
                issue_date=date.today(),
                closing_date=required_delivery_date,
                required_delivery_date=required_delivery_date,
                status=RfqStatus.SENT,
            )
        )
        for vendor_id in invited_vendor_ids:
            self.repo.add_invited_vendor(RfqInvitedVendor(rfq_id=rfq.id, vendor_id=vendor_id))
        self.session.commit()

        from app.services.auth.notification_service import NotificationService
        from app.models.vendor import Vendor
        from app.models.user import User

        notifications = NotificationService(self.session)
        for vendor_id in invited_vendor_ids:
            recipients = self.session.scalars(select(User).where(User.portal_type == "vendor", User.entity_id == vendor_id)).all()
            for recipient in recipients:
                notifications.notify_user(recipient.id, "rfq", "New RFQ invitation", f"You've been invited to quote on RFQ {rfq.ref_code}.", "rfq", rfq.id)
        if user_id:
            from app.services.audit_service import AuditService

            AuditService(self.session).log(user_id, "warehouse", "RFQ Created", f"RFQ {rfq.ref_code} raised for {quantity} unit(s).", "rfq", rfq.id)
        return rfq

    def _to_out(self, rfq: Rfq) -> dict:
        from app.models.catalog import Sku, SkuVariant
        from app.models.fulfillment import PurchaseRequest
        from app.models.procurement import PurchaseOrder
        from app.models.retail import Store, StoreReturn
        from app.models.warehouse import Warehouse

        variant = self.session.get(SkuVariant, rfq.sku_variant_id)
        sku = self.session.get(Sku, variant.sku_id) if variant else None
        warehouse = self.session.get(Warehouse, rfq.warehouse_id)

        # An RFQ is raised from EITHER a PurchaseRequest OR a StoreReturn shortfall — neither
        # carries its own store_id, so the store name has to be resolved through whichever one
        # actually triggered it (this was previously missing entirely, leaving "PR ID"/"Store"
        # blank everywhere this dict is used: the RFQ list, its eye-button dialog, and the full
        # RFQ detail screen).
        pr_ref = return_ref = store_name = None
        if rfq.pr_id:
            pr = self.session.get(PurchaseRequest, rfq.pr_id)
            if pr:
                pr_ref = pr.ref_code
                store = self.session.get(Store, pr.store_id)
                store_name = store.name if store else None
        elif rfq.return_id:
            sr = self.session.get(StoreReturn, rfq.return_id)
            if sr:
                return_ref = sr.ref_code
                store = self.session.get(Store, sr.store_id)
                store_name = store.name if store else None

        from app.repositories.procurement_repository import QuotationRepository

        quotation_count = len(QuotationRepository(self.session).list_for_rfq(rfq.id))
        po = self.session.execute(select(PurchaseOrder).where(PurchaseOrder.rfq_id == rfq.id)).scalar_one_or_none()

        return {
            "id": rfq.id, "ref_code": rfq.ref_code, "pr_ref": pr_ref, "return_ref": return_ref, "store": store_name,
            "warehouse": warehouse.name if warehouse else None,
            "sku": variant.variant_code if variant else None, "product": sku.name if sku else None,
            # quantity/qty and required_delivery_date/required_by are duplicated under both
            # names: the vendor-side RfqsPage.jsx reads `quantity`/`required_delivery_date`,
            # the warehouse-side WhRfqList/WhRfqDetail read `qty`/`required_by` — one dict now
            # serves both instead of the warehouse side silently reading undefined fields.
            "quantity": rfq.quantity, "qty": rfq.quantity, "unit": rfq.unit,
            "required_delivery_date": rfq.required_delivery_date, "required_by": rfq.required_delivery_date,
            "issue_date": rfq.issue_date, "closing_date": rfq.closing_date,
            "status": rfq.status.value,
            "created_at": rfq.created_at,
            "invited_vendor_ids": self.repo.invited_vendor_ids(rfq.id),
            "quotation_count": quotation_count,
            "po_id": po.id if po else None,
            # No stored "selected vendor" column exists on Rfq — a PurchaseOrder only ever
            # gets created via select_vendor, so its vendor_id IS the selection.
            "selected_vendor_id": po.vendor_id if po else None,
        }

    def list_rfqs(self, warehouse_id: uuid.UUID, params: PaginationParams, search: str | None = None, status: str | None = None):
        rows, total = self.repo.list_for_warehouse(warehouse_id, params, search, status)
        return [self._to_out(r) for r in rows], total

    def list_rfqs_for_vendor(self, vendor_id: uuid.UUID, params: PaginationParams, status: str | None = None):
        rows, total = self.repo.list_for_vendor(vendor_id, params, status)
        return [self._to_out(r) for r in rows], total

    def get_rfq(self, warehouse_id: uuid.UUID, rfq_id: uuid.UUID) -> Rfq:
        rfq = self.repo.get_for_warehouse(warehouse_id, rfq_id)
        if not rfq:
            raise NotFoundException("RFQ not found")
        return rfq

    def get_rfq_for_vendor(self, vendor_id: uuid.UUID, rfq_id: uuid.UUID) -> Rfq:
        rfq = self.repo.get_by_id(rfq_id)
        if not rfq or not self.repo.is_vendor_invited(rfq_id, vendor_id):
            raise NotFoundException("RFQ not found")
        return rfq

    def get_rfq_detail_for_vendor(self, vendor_id: uuid.UUID, rfq_id: uuid.UUID) -> dict:
        return self._to_out(self.get_rfq_for_vendor(vendor_id, rfq_id))

    def get_rfq_detail(self, warehouse_id: uuid.UUID, rfq_id: uuid.UUID) -> dict:
        return self._to_out(self.get_rfq(warehouse_id, rfq_id))

    def list_quotations(self, warehouse_id: uuid.UUID, rfq_id: uuid.UUID) -> list:
        from app.repositories.procurement_repository import QuotationRepository

        self.get_rfq(warehouse_id, rfq_id)
        return QuotationRepository(self.session).list_for_rfq(rfq_id)

    def select_vendor(self, warehouse_id: uuid.UUID, rfq_id: uuid.UUID, quotation_id: uuid.UUID, user_id: uuid.UUID | None = None):
        from app.repositories.procurement_repository import QuotationRepository
        from app.services.vendor.purchase_order_service import PurchaseOrderService

        rfq = self.get_rfq(warehouse_id, rfq_id)
        quotation = QuotationRepository(self.session).get_by_id(quotation_id)
        if not quotation or quotation.rfq_id != rfq.id:
            raise NotFoundException("Quotation not found for this RFQ")
        po = PurchaseOrderService(self.session).create_po_from_quotation(rfq, quotation)
        rfq.status = "Purchase Order Generated"
        self.session.commit()
        if user_id:
            from app.services.audit_service import AuditService

            AuditService(self.session).log(user_id, "warehouse", "Vendor Selected", f"Vendor selected for {rfq.ref_code}, PO {po.ref_code} generated.", "rfq", rfq.id)
        return po
