"""
API package — versioned API routers for Launatrausti.

To add a new API version:
1. Create a new module (e.g., v2.py) with an APIRouter
2. Import and mount it in this file
"""

from fastapi import APIRouter

from .v1 import router as v1_router

API_VERSIONS = {
    1: {"status": "current", "prefix": "/api/v1"},
}

# Top-level API router that mounts all versions
api_router = APIRouter()
api_router.include_router(v1_router, prefix="/v1")

# Backward-compatible aliases — mount v1 at /api/ directly
compat_router = APIRouter()
compat_router.include_router(v1_router)


@api_router.get("/versions")
async def list_versions():
    """List available API versions."""
    return {
        "versions": [
            {"version": ver, "status": info["status"], "prefix": info["prefix"]}
            for ver, info in sorted(API_VERSIONS.items())
        ],
        "current": max(
            (v for v, i in API_VERSIONS.items() if i["status"] == "current"),
            default=1,
        ),
    }
