"""
API tests for Launatrausti.

Tests all HTML pages and JSON API endpoints using Starlette's TestClient
with a populated test database.
"""

import pytest
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient

import src.database as db
from src.main import app
from src.hagstofa import IndustryWage


def _mock_industry_wage(code="J", name="Upplysingar og fjarskipti", year=2023):
    """Create a mock IndustryWage for hagstofa stubs."""
    return IndustryWage(
        industry_code=code,
        industry_name=name,
        year=year,
        monthly_wage=800_000,
        annual_wage=9_600_000,
    )


@pytest.fixture
def client(test_db, sample_company, sample_reports, sample_vr_surveys):
    """Create test client with populated test database."""
    with patch.object(db, "DB_PATH", test_db):
        yield TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# HTML page tests
# ---------------------------------------------------------------------------


def test_index_returns_200(client):
    """GET / returns 200."""
    response = client.get("/")
    assert response.status_code == 200


def test_index_has_company_data(client):
    """GET / response contains 'Test Company'."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Test Company" in response.text


def test_index_sector_filter(client):
    """GET /?sector=private returns 200 (no crash even if no matching data)."""
    response = client.get("/?sector=private")
    assert response.status_code == 200


def test_company_detail_returns_200(client, sample_company):
    """GET /company/{id} returns 200 for an existing company."""
    mock_wage = _mock_industry_wage()
    with (
        patch("src.main.hagstofa.get_industry_benchmark", return_value=mock_wage),
        patch("src.main.hagstofa.isat_to_industry_name", return_value="Information & communication"),
        patch("src.main.hagstofa.get_national_average", return_value=mock_wage),
    ):
        response = client.get(f"/company/{sample_company}")
        assert response.status_code == 200


def test_company_detail_404(client):
    """GET /company/99999 returns 404 for a non-existent company."""
    response = client.get("/company/99999")
    assert response.status_code == 404


def test_salaries_page_returns_200(client):
    """GET /salaries returns 200."""
    response = client.get("/salaries")
    assert response.status_code == 200


def test_salaries_with_category(client):
    """GET /salaries?category=Taekni returns 200."""
    response = client.get("/salaries?category=Taekni")
    assert response.status_code == 200


def test_financials_page_returns_200(client, sample_company):
    """GET /company/{id}/financials returns 200 for an existing company."""
    response = client.get(f"/company/{sample_company}/financials")
    assert response.status_code == 200


def test_launaleynd_returns_200(client):
    """GET /launaleynd returns 200."""
    response = client.get("/launaleynd")
    assert response.status_code == 200


def test_benchmarks_returns_200(client):
    """GET /benchmarks returns 200."""
    mock_wage = _mock_industry_wage()
    with (
        patch("src.main.hagstofa.get_all_benchmarks", return_value=[mock_wage]),
        patch("src.main.hagstofa.get_national_average", return_value=mock_wage),
    ):
        response = client.get("/benchmarks")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# JSON API tests
# ---------------------------------------------------------------------------


def test_api_stats_json(client):
    """GET /api/stats returns JSON with total_companies and total_reports keys."""
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_companies" in data
    assert "total_reports" in data
    assert data["total_companies"] >= 1
    assert data["total_reports"] >= 1


def test_api_salaries_json(client):
    """GET /api/salaries returns JSON with surveys key."""
    response = client.get("/api/salaries")
    assert response.status_code == 200
    data = response.json()
    assert "surveys" in data
    assert len(data["surveys"]) >= 1


def test_api_company_financials_json(client, sample_company):
    """GET /api/company/{id}/financials returns JSON with company and reports."""
    response = client.get(f"/api/company/{sample_company}/financials")
    assert response.status_code == 200
    data = response.json()
    assert "company" in data
    assert "reports" in data
    assert len(data["reports"]) >= 1


def test_api_salary_comparison_json(client, sample_company):
    """GET /api/company/{id}/salary-comparison returns JSON with comparison data."""
    response = client.get(f"/api/company/{sample_company}/salary-comparison")
    assert response.status_code == 200
    data = response.json()
    assert "company_avg_salary" in data
    assert "report_year" in data


def test_health(client):
    """GET /health returns {"status": "ok"}."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Admin API tests (soft delete, trash, restore)
# ---------------------------------------------------------------------------


def test_admin_trash_empty(client):
    """GET /api/admin/trash returns empty lists when nothing is deleted."""
    response = client.get("/api/admin/trash")
    assert response.status_code == 200
    data = response.json()
    assert data["companies"] == []
    assert data["reports"] == []
    assert data["surveys"] == []


def test_admin_soft_delete_and_restore_company(client, sample_company):
    """DELETE then POST restore round-trips a company through trash."""
    # Soft-delete
    response = client.delete(f"/api/admin/company/{sample_company}")
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"

    # Appears in trash
    trash = client.get("/api/admin/trash").json()
    assert any(c["id"] == sample_company for c in trash["companies"])

    # Invisible to normal detail endpoint
    response = client.get(f"/api/company/{sample_company}")
    assert response.status_code == 404

    # Restore
    response = client.post(f"/api/admin/restore/company/{sample_company}")
    assert response.status_code == 200
    assert response.json()["status"] == "restored"

    # Visible again
    response = client.get(f"/api/company/{sample_company}")
    assert response.status_code == 200


def test_admin_delete_invalid_type(client):
    """DELETE with invalid resource type returns 400."""
    response = client.delete("/api/admin/invalid/1")
    assert response.status_code == 400


def test_admin_delete_nonexistent(client):
    """DELETE on non-existent ID returns 404."""
    response = client.delete("/api/admin/company/99999")
    assert response.status_code == 404
