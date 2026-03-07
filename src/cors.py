"""
CORS middleware for Launatrausti.

Reads allowed origins from CORS_ORIGINS env var (comma-separated).
In development (DEBUG != "false"), defaults to localhost:3000 and localhost:8080.
In production (DEBUG=false), requires explicit origins.
Logs CORS rejections at WARNING level.
"""

import logging
import os

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger(__name__)

DEFAULT_DEV_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8080",
]

ALLOWED_METHODS = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
ALLOWED_HEADERS = "Authorization, Content-Type, Accept, Origin, X-Requested-With"
MAX_AGE = "86400"


def get_allowed_origins() -> list[str]:
    """Parse allowed origins from environment, with dev defaults."""
    cors_origins = os.environ.get("CORS_ORIGINS", "").strip()
    is_production = os.environ.get("DEBUG", "true").lower() == "false"

    if cors_origins:
        origins = [o.strip() for o in cors_origins.split(",") if o.strip()]
    elif is_production:
        logger.warning(
            "CORS_ORIGINS not set in production (DEBUG=false). "
            "No cross-origin requests will be allowed."
        )
        origins = []
    else:
        origins = DEFAULT_DEV_ORIGINS.copy()
        logger.info("CORS: using default dev origins: %s", origins)

    return origins


def _origin_allowed(origin: str, allowed_origins: list[str]) -> bool:
    return origin in allowed_origins


def _add_cors_headers(response: Response, origin: str) -> None:
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = ALLOWED_METHODS
    response.headers["Access-Control-Allow-Headers"] = ALLOWED_HEADERS
    response.headers["Access-Control-Max-Age"] = MAX_AGE
    response.headers["Vary"] = "Origin"


class CORSMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_origins: list[str]) -> None:
        super().__init__(app)
        self.allowed_origins = allowed_origins

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        origin = request.headers.get("origin")

        if not origin:
            return await call_next(request)

        if not _origin_allowed(origin, self.allowed_origins):
            logger.warning(
                "CORS rejected: origin=%s method=%s path=%s",
                origin,
                request.method,
                request.url.path,
            )
            if request.method == "OPTIONS":
                return Response(status_code=403)
            response = await call_next(request)
            return response

        # Preflight
        if request.method == "OPTIONS":
            response = Response(status_code=200)
            _add_cors_headers(response, origin)
            return response

        response = await call_next(request)
        _add_cors_headers(response, origin)
        return response


def setup_cors(app: FastAPI) -> None:
    """Configure CORS middleware on the FastAPI app."""
    allowed_origins = get_allowed_origins()
    app.add_middleware(CORSMiddleware, allowed_origins=allowed_origins)
