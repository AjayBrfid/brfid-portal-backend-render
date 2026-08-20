"""ASN creation (vendor) and goods-receipt inspection (warehouse) — the latter is the most
cross-cutting flow in the whole vendor domain: on inspection, accepted qty increases warehouse
on_hand; rejected qty auto-creates a VendorReturn; once the PO is fully received, this
auto-dispatches a TransferOrder to whichever PurchaseRequest/StoreReturn the originating RFQ
was raised for (combining any pre-existing reservation with what the vendor just delivered, or
shipping the vendor-delivered qty on its own if no reservation was ever held back).
"""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.fulfillment import InventoryReservation
from app.models.procurement import PurchaseOrder, PurchaseOrderStatus
from app.models.shipping import Asn, AsnItem, GoodsReceipt
from app.models.vendor_return import VendorReturn
from app.repositories.procurement_repository import PurchaseOrderRepository
from app.repositories.shipping_repository import AsnRepository
from app.utils.pagination import PaginationParams


class AsnService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = AsnRepository(session)
        self.pos = PurchaseOrderRepository(session)

    def create_asn(self, vendor_id: uuid.UUID, po_id: uuid.UUID, shipped_qty: int, expected_delivery_date: date | None, transport_charge=None) -> Asn:
        po = self.pos.get_for_vendor(vendor_id, po_id)
        if not po:
            raise NotFoundException("Purchase order not found")
        if po.status != PurchaseOrderStatus.ACCEPTED and po.status != PurchaseOrderStatus.IN_PRODUCTION and po.status != PurchaseOrderStatus.READY_TO_SHIP:
            raise ConflictException(f"Cannot create an ASN for a PO with status '{po.status.value}'")
        # One ASN per PO — once submitted it's locked; a vendor whose shipment gets partially
        # rejected corrects and resubmits the SAME ASN via resubmit_after_rejection() rather
        # than filing a second, disconnected one.
        if self.repo.list_for_po(po_id):
            raise ConflictException("An ASN has already been submitted for this purchase order.")
        asn = self.repo.add(
            Asn(ref_code=self.repo.next_ref_code(), po_id=po_id, shipped_qty=shipped_qty, expected_delivery_date=expected_delivery_date, transport_charge=transport_charge, draft_status="Draft")
        )
        self.repo.add_item(AsnItem(asn_id=asn.id, po_id=po_id, sku_variant_id=po.sku_variant_id, ordered_qty=po.quantity, shipped_qty=shipped_qty))
        po.status = PurchaseOrderStatus.READY_TO_SHIP
        self.session.commit()
        return asn

    def submit_asn(self, vendor_id: uuid.UUID, asn_id: uuid.UUID, user_id: uuid.UUID | None = None) -> Asn:
        asn = self._get_asn_for_vendor(vendor_id, asn_id)
        asn.draft_status = "Submitted"
        self.session.commit()
        if user_id:
            from app.services.audit_service import AuditService

            AuditService(self.session).log(user_id, "vendor", "ASN Submitted", f"ASN {asn.ref_code} submitted.", "asn", asn.id)
        return asn

    def resubmit_after_rejection(
        self, vendor_id: uuid.UUID, asn_id: uuid.UUID, shipped_qty: int, expected_delivery_date: date | None, batch_no: str | None,
        shipment_data: dict | None = None, freight_data: dict | None = None,
    ) -> Asn:
        """The vendor's one correction path: after a partial/full rejection, the SAME ASN's
        shipped_qty/dates/batch are updated for the corrected shipment and its stale
        GoodsReceipt is cleared so the warehouse can re-inspect — a fresh Asn row would leave
        the original rejection's GoodsReceipt/VendorReturn orphaned from the corrected shipment.
        The replacement shipment is physically its own trip (own dispatch date, transporter,
        driver, vehicle, tracking, freight), so shipment_data/freight_data update those same
        Shipment/FreightPayment rows in place rather than being create-only fields — the
        invoice itself is left untouched since it already covers the full original order and
        isn't re-billed for a like-for-like replacement."""
        from app.repositories.shipping_repository import ShipmentRepository

        asn = self._get_asn_for_vendor(vendor_id, asn_id)
        receipt = self.repo.get_goods_receipt(asn_id)
        if not receipt or receipt.inspection_status.value not in ("partial", "rejected"):
            raise ConflictException("This ASN is not open for correction.")

        asn.shipped_qty = shipped_qty
        asn.expected_delivery_date = expected_delivery_date
        for item in self.repo.items_for_asn(asn_id):
            item.shipped_qty = shipped_qty
            if batch_no:
                item.batch_no = batch_no

        if shipment_data:
            shipment = ShipmentRepository(self.session).get_for_asn(asn_id)
            if shipment:
                shipment.dispatch_date = shipment_data.get("dispatch_date") or shipment.dispatch_date
                shipment.expected_delivery = expected_delivery_date
                shipment.transporter = shipment_data.get("transporter") or shipment.transporter
                shipment.driver_name = shipment_data.get("driver_name")
                shipment.driver_contact = shipment_data.get("driver_contact")
                shipment.vehicle_no = shipment_data.get("vehicle_no") or shipment.vehicle_no
                shipment.tracking_no = shipment_data.get("tracking_no")
                shipment.packages = shipment_data.get("packages") or shipment.packages

                if freight_data:
                    from app.models.payment import FreightPayment

                    freight = self.session.execute(
                        select(FreightPayment).where(FreightPayment.linked_type == "shipment", FreightPayment.linked_id == shipment.id)
                    ).scalar_one_or_none()
                    base_freight = freight_data.get("base_freight") or 0
                    gst_on_freight = freight_data.get("gst_on_freight") or 0
                    if freight:
                        freight.transporter = shipment.transporter
                        freight.payer = freight_data.get("payer") or freight.payer
                        freight.base_freight = base_freight
                        freight.gst_on_freight = gst_on_freight
                        freight.net_payable_to_transporter = base_freight + gst_on_freight
                        freight.final_liability_amount = base_freight + gst_on_freight
                    else:
                        from app.models.payment import FreightDirection, FreightLinkedType
                        from app.repositories.payment_repository import FreightPaymentRepository

                        FreightPaymentRepository(self.session).add(
                            FreightPayment(
                                direction=FreightDirection.VENDOR_TO_WAREHOUSE, linked_type=FreightLinkedType.SHIPMENT, linked_id=shipment.id,
                                transporter=shipment.transporter, payer=freight_data.get("payer") or "vendor",
                                base_freight=base_freight, gst_on_freight=gst_on_freight,
                                net_payable_to_transporter=base_freight + gst_on_freight, final_liability_amount=base_freight + gst_on_freight,
                            )
                        )

        self.session.delete(receipt)
        self.session.commit()
        return asn

    def _get_asn_for_vendor(self, vendor_id: uuid.UUID, asn_id: uuid.UUID) -> Asn:
        asn = self.repo.get_by_id(asn_id)
        if not asn:
            raise NotFoundException("ASN not found")
        po = self.pos.get_by_id(asn.po_id)
        if not po or po.vendor_id != vendor_id:
            raise NotFoundException("ASN not found")
        return asn

    def _to_out(self, asn: Asn) -> dict:
        # "status" (awaiting_inspection/accepted/partial/rejected) is what WhPrForwarded.jsx
        # actually reads to decide whether to open the Inspect dialog — it was never in this
        # dict at all (only draft_status, a completely different Draft/Submitted concept), so
        # that lookup always failed and the screen fell through to "already fully received"
        # (or, if stock wasn't fully received yet, incorrectly reopened the create-new-ASN form
        # instead of the inspection form for an ASN that was already sitting there awaiting it).
        from sqlalchemy import select as _select
        from app.models.shipping import Invoice as _Invoice
        from app.repositories.shipping_repository import ShipmentRepository

        receipt = self.repo.get_goods_receipt(asn.id)
        status = receipt.inspection_status.value if receipt else "awaiting_inspection"
        # transporter/vehicle_number/driver/tracking live on the linked Shipment, batch_no on
        # the AsnItem line, and invoice totals on the linked Invoice — every one of these is a
        # field the vendor actually submitted on CreateAsnPage.jsx, so the warehouse's
        # Log/Inspect ASN view surfaces all of them here rather than the 3-field subset before.
        shipment = ShipmentRepository(self.session).get_for_asn(asn.id)
        items = self.repo.items_for_asn(asn.id)
        invoice = self.session.execute(_select(_Invoice).where(_Invoice.asn_id == asn.id)).scalar_one_or_none()
        return {
            "id": asn.id, "ref_code": asn.ref_code, "po_id": asn.po_id, "shipped_qty": asn.shipped_qty,
            "expected_delivery_date": asn.expected_delivery_date, "draft_status": asn.draft_status.value,
            "status": status,
            "batch_no": items[0].batch_no if items else None,
            "transporter": shipment.transporter if shipment else None,
            "vehicle_number": shipment.vehicle_no if shipment else None,
            "driver_name": shipment.driver_name if shipment else None,
            "driver_phone": shipment.driver_contact if shipment else None,
            "tracking_no": shipment.tracking_no if shipment else None,
            "packages": shipment.packages if shipment else None,
            "dispatch_date": shipment.dispatch_date if shipment else None,
            "created_date": asn.created_date,
            "invoice": {
                "id": invoice.id, "invoice_number": invoice.invoice_number, "invoice_date": invoice.invoice_date,
                "base_amount": float(invoice.base_amount), "gst_amount": float(invoice.gst_amount),
                "discount_amount": float(invoice.discount_amount), "freight_amount": float(invoice.freight_amount),
                "total_amount": float(invoice.total_amount), "status": invoice.status.value,
            } if invoice else None,
            "accepted_qty": receipt.accepted_qty if receipt else None,
            "rejected_qty": receipt.rejected_qty if receipt else None,
            "rejection_reason": receipt.rejection_reason if receipt else None,
        }

    def list_for_vendor(self, vendor_id: uuid.UUID, params: PaginationParams):
        rows, total = self.repo.list_for_vendor(vendor_id, params)
        return [self._to_out(a) for a in rows], total

    def list_for_warehouse(self, warehouse_id: uuid.UUID, params: PaginationParams, po_id: uuid.UUID | None = None):
        rows, total = self.repo.list_for_warehouse(warehouse_id, params, po_id)
        return [self._to_out(a) for a in rows], total

    def get_detail(self, asn_id: uuid.UUID) -> dict:
        asn = self.repo.get_by_id(asn_id)
        if not asn:
            raise NotFoundException("ASN not found")
        detail = self._to_out(asn)
        detail["items"] = [{"sku_variant_id": i.sku_variant_id, "ordered_qty": i.ordered_qty, "shipped_qty": i.shipped_qty} for i in self.repo.items_for_asn(asn_id)]
        return detail

    def get_detail_for_vendor(self, vendor_id: uuid.UUID, asn_id: uuid.UUID) -> dict:
        """Same as get_detail, but 404s if this ASN's PO doesn't belong to vendor_id -- use this
        for any endpoint taking a client-supplied asn_id, so one vendor can't fetch another
        vendor's ASN (and its nested PO/shipment/invoice data) by guessing/enumerating UUIDs."""
        self._get_asn_for_vendor(vendor_id, asn_id)
        return self.get_detail(asn_id)

    def upload_attachment(self, asn_id: uuid.UUID, file_name: str, url: str, remark: str | None, uploaded_by_role: str):
        from app.models.shipping import AsnAttachment

        return self.repo.add_attachment(AsnAttachment(asn_id=asn_id, file_name=file_name, url=url, remark=remark, uploaded_by_role=uploaded_by_role))

    def record_goods_receipt(
        self,
        warehouse_id: uuid.UUID,
        po_id: uuid.UUID,
        asn_id: uuid.UUID,
        accepted_qty: int,
        rejected_qty: int,
        rejection_reason: str | None,
        user_id: uuid.UUID | None = None,
        attachments: list | None = None,
    ) -> dict:
        from app.services.warehouse.inventory_service import InventoryService
        from app.services.warehouse.transfer_order_service import TransferOrderService

        po = self.pos.get_for_warehouse(warehouse_id, po_id)
        if not po:
            raise NotFoundException("Purchase order not found")
        asn = self.repo.get_by_id(asn_id)
        # str() both sides: po_id here is a raw path-param string, asn.po_id is a UUID object —
        # comparing them directly would silently always be unequal.
        if not asn or str(asn.po_id) != str(po_id):
            raise NotFoundException("ASN not found for this purchase order")
        if self.repo.get_goods_receipt(asn_id):
            raise ConflictException("This ASN has already been inspected")

        received_qty = accepted_qty + rejected_qty
        inspection_status = "rejected" if accepted_qty == 0 and rejected_qty > 0 else ("partial" if rejected_qty > 0 else "accepted")
        receipt = self.repo.add_goods_receipt(
            GoodsReceipt(
                asn_id=asn_id, po_id=po_id, received_qty=received_qty, accepted_qty=accepted_qty,
                rejected_qty=rejected_qty, rejection_reason=rejection_reason, inspection_status=inspection_status,
                inspected_at=datetime.now(timezone.utc),
            )
        )

        inventory = InventoryService(self.session)
        if accepted_qty > 0:
            inventory.increase_on_hand(warehouse_id, po.sku_variant_id, accepted_qty)

        if rejected_qty > 0:
            from app.models.vendor_return import VendorReturnAttachment
            from app.repositories.vendor_return_repository import VendorReturnRepository

            returns = VendorReturnRepository(self.session)
            vendor_return = returns.add(
                VendorReturn(
                    ref_code=returns.next_ref_code(), po_id=po_id, asn_id=asn_id, warehouse_id=warehouse_id,
                    vendor_id=po.vendor_id, sku_variant_id=po.sku_variant_id, qty=rejected_qty,
                    reason=rejection_reason or "Rejected on inspection", status="Initiated",
                )
            )
            for att in (attachments or []):
                returns.add_attachment(VendorReturnAttachment(vendor_return_id=vendor_return.id, file_name=att.file_name, url=att.url))

        transfer_order_ref = None
        po.received_qty += accepted_qty
        if po.received_qty >= po.quantity:
            po.status = PurchaseOrderStatus.DELIVERED
            transfer_order_ref = self._dispatch_on_delivery(po, user_id)

        # The warehouse logging this receipt is what actually confirms physical delivery —
        # flip the vendor-visible shipment status to "Delivered" here rather than leaving it to
        # the vendor to self-report (see ShipmentService.update_status/mark_delivered).
        from app.services.vendor.shipment_service import ShipmentService

        ShipmentService(self.session).mark_delivered(asn_id)

        self.session.commit()
        # transfer_order_ref lets the warehouse UI's success toast link straight to the created
        # Transfer Order — it was never returned before, so that toast branch was unreachable.
        return {"receipt_id": receipt.id, "po_status": po.status.value, "inspection_status": inspection_status, "transfer_order_ref": transfer_order_ref}

    def _dispatch_on_delivery(self, po: PurchaseOrder, user_id: uuid.UUID | None) -> str | None:
        """Once a PO is fully delivered, ship the goods on to whichever PR/StoreReturn the
        originating RFQ was raised for — combining any pre-existing reservation with what the
        vendor just delivered, or shipping the vendor-delivered qty alone if no reservation was
        ever held back (the zero-stock RFQ path)."""
        from app.models.procurement import Rfq
        from app.services.warehouse.transfer_order_service import TransferOrderService

        rfq = self.session.get(Rfq, po.rfq_id)
        if not rfq:
            return None
        transfer_orders = TransferOrderService(self.session)

        reservation = None
        if rfq.pr_id:
            stmt = select(InventoryReservation).where(InventoryReservation.pr_id == rfq.pr_id)
            reservation = self.session.execute(stmt).scalar_one_or_none()
        elif rfq.return_id:
            stmt = select(InventoryReservation).where(InventoryReservation.return_id == rfq.return_id)
            reservation = self.session.execute(stmt).scalar_one_or_none()

        if reservation:
            to = transfer_orders.create_combined_transfer_order(po.warehouse_id, rfq, po.sku_variant_id, reservation, user_id=user_id)
        else:
            to = transfer_orders.create_vendor_transfer_order(po.warehouse_id, rfq, po.sku_variant_id, po.received_qty, user_id=user_id)
        rfq.status = "Closed"
        return to.ref_code
