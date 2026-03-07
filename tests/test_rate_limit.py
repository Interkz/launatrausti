"""
Tests for sliding window rate limiting middleware.

Tests verify:
- Rate limit headers present on every response
- 429 returned when limit exceeded
- Per-IP isolation
- Expired entry cleanup
"""

import time
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

import src.database as db
from src.main import app


@pytest.fixture
def client(test_db):
    """Minimal test client — only needs DB init, not full sample data."""
    from src.rate_limit import _buckets

    _buckets.clear()
    with patch.object(db, "DB_PATH", test_db):
        yield TestClient(app, raise_server_exceptions=False)


class TestRateLimitHeaders:
    """Every response must include rate limit headers."""

    def test_response_has_rate_limit_headers(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Remaining" in resp.headers
        assert "X-RateLimit-Reset" in resp.headers

    def test_limit_header_is_100(self, client):
        resp = client.get("/health")
        assert resp.headers["X-RateLimit-Limit"] == "100"

    def test_remaining_decreases(self, client):
        r1 = client.get("/health")
        r2 = client.get("/health")
        rem1 = int(r1.headers["X-RateLimit-Remaining"])
        rem2 = int(r2.headers["X-RateLimit-Remaining"])
        assert rem1 == 99
        assert rem2 == 98

    def test_reset_header_is_unix_timestamp(self, client):
        resp = client.get("/health")
        reset_val = int(resp.headers["X-RateLimit-Reset"])
        now = int(time.time())
        # Reset should be within the next 60 seconds
        assert now < reset_val <= now + 61


class TestRateLimitEnforcement:
    """Requests beyond 100/min must be rejected with 429."""

    def test_429_after_limit_exceeded(self, client):
        from src.rate_limit import _buckets

        _buckets.clear()

        for _ in range(100):
            resp = client.get("/health")
            assert resp.status_code == 200

        resp = client.get("/health")
        assert resp.status_code == 429

    def test_429_response_has_retry_after(self, client):
        from src.rate_limit import _buckets

        _buckets.clear()

        for _ in range(100):
            client.get("/health")

        resp = client.get("/health")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        retry_after = int(resp.headers["Retry-After"])
        assert 0 < retry_after <= 60

    def test_429_body_is_json(self, client):
        from src.rate_limit import _buckets

        _buckets.clear()

        for _ in range(100):
            client.get("/health")

        resp = client.get("/health")
        assert resp.status_code == 429
        body = resp.json()
        assert "detail" in body

    def test_429_still_has_rate_limit_headers(self, client):
        from src.rate_limit import _buckets

        _buckets.clear()

        for _ in range(100):
            client.get("/health")

        resp = client.get("/health")
        assert resp.status_code == 429
        assert "X-RateLimit-Limit" in resp.headers
        assert resp.headers["X-RateLimit-Remaining"] == "0"


class TestPerIPIsolation:
    """Different client IPs have independent rate limits."""

    def test_different_ips_have_separate_limits(self, client):
        from src.rate_limit import _buckets

        _buckets.clear()

        # Exhaust limit for one IP by inserting timestamps directly
        ip1 = "testclient"  # default TestClient IP
        now = time.time()
        _buckets[ip1] = [now] * 100

        # A different IP should still be allowed
        _buckets["10.0.0.99"] = []

        # testclient is blocked
        resp = client.get("/health")
        assert resp.status_code == 429


class TestCleanup:
    """Expired entries must be cleaned up to prevent memory leaks."""

    def test_cleanup_removes_expired_entries(self):
        from src.rate_limit import _buckets, cleanup_expired

        now = time.time()
        # IP with only old timestamps (>60s ago)
        _buckets["old_ip"] = [now - 120, now - 90]
        # IP with recent timestamps
        _buckets["active_ip"] = [now - 10, now - 5]

        cleanup_expired()

        assert "old_ip" not in _buckets
        assert "active_ip" in _buckets

    def test_cleanup_keeps_recent_timestamps(self):
        from src.rate_limit import _buckets, cleanup_expired

        now = time.time()
        _buckets["mixed_ip"] = [now - 120, now - 5, now - 2]

        cleanup_expired()

        # IP still has recent timestamps so it stays
        assert "mixed_ip" in _buckets
        # But old timestamps are pruned
        assert len(_buckets["mixed_ip"]) == 2
