"""Tests for audit log functionality."""

import json
import pytest
from datetime import datetime
from unittest.mock import patch
from starlette.testclient import TestClient

import src.database as db
from src.main import app


# ---------------------------------------------------------------------------
# Database-level tests for log_action() and get_audit_log()
# ---------------------------------------------------------------------------


def test_log_action_creates_entry(test_db):
    """log_action() inserts an audit log row with correct fields."""
    with patch.object(db, "DB_PATH", test_db):
        db.log_action(
            action="create",
            resource_type="company",
            resource_id=1,
            changes={"name": "Test Corp"},
            ip_address="127.0.0.1",
        )
        entries = db.get_audit_log()
        assert len(entries) == 1
        entry = entries[0]
        assert entry["action"] == "create"
        assert entry["resource_type"] == "company"
        assert entry["resource_id"] == 1
        assert json.loads(entry["changes_json"]) == {"name": "Test Corp"}
        assert entry["ip_address"] == "127.0.0.1"
        assert entry["created_at"] is not None


def test_log_action_without_optional_fields(test_db):
    """log_action() works with None changes and ip_address."""
    with patch.object(db, "DB_PATH", test_db):
        db.log_action(
            action="delete",
            resource_type="annual_report",
            resource_id=42,
        )
        entries = db.get_audit_log()
        assert len(entries) == 1
        assert entries[0]["changes_json"] is None
        assert entries[0]["ip_address"] is None


def test_get_audit_log_ordering(test_db):
    """get_audit_log() returns entries newest first."""
    with patch.object(db, "DB_PATH", test_db):
        db.log_action("create", "company", 1)
        db.log_action("update", "company", 1)
        db.log_action("delete", "company", 1)

        entries = db.get_audit_log()
        actions = [e["action"] for e in entries]
        assert actions == ["delete", "update", "create"]


def test_get_audit_log_pagination(test_db):
    """get_audit_log() supports limit and offset."""
    with patch.object(db, "DB_PATH", test_db):
        for i in range(5):
            db.log_action("create", "company", i + 1)

        page1 = db.get_audit_log(limit=2, offset=0)
        assert len(page1) == 2

        page2 = db.get_audit_log(limit=2, offset=2)
        assert len(page2) == 2

        page3 = db.get_audit_log(limit=2, offset=4)
        assert len(page3) == 1


def test_get_audit_log_filter_by_resource_type(test_db):
    """get_audit_log() can filter by resource_type."""
    with patch.object(db, "DB_PATH", test_db):
        db.log_action("create", "company", 1)
        db.log_action("create", "annual_report", 1)
        db.log_action("update", "company", 1)

        entries = db.get_audit_log(resource_type="company")
        assert len(entries) == 2
        assert all(e["resource_type"] == "company" for e in entries)


def test_get_audit_log_filter_by_action(test_db):
    """get_audit_log() can filter by action."""
    with patch.object(db, "DB_PATH", test_db):
        db.log_action("create", "company", 1)
        db.log_action("update", "company", 1)
        db.log_action("create", "annual_report", 2)

        entries = db.get_audit_log(action="create")
        assert len(entries) == 2
        assert all(e["action"] == "create" for e in entries)


# ---------------------------------------------------------------------------
# Integration: mutation functions log audit entries
# ---------------------------------------------------------------------------


def test_get_or_create_company_logs_create(test_db):
    """Creating a new company logs a 'create' audit entry."""
    with patch.object(db, "DB_PATH", test_db):
        cid = db.get_or_create_company("9876543210", "Audit Corp", "62.01")
        entries = db.get_audit_log(resource_type="company")
        assert len(entries) >= 1
        create_entry = [e for e in entries if e["action"] == "create"]
        assert len(create_entry) == 1
        assert create_entry[0]["resource_id"] == cid


def test_get_or_create_company_logs_update(test_db):
    """Updating an existing company logs an 'update' audit entry."""
    with patch.object(db, "DB_PATH", test_db):
        cid = db.get_or_create_company("9876543210", "Audit Corp", "62.01")
        db.get_or_create_company("9876543210", "Audit Corp Updated", "62.02")
        entries = db.get_audit_log(resource_type="company", action="update")
        assert len(entries) == 1
        changes = json.loads(entries[0]["changes_json"])
        assert changes["name"] == "Audit Corp Updated"


def test_save_annual_report_logs_create(test_db, sample_company):
    """Saving a new annual report logs a 'create' audit entry."""
    with patch.object(db, "DB_PATH", test_db):
        rid = db.save_annual_report(
            company_id=sample_company,
            year=2023,
            launakostnadur=100_000_000,
            starfsmenn=10.0,
            source_pdf="test.pdf",
        )
        entries = db.get_audit_log(resource_type="annual_report")
        assert len(entries) >= 1
        create_entry = [e for e in entries if e["action"] in ("create", "update")]
        assert len(create_entry) >= 1
        assert create_entry[0]["resource_id"] == rid


def test_delete_sample_data_logs_delete(test_db):
    """Deleting sample data logs a 'delete' audit entry."""
    with patch.object(db, "DB_PATH", test_db):
        cid = db.get_or_create_company("4444444444", "Sample Corp")
        db.save_annual_report(cid, 2023, 50_000_000, 3.0, "sample_data")
        db.flag_sample_data()
        db.delete_sample_data()

        entries = db.get_audit_log(action="delete")
        assert len(entries) >= 1


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


@pytest.fixture
def audit_client(test_db):
    """Test client with empty database for audit log endpoint tests."""
    with patch.object(db, "DB_PATH", test_db):
        yield TestClient(app, raise_server_exceptions=False)


def test_api_audit_log_returns_200(audit_client, test_db):
    """GET /api/admin/audit-log returns 200."""
    with patch.object(db, "DB_PATH", test_db):
        response = audit_client.get("/api/admin/audit-log")
        assert response.status_code == 200


def test_api_audit_log_returns_entries(audit_client, test_db):
    """GET /api/admin/audit-log returns audit entries."""
    with patch.object(db, "DB_PATH", test_db):
        db.log_action("create", "company", 1, {"name": "Test"})
        response = audit_client.get("/api/admin/audit-log")
        data = response.json()
        assert "entries" in data
        assert "total" in data
        assert len(data["entries"]) == 1


def test_api_audit_log_pagination(audit_client, test_db):
    """GET /api/admin/audit-log supports limit and offset params."""
    with patch.object(db, "DB_PATH", test_db):
        for i in range(5):
            db.log_action("create", "company", i + 1)

        response = audit_client.get("/api/admin/audit-log?limit=2&offset=0")
        data = response.json()
        assert len(data["entries"]) == 2
        assert data["total"] == 5

        response2 = audit_client.get("/api/admin/audit-log?limit=2&offset=4")
        data2 = response2.json()
        assert len(data2["entries"]) == 1


def test_api_audit_log_filters(audit_client, test_db):
    """GET /api/admin/audit-log supports resource_type and action filters."""
    with patch.object(db, "DB_PATH", test_db):
        db.log_action("create", "company", 1)
        db.log_action("create", "annual_report", 1)
        db.log_action("update", "company", 1)

        response = audit_client.get("/api/admin/audit-log?resource_type=company")
        data = response.json()
        assert data["total"] == 2

        response2 = audit_client.get("/api/admin/audit-log?action=create")
        data2 = response2.json()
        assert data2["total"] == 2
