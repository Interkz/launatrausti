"""
Security headers middleware for the Launatrausti application.

Adds standard security headers to all HTTP responses to protect against
common web vulnerabilities (XSS, clickjacking, MIME sniffing, etc.).
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Default security headers applied to every response
SECURITY_HEADERS = {
    # Prevent MIME type sniffing
    "X-Content-Type-Options": "nosniff",
    # Prevent clickjacking — only allow same-origin framing
    "X-Frame-Options": "DENY",
    # Enable XSS filter in older browsers (modern browsers ignore it)
    "X-XSS-Protection": "1; mode=block",
    # Control referrer information sent with requests
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # Restrict browser features/APIs
    "Permissions-Policy": (
        "camera=(), microphone=(), geolocation=(), "
        "payment=(), usb=(), magnetometer=()"
    ),
    # Prevent caching of sensitive data (conservative default)
    "Cache-Control": "no-store, max-age=0",
    # Content Security Policy — allow self-hosted resources plus common CDNs
    # used by Jinja2 templates (fonts, CSS frameworks, etc.)
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "img-src 'self' data:; "
        "font-src 'self' https://fonts.gstatic.com; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds security headers to all responses.

    Usage:
        app.add_middleware(SecurityHeadersMiddleware)

    Or with custom header overrides:
        app.add_middleware(
            SecurityHeadersMiddleware,
            custom_headers={"X-Frame-Options": "SAMEORIGIN"}
        )
    """

    def __init__(self, app, custom_headers: dict | None = None):
        super().__init__(app)
        self.headers = {**SECURITY_HEADERS}
        if custom_headers:
            self.headers.update(custom_headers)

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for header, value in self.headers.items():
            response.headers[header] = value
        return response
