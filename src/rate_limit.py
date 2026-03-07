"""
Sliding window rate limiting middleware for FastAPI.

Tracks requests per client IP using an in-memory dictionary.
Allows 100 requests per 60-second sliding window per IP.
"""

import asyncio
import time
from typing import Dict, List

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

RATE_LIMIT = 100
WINDOW_SECONDS = 60

# In-memory store: IP -> list of request timestamps
_buckets: Dict[str, List[float]] = {}


def cleanup_expired() -> None:
    """Remove expired entries from the buckets to prevent memory leaks."""
    now = time.time()
    cutoff = now - WINDOW_SECONDS
    to_delete = []
    for ip, timestamps in _buckets.items():
        # Prune old timestamps
        fresh = [t for t in timestamps if t > cutoff]
        if fresh:
            _buckets[ip] = fresh
        else:
            to_delete.append(ip)
    for ip in to_delete:
        del _buckets[ip]


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._cleanup_task = None

    async def dispatch(self, request: Request, call_next) -> Response:
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

        now = time.time()
        client_ip = request.client.host if request.client else "unknown"
        cutoff = now - WINDOW_SECONDS

        # Get or create bucket for this IP
        timestamps = _buckets.get(client_ip, [])
        # Prune expired timestamps from this IP's window
        timestamps = [t for t in timestamps if t > cutoff]

        # Calculate window reset time
        window_reset = int(now) + WINDOW_SECONDS
        remaining = max(0, RATE_LIMIT - len(timestamps))

        headers = {
            "X-RateLimit-Limit": str(RATE_LIMIT),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(window_reset),
        }

        if len(timestamps) >= RATE_LIMIT:
            # Oldest timestamp in the current window determines when a slot opens
            earliest = min(timestamps)
            retry_after = int(earliest + WINDOW_SECONDS - now) + 1
            retry_after = max(1, retry_after)
            _buckets[client_ip] = timestamps
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Try again later."},
                headers={**headers, "Retry-After": str(retry_after)},
            )

        # Record this request
        timestamps.append(now)
        _buckets[client_ip] = timestamps

        remaining = max(0, RATE_LIMIT - len(timestamps))
        headers["X-RateLimit-Remaining"] = str(remaining)

        response = await call_next(request)

        for key, value in headers.items():
            response.headers[key] = value

        return response

    async def _periodic_cleanup(self):
        """Run cleanup every 60 seconds."""
        while True:
            await asyncio.sleep(WINDOW_SECONDS)
            cleanup_expired()
