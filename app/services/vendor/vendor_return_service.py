import uuid
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.repositories.vendor_return_repository import VendorReturnRepository
from app.utils.pagination import PaginationParams


class VendorReturnService:
    """Created automatically from ASN inspection rejections (see
    app/services/vendor/asn_service.py::record_goods_receipt) — this service covers the
    subsequent lifecycle only (warehouse review, vendor pickup/dispatch, completion)."""

    def __init__(self, session: Session):
        self.session = session
        self.repo = VendorReturnRepository(session)

    def _to_out(self, row) -> dict:
        # sku/vendor were never resolved here (unlike the vendor-side compat _return_out, which
        # does) — WhReturns.jsx's "To Vendor" table reads exactly these two keys, so they always
        # rendered blank even though the real IDs were on the row all along.
        from app.models.catalog import Sku, SkuVariant
        from app.models.procurement import PurchaseOrder
        from app.models.shipping import Asn
        from app.models.vendor import Vendor

        attachments = self.repo.attachments_for_return(row.id)
        po = self.session.get(PurchaseOrder, row.po_id)
        asn = self.session.get(Asn, row.asn_id)
        vendor = self.session.get(Vendor, row.vendor_id)
        variant = self.session.get(SkuVariant, row.sku_variant_id)
        sku = self.session.get(Sku, variant.sku_id) if variant else None
        return {
            "id": row.id, "ref_code": row.ref_code, "po_id": row.po_id, "po_ref": po.ref_code if po else None,
            "asn_id": row.asn_id, "asn_ref": asn.ref_code if asn else None, "qty": row.qty,
            "sku": variant.variant_code if variant else None, "product": sku.name if sku else None,
            "vendor": vendor.name if vendor else None,
            "refund_amount": float(row.refund_amount) if row.refund_amount else None, "reason": row.reason,
            "status": row.status.value, "review_remarks": row.review_remarks, "pickup_date": row.pickup_date,
            "transporter": row.transporter, "driver_name": row.driver_name, "driver_contact": row.driver_contact,
            "vehicle_no": row.vehicle_no, "tracking_no": row.tracking_no,
            # Raw `url` is a bare storage key (SeaweedFS/S3), not a browsable link — callers
            # fetch the actual image through the id-keyed attachment-download endpoint instead,
            # which resolves it to a signed URL server-side.
            "attachments": [{"id": str(a.id), "file_name": a.file_name} for a in attachments],
        }

    def mark_delivered(self, warehouse_id: uuid.UUID, return_id: uuid.UUID) -> dict:
        """Warehouse-side confirmation that a return shipment the vendor created (see
        app/compat/vendor/return_router.py::create_return_shipment) has arrived — the vendor's
        own complete() covers the same "In Transit" -> "Received" transition from their side."""
        row = self.repo.get_for_warehouse(warehouse_id, return_id)
        if not row:
            raise NotFoundException("Vendor return not found")
        if row.status.value != "In Transit":
            raise ConflictException(f"Cannot mark a return delivered from status '{row.status.value}'")
        row.status = "Received"
        self.session.commit()
        return self._to_out(row)

    def list_for_vendor(self, vendor_id: uuid.UUID, params: PaginationParams, status: str | None = None):
        rows, total = self.repo.list_for_vendor(vendor_id, params, status)
        return [self._to_out(r) for r in rows], total

    def list_for_warehouse(self, warehouse_id: uuid.UUID, params: PaginationParams, status: str | None = None):
        rows, total = self.repo.list_for_warehouse(warehouse_id, params, status)
        return [self._to_out(r) for r in rows], total

    def get_for_vendor(self, vendor_id: uuid.UUID, return_id: uuid.UUID) -> dict:
        row = self.repo.get_for_vendor(vendor_id, return_id)
        if not row:
            raise NotFoundException("Vendor return not found")
        return self._to_out(row)

    def get_for_warehouse(self, warehouse_id: uuid.UUID, return_id: uuid.UUID) -> dict:
        row = self.repo.get_for_warehouse(warehouse_id, return_id)
        if not row:
            raise NotFoundException("Vendor return not found")
        return self._to_out(row)

    def approve(self, warehouse_id: uuid.UUID, return_id: uuid.UUID, remarks: str | None, refund_amount=None) -> dict:
        row = self.repo.get_for_warehouse(warehouse_id, return_id)
        if not row:
            raise NotFoundException("Vendor return not found")
        if row.status.value != "Initiated":
            raise ConflictException(f"Cannot approve a return with status '{row.status.value}'")
        row.status = "Approved"
        row.review_remarks = remarks
        row.refund_amount = refund_amount
        self.session.commit()
        return self._to_out(row)

    def reject(self, warehouse_id: uuid.UUID, return_id: uuid.UUID, remarks: str | None) -> dict:
        row = self.repo.get_for_warehouse(warehouse_id, return_id)
        if not row:
            raise NotFoundException("Vendor return not found")
        if row.status.value != "Initiated":
            raise ConflictException(f"Cannot reject a return with status '{row.status.value}'")
        row.status = "Rejected"
        row.review_remarks = remarks
        self.session.commit()
        return self._to_out(row)

    def schedule_pickup(self, warehouse_id: uuid.UUID, return_id: uuid.UUID, pickup_date: date, transporter: str, vehicle_no: str | None) -> dict:
        row = self.repo.get_for_warehouse(warehouse_id, return_id)
        if not row:
            raise NotFoundException("Vendor return not found")
        if row.status.value != "Approved":
            raise ConflictException(f"Cannot schedule pickup for a return with status '{row.status.value}'")
        row.pickup_date = pickup_date
        row.transporter = transporter
        row.vehicle_no = vehicle_no
        self.session.commit()
        return self._to_out(row)

    def dispatch(self, warehouse_id: uuid.UUID, return_id: uuid.UUID, tracking_no: str | None) -> dict:
        row = self.repo.get_for_warehouse(warehouse_id, return_id)
        if not row:
            raise NotFoundException("Vendor return not found")
        row.status = "In Transit"
        row.tracking_no = tracking_no
        self.session.commit()
        return self._to_out(row)

    def complete(self, vendor_id: uuid.UUID, return_id: uuid.UUID) -> dict:
        row = self.repo.get_for_vendor(vendor_id, return_id)
        if not row:
            raise NotFoundException("Vendor return not found")
        row.status = "Received"
        self.session.commit()
        return self._to_out(row)
