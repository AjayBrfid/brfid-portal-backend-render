"""Portal identity constants shared by every router's require_portal()/require_role() checks."""

PORTAL_SUPER_ADMIN = "super_admin"
PORTAL_WAREHOUSE = "warehouse"
PORTAL_VENDOR = "vendor"
PORTAL_STORE = "store"

# users.portal_type — who this login belongs to.
PORTAL_TYPES = [PORTAL_SUPER_ADMIN, PORTAL_WAREHOUSE, PORTAL_VENDOR, PORTAL_STORE]
