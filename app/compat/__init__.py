"""Backward-compatibility layer.

vms-react (Vendor portal) and vms-sa-react (Super Admin portal) were each built against their
own standalone backend's API contract (see API_SPECIFICATION.md in vms-react and
BACKEND_API_SPEC.md in vms-sa-react) before those backends were consolidated into this unified
one. Rather than update either frontend, these routers translate each frontend's original
request/response shapes to/from the unified backend's real services — no business logic lives
here, only path/field/shape adaptation.

- `vendor_legacy.py` mounts at root (no prefix) — matches vms-react's original
  `VITE_API_BASE_URL=http://localhost:8000` with un-prefixed paths (`/auth/login`, `/rfqs`, ...).
- `super_admin_legacy.py` mounts at `/api/v1` flat (no `/super-admin` segment) — matches
  vms-sa-react's original `VITE_API_BASE_URL=http://localhost:8001/api/v1` with paths like
  `/api/v1/vendors`, `/api/v1/warehouses` (no portal segment).
"""
