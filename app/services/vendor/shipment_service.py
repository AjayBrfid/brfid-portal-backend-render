import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import InvalidStateTransitionException, NotFoundException
from app.models.shipping import Shipment, ShipmentTimelineEvent
from app.repositories.shipping_repository import ShipmentRepository
from app.utils.pagination import PaginationParams


class ShipmentService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = ShipmentRepository(session)

    def create_shipment(
        self, vendor_id: uuid.UUID, asn_id: uuid.UUID, dispatch_date: date, expected_delivery: date | None,
        transporter: str, driver_name: str | None, driver_contact: str | None, vehicle_no: str | None,
        tracking_no: str | None, weight: Decimal | None, packages: int | None, notes: str | None,
    ) -> Shipment:
        # Dispatch details (transporter/vehicle/dispatch date) are already known at the moment
        # the vendor submits this shipment, so it starts life as "Dispatched" rather than
        # "Packed" — there's no separate warehouse-invisible packing step to wait on, and the
        # vendor shouldn't have to take a second manual action just to reflect what they already
        # told the system. "Delivered" is deliberately NOT settable here — see update_status().
        shipment = self.repo.add(
            Shipment(
                code=self.repo.next_code(), asn_id=asn_id, dispatch_date=dispatch_date, expected_delivery=expected_delivery, transporter=transporter,
                driver_name=driver_name, driver_contact=driver_contact, vehicle_no=vehicle_no, tracking_no=tracking_no,
                weight=weight, packages=packages, notes=notes, status="Dispatched",
            )
        )
        self.repo.add_timeline_event(ShipmentTimelineEvent(shipment_id=shipment.id, status="Dispatched"))
        self.session.commit()
        return shipment

    def _to_out(self, shipment: Shipment) -> dict:
        return {
            "id": shipment.id, "asn_id": shipment.asn_id, "dispatch_date": shipment.dispatch_date,
            "expected_delivery": shipment.expected_delivery, "transporter": shipment.transporter,
            "vehicle_no": shipment.vehicle_no, "tracking_no": shipment.tracking_no, "status": shipment.status.value,
            "timeline": [{"status": e.status, "occurred_at": e.occurred_at, "remarks": e.remarks} for e in self.repo.timeline_for_shipment(shipment.id)],
        }

    def list_for_vendor(self, vendor_id: uuid.UUID, params: PaginationParams):
        rows, total = self.repo.list_for_vendor(vendor_id, params)
        return [self._to_out(s) for s in rows], total

    def get_for_vendor(self, vendor_id: uuid.UUID, shipment_id: uuid.UUID) -> dict:
        shipment = self.repo.get_for_vendor(vendor_id, shipment_id)
        if not shipment:
            raise NotFoundException("Shipment not found")
        return self._to_out(shipment)

    def update_status(self, vendor_id: uuid.UUID, shipment_id: uuid.UUID, status: str, remarks: str | None = None) -> dict:
        # "Delivered" is not vendor-settable: it has no connection to what actually happened at
        # the warehouse otherwise, letting a vendor mark a shipment Delivered before the
        # warehouse ever inspected it. That transition only happens automatically, from
        # mark_delivered() below, once the warehouse records a goods receipt for this shipment's
        # ASN (see AsnService.record_goods_receipt).
        if status == "Delivered":
            raise InvalidStateTransitionException(
                "Delivered is set automatically once the warehouse logs receipt of this shipment — it can't be set manually."
            )
        shipment = self.repo.get_for_vendor(vendor_id, shipment_id)
        if not shipment:
            raise NotFoundException("Shipment not found")
        shipment.status = status
        self.repo.add_timeline_event(ShipmentTimelineEvent(shipment_id=shipment.id, status=status, remarks=remarks))
        self.session.commit()
        return self._to_out(shipment)

    def mark_delivered(self, asn_id: uuid.UUID, remarks: str | None = None) -> None:
        """Called by AsnService.record_goods_receipt once the warehouse logs receipt of an ASN —
        the only path that can move a shipment to "Delivered". A FreightPayment already exists
        for this shipment (created alongside it from the vendor's ASN freight details), so unlike
        the old vendor-triggered transition this does not create another one."""
        shipment = self.repo.get_for_asn(asn_id)
        if not shipment or shipment.status == "Delivered":
            return
        shipment.status = "Delivered"
        self.repo.add_timeline_event(ShipmentTimelineEvent(shipment_id=shipment.id, status="Delivered", remarks=remarks))
