"""Per-portal ticket categories and SLA hours for the Support feature. Kept as plain constants
(not DB-enforced) since category is a free-text column on SupportTicket -- see support.py's
model docstring."""

CATEGORIES_BY_ROLE = {
    "vendor": [
        "Quotation/RFQ Issue", "Purchase Order Issue", "ASN/Shipment Issue", "Invoice/Payment Issue",
        "Freight Payment Issue", "Return Issue", "Catalog Issue", "Account/Access Issue", "Other",
    ],
    "warehouse": [
        "Vendor Relationship Issue", "Store Relationship Issue", "PO/RFQ Issue", "ASN/Goods Inspection Issue",
        "Transfer Order Issue", "Inventory/Catalogue Issue", "Return Issue", "Staff/User Management Issue",
        "System/Audit Log Issue", "Account/Access Issue", "Other",
    ],
    "store": [
        "Purchase Request Issue", "Receiving/Shipment Discrepancy", "Catalog/Pricing Issue",
        "Stock/Low-Stock Alert Issue", "POS/Sales Issue", "Account/Access Issue", "Other",
    ],
}

# hours until sla_due_at, keyed by TicketPriority value
SLA_HOURS_BY_PRIORITY = {
    "urgent": 4,
    "high": 24,
    "medium": 72,
    "low": 120,
}

REOPEN_ALLOWED_STATUSES = {"resolved"}
