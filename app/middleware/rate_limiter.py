import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """In-memory sliding-window limiter, keyed by client IP. Fine for a single-process dev/
    small-deployment setup; a multi-instance production deployment should replace `_hits`
    with a shared store (Redis INCR + TTL) since in-memory state isn't shared across workers.
    """

    def __init__(self, app):
        super().__init__(app)
        self._hits: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window = self._hits[client_ip]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= settings.RATE_LIMIT_PER_MINUTE:
            return JSONResponse(
                status_code=429,
                content={"success": False, "error": {"code": "RATE_LIMITED", "message": "Too many requests"}},
            )
        window.append(now)
        return await call_next(request)
