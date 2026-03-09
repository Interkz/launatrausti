"""Tests for security headers middleware."""

import pytest
from unittest.mock import patch
from starlette.testclient import TestClient

import src.database as db
from src.main import app
from src.security import SECURITY_HEADERS


@pytest.fixture
def client(test_db, sample_company, sample_reports, sample_vr_surveys):
    """Create test client with populated test database."""
    with patch.object(db, "DB_PATH", test_db):
        yield TestClient(app, raise_server_exceptions=False)


def test_security_headers_present_on_html(client):
    """All security headers should be present on HTML page responses."""
    response = client.get("/")
    for header, value in SECURITY_HEADERS.items():
        assert header in response.headers, f"Missing header: {header}"
        assert response.headers[header] == value, (
            f"Header {header}: expected {value!r}, got {response.headers[header]!r}"
        )


def test_security_headers_present_on_json(client):
    """All security headers should be present on JSON API responses."""
    response = client.get("/api/stats")
    for header in SECURITY_HEADERS:
        assert header in response.headers, f"Missing header: {header}"


def test_security_headers_present_on_health(client):
    """Security headers should be present on health endpoint too."""
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-Content-Type-Options" in response.headers
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_x_frame_options_deny(client):
    """X-Frame-Options should be DENY to prevent clickjacking."""
    response = client.get("/")
    assert response.headers["X-Frame-Options"] == "DENY"


def test_csp_blocks_frames(client):
    """Content-Security-Policy should include frame-ancestors 'none'."""
    response = client.get("/")
    csp = response.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in csp


def test_referrer_policy(client):
    """Referrer-Policy should be set to strict-origin-when-cross-origin."""
    response = client.get("/")
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_permissions_policy(client):
    """Permissions-Policy should restrict dangerous browser features."""
    response = client.get("/")
    pp = response.headers["Permissions-Policy"]
    assert "camera=()" in pp
    assert "microphone=()" in pp
    assert "geolocation=()" in pp
