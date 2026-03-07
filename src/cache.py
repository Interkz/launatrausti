"""In-memory response cache with TTL support for GET endpoints."""

import logging
import time
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

DEFAULT_TTL = 60  # seconds


class CacheEntry:
    __slots__ = ("body", "status_code", "headers", "media_type", "expires_at")

    def __init__(self, body: bytes, status_code: int, headers: dict, media_type: str, ttl: int):
        self.body = body
        self.status_code = status_code
        self.headers = headers
        self.media_type = media_type
        self.expires_at = time.monotonic() + ttl

    def is_expired(self) -> bool:
        return time.monotonic() > self.expires_at

    def remaining_ttl(self) -> int:
        return max(0, int(self.expires_at - time.monotonic()))


class ResponseCache:
    def __init__(self, default_ttl: int = DEFAULT_TTL):
        self._store: dict[str, CacheEntry] = {}
        self.default_ttl = default_ttl

    def get(self, key: str) -> Optional[CacheEntry]:
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.is_expired():
            del self._store[key]
            return None
        return entry

    def set(self, key: str, entry: CacheEntry) -> None:
        self._store[key] = entry

    def clear(self) -> int:
        count = len(self._store)
        self._store.clear()
        return count

    def size(self) -> int:
        return len(self._store)


# Global cache instance
cache = ResponseCache()


def make_cache_key(request: Request) -> str:
    """Build cache key from request path and sorted query parameters."""
    path = request.url.path
    params = sorted(request.query_params.items())
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params)
        return f"{path}?{qs}"
    return path


class CacheMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, cache_instance: ResponseCache):
        super().__init__(app)
        self.cache = cache_instance

    async def dispatch(self, request: Request, call_next):
        if request.method != "GET":
            return await call_next(request)

        key = make_cache_key(request)
        entry = self.cache.get(key)

        if entry is not None:
            logger.debug("Cache HIT: %s", key)
            response = Response(
                content=entry.body,
                status_code=entry.status_code,
                media_type=entry.media_type,
            )
            for k, v in entry.headers.items():
                response.headers[k] = v
            response.headers["X-Cache"] = "HIT"
            response.headers["Cache-Control"] = f"public, max-age={entry.remaining_ttl()}"
            return response

        logger.debug("Cache MISS: %s", key)
        response = await call_next(request)

        if response.status_code == 200:
            body = b""
            async for chunk in response.body_iterator:
                body += chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")

            preserved_headers = {}
            for k, v in response.headers.items():
                if k.lower() in ("content-type",):
                    preserved_headers[k] = v

            self.cache.set(
                key,
                CacheEntry(
                    body=body,
                    status_code=response.status_code,
                    headers=preserved_headers,
                    media_type=response.media_type,
                    ttl=self.cache.default_ttl,
                ),
            )

            cached_response = Response(
                content=body,
                status_code=response.status_code,
                media_type=response.media_type,
            )
            for k, v in preserved_headers.items():
                cached_response.headers[k] = v
            cached_response.headers["X-Cache"] = "MISS"
            cached_response.headers["Cache-Control"] = f"public, max-age={self.cache.default_ttl}"
            return cached_response

        return response
