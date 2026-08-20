"""Seed a handful of representative support tickets across all three raising portals (vendor,
warehouse, store), so the Support feature's UI has real data to show instead of empty tables.

Usage:
    python scripts/seed_support_tickets.py

Idempotent: does nothing if any support_tickets rows already exist.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal
from app.models.support import SupportTicket
from app.models.user import User
from app.services.support.support_service import SupportService

# (portal_type, category, subject, description, priority, status)
MOCK_TICKETS = [
    ("vendor", "Purchase Order Issue", "PO quantity mismatch on last order",
     "The purchase order we received shows 500 units but our RFQ response was for 450. Please confirm the correct quantity before we proceed with dispatch.",
     "high", "open"),
    ("vendor", "Invoice/Payment Issue", "Payment not received for Invoice #INV-1042",
     "We submitted invoice INV-1042 three weeks ago and haven't received payment yet. Could someone check the status?",
     "urgent", "in_progress"),
    ("vendor", "ASN/Shipment Issue", "Unable to attach delivery challan to ASN",
     "The file upload keeps failing when I try to attach our delivery challan PDF to the ASN submission form.",
     "medium", "resolved"),
    ("vendor", "Catalog Issue", "Incorrect MRP shown for SKU variant",
     "One of our SKU variants is showing an outdated MRP in the catalog. Please update it to match our latest price list.",
     "low", "closed"),
    ("warehouse", "Vendor Relationship Issue", "Vendor repeatedly missing dispatch dates",
     "A vendor has missed their committed dispatch date on three consecutive POs. Requesting guidance on next steps.",
     "high", "open"),
    ("warehouse", "Transfer Order Issue", "Transfer order stuck in Dispatched status",
     "A transfer order to one of our stores has been stuck in 'Dispatched' for over a week with no delivery confirmation.",
     "medium", "in_progress"),
    ("warehouse", "System/Audit Log Issue", "Audit log export missing recent entries",
     "The exported audit log Excel file seems to be missing entries from the last two days.",
     "low", "resolved"),
    ("store", "Receiving/Shipment Discrepancy", "Received fewer units than the transfer order stated",
     "We received 80 units against a transfer order for 100 units. Requesting a reconciliation.",
     "high", "open"),
    ("store", "POS/Sales Issue", "POS terminal freezing during checkout",
     "Our main POS terminal freezes intermittently during checkout, causing delays at the counter.",
     "urgent", "reopened"),
    ("store", "Stock/Low-Stock Alert Issue", "Low-stock alerts not triggering for fast-moving SKUs",
     "We're not receiving low-stock alerts for a few fast-moving SKUs even though they're below threshold.",
     "medium", "closed"),
]


def main():
    db = SessionLocal()
    try:
        if db.query(SupportTicket.id).first():
            print("Support tickets already exist — skipping (idempotent).")
            return

        service = SupportService(db)
        created = 0
        for portal_type, category, subject, description, priority, status in MOCK_TICKETS:
            user = db.query(User).filter(User.portal_type == portal_type).order_by(User.created_at).first()
            if not user:
                print(f"No {portal_type} user found — skipping '{subject}'.")
                continue
            ticket = service.create_ticket(user, category, subject, description, priority, None, None)
            if status != "open":
                ticket.status = status
                if status in ("resolved", "closed", "reopened"):
                    ticket.resolved_at = datetime.utcnow() - timedelta(days=1)
                if status == "closed":
                    ticket.closed_at = datetime.utcnow()
                db.commit()
            created += 1
            print(f"Created {ticket.ticket_number} ({portal_type}/{status}): {subject}")

        print(f"Done — {created} mock support ticket(s) created.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
