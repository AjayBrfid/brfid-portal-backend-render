from fastapi import FastAPI

from app.api.v1.router import api_router
from app.compat.super_admin.router import router as super_admin_compat_router
from app.compat.vendor.router import router as vendor_compat_router
from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.middleware.cors import add_cors
from app.middleware.logging_middleware import LoggingMiddleware
from app.middleware.rate_limiter import RateLimiterMiddleware

configure_logging(settings.LOG_LEVEL)

app = FastAPI(title="Britannia RFID Platform API", version="1.0.0")

# Starlette wraps middlewares in reverse-add order, so the last one added runs first/outermost.
# CORS is added last so even a 429 short-circuited by the rate limiter still carries CORS headers.
app.add_middleware(RateLimiterMiddleware)
app.add_middleware(LoggingMiddleware)
add_cors(app)

register_exception_handlers(app)

app.include_router(api_router, prefix="/api/v1")
# vms-sa-react's original (pre-unification) Super Admin contract, mounted flat at /api/v1/... —
# see app/compat/super_admin/router.py's module docstring. Does not touch /api/v1/super-admin/...
app.include_router(super_admin_compat_router, prefix="/api/v1")
# vms-react's original (pre-unification) Vendor contract, mounted at root (no prefix at all) —
# see app/compat/vendor/router.py's module docstring. Does not touch /api/v1/vendor/...
app.include_router(vendor_compat_router)


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"success": True, "data": {"status": "ok"}}
