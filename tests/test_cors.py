"""Tests for CORS middleware."""

import os
import pytest
from unittest.mock import patch

import src.database as db
from src.main import app
from src.cors import get_allowed_origins, DEFAULT_DEV_ORIGINS
from starlette.testclient import TestClient


@pytest.fixture
def client(test_db):
    """Test client with populated test database."""
    with patch.object(db, "DB_PATH", test_db):
        yield TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Origin configuration
# ---------------------------------------------------------------------------


def test_dev_defaults_when_no_env():
    """Without CORS_ORIGINS or DEBUG, uses dev defaults."""
    with patch.dict(os.environ, {}, clear=True):
        origins = get_allowed_origins()
    assert origins == DEFAULT_DEV_ORIGINS


def test_explicit_origins_from_env():
    """CORS_ORIGINS env var is parsed correctly."""
    with patch.dict(
        os.environ, {"CORS_ORIGINS": "https://example.com, https://app.example.com"}
    ):
        origins = get_allowed_origins()
    assert origins == ["https://example.com", "https://app.example.com"]


def test_production_no_origins_returns_empty():
    """In production with no CORS_ORIGINS, no origins are allowed."""
    with patch.dict(os.environ, {"DEBUG": "false"}, clear=True):
        origins = get_allowed_origins()
    assert origins == []


def test_production_with_explicit_origins():
    """In production with CORS_ORIGINS set, those origins are used."""
    with patch.dict(
        os.environ, {"DEBUG": "false", "CORS_ORIGINS": "https://prod.example.com"}
    ):
        origins = get_allowed_origins()
    assert origins == ["https://prod.example.com"]


# ---------------------------------------------------------------------------
# Preflight (OPTIONS) requests
# ---------------------------------------------------------------------------


def test_preflight_allowed_origin(client):
    """OPTIONS with allowed origin returns 200 with CORS headers."""
    response = client.options(
        "/api/companies",
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert "GET" in response.headers["Access-Control-Allow-Methods"]
    assert "Authorization" in response.headers["Access-Control-Allow-Headers"]
    assert response.headers["Access-Control-Max-Age"] == "86400"


def test_preflight_rejected_origin(client):
    """OPTIONS with disallowed origin returns 403, no CORS headers."""
    response = client.options(
        "/api/companies",
        headers={"Origin": "https://evil.example.com"},
    )
    assert response.status_code == 403
    assert "Access-Control-Allow-Origin" not in response.headers


# ---------------------------------------------------------------------------
# Regular requests with Origin header
# ---------------------------------------------------------------------------


def test_allowed_origin_gets_cors_headers(client):
    """GET with allowed origin includes CORS headers in response."""
    response = client.get(
        "/health",
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert "Vary" in response.headers


def test_rejected_origin_no_cors_headers(client):
    """GET with disallowed origin has no CORS headers."""
    response = client.get(
        "/health",
        headers={"Origin": "https://evil.example.com"},
    )
    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" not in response.headers


def test_no_origin_header_passes_through(client):
    """Request without Origin header works normally (no CORS headers)."""
    response = client.get("/health")
    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" not in response.headers


# ---------------------------------------------------------------------------
# Rejection logging
# ---------------------------------------------------------------------------


def test_cors_rejection_logs_warning(client, caplog):
    """Rejected origin logs a warning with origin, method, and path."""
    import logging

    with caplog.at_level(logging.WARNING, logger="src.cors"):
        client.get(
            "/health",
            headers={"Origin": "https://evil.example.com"},
        )

    assert any("CORS rejected" in record.message for record in caplog.records)
    assert any("evil.example.com" in record.message for record in caplog.records)
