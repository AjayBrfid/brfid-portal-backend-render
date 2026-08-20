"""Role strings and per-portal creatable-role allowlists, reconciled from Backend-WH-Retail's
auth/constants.py + users/constants.py — the only one of the three source projects that actually
enforced role-level RBAC rather than treating `User.role` as a display-only string.
"""

ROLE_SUPER_ADMIN = "super-admin"
# Support ticketing's one new role -- a super_admin-portal user who can handle tickets (reply,
# assign, close) without necessarily holding full super-admin privileges elsewhere. Deliberately
# not a new portal/entity type, just an additional allowed value for User.role.
ROLE_SUPPORT_AGENT = "support-agent"
SUPPORT_STAFF_ROLES = [ROLE_SUPER_ADMIN, ROLE_SUPPORT_AGENT]

ROLE_WH_ADMIN = "wh-admin"
ROLE_WH_MANAGER = "wh-manager"
ROLE_WH_INBOUND_MANAGER = "wh-inbound-manager"
ROLE_WH_OUTBOUND_MANAGER = "wh-outbound-manager"
ROLE_WH_INVENTORY_MANAGER = "wh-inventory-manager"
WAREHOUSE_MANAGER_ROLES = [ROLE_WH_MANAGER, ROLE_WH_INBOUND_MANAGER, ROLE_WH_OUTBOUND_MANAGER, ROLE_WH_INVENTORY_MANAGER]
WAREHOUSE_ROLES = [ROLE_WH_ADMIN, *WAREHOUSE_MANAGER_ROLES]

ROLE_VENDOR_ADMIN = "vendor-admin"
ROLE_VENDOR_MANAGER = "vendor-manager"
VENDOR_ROLES = [ROLE_VENDOR_ADMIN, ROLE_VENDOR_MANAGER]

ROLE_STORE_ADMIN = "store-admin"
ROLE_STORE_MANAGER = "store-manager"
STORE_ROLES = [ROLE_STORE_ADMIN, ROLE_STORE_MANAGER]

# Roles an admin may assign via the Create User endpoint. wh-admin is deliberately excluded —
# it only ever comes from warehouse self-registration, never from a manual user-creation call.
CREATABLE_ROLES_BY_PORTAL = {
    "warehouse": WAREHOUSE_MANAGER_ROLES,
    "vendor": [ROLE_VENDOR_MANAGER],
    "store": STORE_ROLES,
}
