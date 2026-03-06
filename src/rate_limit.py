"""
In-memory sliding window rate limiter middleware for FastAPI.

Limits API endpoints (/api/*) to 60 requests per minute per client IP.
Returns 429 Too Many Requests with Retry-After header when exceeded.
"""

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

RATE_LIMIT = 60
WINDOW_SECONDS = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        ip = self._get_client_ip(request)
        now = time.time()
        cutoff = now - WINDOW_SECONDS

        # Prune expired timestamps
        timestamps = self._requests[ip]
        self._requests[ip] = [t for t in timestamps if t > cutoff]

        if len(self._requests[ip]) >= RATE_LIMIT:
            oldest = min(self._requests[ip])
            retry_after = int(oldest + WINDOW_SECONDS - now) + 1
            retry_after = max(1, min(retry_after, WINDOW_SECONDS))
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
                headers={"Retry-After": str(retry_after)},
            )

        self._requests[ip].append(now)
        return await call_next(request)
