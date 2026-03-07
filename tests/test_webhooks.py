"""
Tests for the webhook system: CRUD endpoints, dispatch, and retry logic.
"""

import asyncio
import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from starlette.testclient import TestClient

import src.database as db
from src.main import app
from src.webhooks import dispatch_event, _deliver_webhook, _send_webhook


@pytest.fixture
def client(test_db):
    """Create test client with isolated test database."""
    with patch.object(db, "DB_PATH", test_db):
        yield TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Admin CRUD endpoint tests
# ---------------------------------------------------------------------------


def test_create_webhook(client):
    """POST /api/admin/webhooks creates a webhook and returns it."""
    response = client.post("/api/admin/webhooks", json={
        "url": "https://example.com/hook",
        "events": ["company.created", "report.created"],
    })
    assert response.status_code == 201
    data = response.json()
    assert data["url"] == "https://example.com/hook"
    assert data["events"] == ["company.created", "report.created"]
    assert data["active"] == 1
    assert data["id"] is not None


def test_create_webhook_invalid_url(client):
    """POST /api/admin/webhooks with invalid URL returns 422."""
    response = client.post("/api/admin/webhooks", json={
        "url": "not-a-url",
        "events": ["company.created"],
    })
    assert response.status_code == 422


def test_list_webhooks_empty(client):
    """GET /api/admin/webhooks returns empty list when none registered."""
    response = client.get("/api/admin/webhooks")
    assert response.status_code == 200
    assert response.json() == {"webhooks": []}


def test_list_webhooks(client):
    """GET /api/admin/webhooks returns registered webhooks."""
    client.post("/api/admin/webhooks", json={
        "url": "https://example.com/hook1",
        "events": ["company.created"],
    })
    client.post("/api/admin/webhooks", json={
        "url": "https://example.com/hook2",
        "events": ["report.created"],
    })

    response = client.get("/api/admin/webhooks")
    assert response.status_code == 200
    data = response.json()
    assert len(data["webhooks"]) == 2


def test_delete_webhook(client):
    """DELETE /api/admin/webhooks/{id} removes a webhook."""
    create_resp = client.post("/api/admin/webhooks", json={
        "url": "https://example.com/hook",
        "events": ["company.created"],
    })
    webhook_id = create_resp.json()["id"]

    delete_resp = client.delete(f"/api/admin/webhooks/{webhook_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json() == {"deleted": True}

    list_resp = client.get("/api/admin/webhooks")
    assert len(list_resp.json()["webhooks"]) == 0


def test_delete_webhook_not_found(client):
    """DELETE /api/admin/webhooks/99999 returns 404."""
    response = client.delete("/api/admin/webhooks/99999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Database CRUD tests
# ---------------------------------------------------------------------------


def test_db_create_and_list_webhooks(test_db):
    """create_webhook and list_webhooks work correctly."""
    with patch.object(db, "DB_PATH", test_db):
        wh = db.create_webhook("https://example.com/hook", ["company.created"])
        assert wh["url"] == "https://example.com/hook"
        assert wh["events"] == ["company.created"]

        all_hooks = db.list_webhooks()
        assert len(all_hooks) == 1


def test_db_get_webhooks_for_event(test_db):
    """get_webhooks_for_event filters by event type."""
    with patch.object(db, "DB_PATH", test_db):
        db.create_webhook("https://example.com/a", ["company.created"])
        db.create_webhook("https://example.com/b", ["report.created"])
        db.create_webhook("https://example.com/c", ["*"])

        company_hooks = db.get_webhooks_for_event("company.created")
        assert len(company_hooks) == 2  # a + c (wildcard)

        report_hooks = db.get_webhooks_for_event("report.created")
        assert len(report_hooks) == 2  # b + c (wildcard)

        other_hooks = db.get_webhooks_for_event("report.deleted")
        assert len(other_hooks) == 1  # only c (wildcard)


def test_db_delete_webhook(test_db):
    """delete_webhook removes webhook and returns True."""
    with patch.object(db, "DB_PATH", test_db):
        wh = db.create_webhook("https://example.com/hook", ["company.created"])
        assert db.delete_webhook(wh["id"]) is True
        assert db.delete_webhook(wh["id"]) is False  # already deleted
        assert len(db.list_webhooks()) == 0


# ---------------------------------------------------------------------------
# Async dispatch tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_event_calls_webhooks(test_db):
    """dispatch_event sends POST to all matching webhooks."""
    with patch.object(db, "DB_PATH", test_db):
        db.create_webhook("https://example.com/hook1", ["company.created"])
        db.create_webhook("https://example.com/hook2", ["company.created"])

        with patch("src.webhooks._send_webhook", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            await dispatch_event("company.created", {"id": 1, "name": "Test"})
            # Give tasks a moment to run
            await asyncio.sleep(0.1)

            assert mock_send.call_count == 2
            # Verify payload structure
            call_args = mock_send.call_args_list[0]
            payload = call_args[0][1]
            assert payload["event"] == "company.created"
            assert payload["data"] == {"id": 1, "name": "Test"}
            assert "timestamp" in payload


@pytest.mark.asyncio
async def test_dispatch_event_skips_unmatched(test_db):
    """dispatch_event doesn't send to webhooks for other events."""
    with patch.object(db, "DB_PATH", test_db):
        db.create_webhook("https://example.com/hook", ["report.created"])

        with patch("src.webhooks._send_webhook", new_callable=AsyncMock) as mock_send:
            await dispatch_event("company.created", {"id": 1})
            await asyncio.sleep(0.1)
            mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_deliver_webhook_retries_on_failure():
    """_deliver_webhook retries once after failure."""
    with patch("src.webhooks._send_webhook", new_callable=AsyncMock) as mock_send:
        mock_send.side_effect = [Exception("connection refused"), True]
        with patch("src.webhooks.RETRY_DELAY_SECONDS", 0):  # No delay in tests
            await _deliver_webhook("https://example.com/hook", {"event": "test"})
        assert mock_send.call_count == 2


@pytest.mark.asyncio
async def test_deliver_webhook_logs_final_failure():
    """_deliver_webhook logs error when retry also fails."""
    with patch("src.webhooks._send_webhook", new_callable=AsyncMock) as mock_send:
        mock_send.side_effect = [Exception("fail1"), Exception("fail2")]
        with patch("src.webhooks.RETRY_DELAY_SECONDS", 0):
            # Should not raise — errors are caught and logged
            await _deliver_webhook("https://example.com/hook", {"event": "test"})
        assert mock_send.call_count == 2


@pytest.mark.asyncio
async def test_deliver_webhook_no_retry_on_success():
    """_deliver_webhook doesn't retry when first attempt succeeds."""
    with patch("src.webhooks._send_webhook", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        await _deliver_webhook("https://example.com/hook", {"event": "test"})
        assert mock_send.call_count == 1
