"""
Tests for rate limiting middleware.

Verifies that API endpoints are rate-limited to 60 requests per minute per IP,
returning 429 Too Many Requests with a Retry-After header when exceeded.
"""

import time
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

import src.database as db
from src.main import app


@pytest.fixture
def client(test_db, sample_company, sample_reports, sample_vr_surveys):
    """Create test client with populated test database."""
    with patch.object(db, "DB_PATH", test_db):
        yield TestClient(app, raise_server_exceptions=False)


class TestRateLimitMiddleware:
    """Rate limiting: 60 requests per minute per IP on API endpoints."""

    def test_api_request_under_limit_succeeds(self, client):
        """A single API request should return 200."""
        response = client.get("/api/stats")
        assert response.status_code == 200

    def test_api_returns_429_when_limit_exceeded(self, client):
        """After 60 requests, the 61st should return 429."""
        for _ in range(60):
            client.get("/api/stats")

        response = client.get("/api/stats")
        assert response.status_code == 429

    def test_429_response_has_retry_after_header(self, client):
        """429 response must include a Retry-After header."""
        for _ in range(60):
            client.get("/api/stats")

        response = client.get("/api/stats")
        assert response.status_code == 429
        assert "retry-after" in response.headers
        retry_after = int(response.headers["retry-after"])
        assert 0 < retry_after <= 60

    def test_429_response_body(self, client):
        """429 response body should explain the rate limit."""
        for _ in range(60):
            client.get("/api/stats")

        response = client.get("/api/stats")
        data = response.json()
        assert "detail" in data

    def test_html_pages_not_rate_limited(self, client):
        """HTML page endpoints should not be rate-limited."""
        for _ in range(65):
            response = client.get("/health")
        assert response.status_code == 200

    def test_different_ips_have_separate_limits(self, test_db, sample_company, sample_reports, sample_vr_surveys):
        """Each IP gets its own rate limit counter."""
        with patch.object(db, "DB_PATH", test_db):
            client = TestClient(app, raise_server_exceptions=False)

            # Exhaust limit for 1.1.1.1
            for _ in range(60):
                client.get("/api/stats", headers={"X-Forwarded-For": "1.1.1.1"})

            # 1.1.1.1 should be blocked
            r1 = client.get("/api/stats", headers={"X-Forwarded-For": "1.1.1.1"})
            assert r1.status_code == 429

            # 2.2.2.2 should still work
            r2 = client.get("/api/stats", headers={"X-Forwarded-For": "2.2.2.2"})
            assert r2.status_code == 200

    def test_sliding_window_expires_old_requests(self, client):
        """Requests older than 60 seconds should expire from the window."""
        now = time.time()

        # Make 60 requests at time T
        with patch("src.rate_limit.time") as mock_time:
            mock_time.time.return_value = now
            for _ in range(60):
                client.get("/api/stats")

            # At T+61, the old requests should have expired
            mock_time.time.return_value = now + 61
            response = client.get("/api/stats")
            assert response.status_code == 200
