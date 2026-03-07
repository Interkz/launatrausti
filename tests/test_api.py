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
# Bulk operation API tests
# ---------------------------------------------------------------------------


def test_bulk_create_companies(client):
    """POST /api/companies/bulk creates multiple companies."""
    response = client.post("/api/companies/bulk", json={
        "items": [
            {"kennitala": "8880000001", "name": "Bulk API Co 1"},
            {"kennitala": "8880000002", "name": "Bulk API Co 2", "isat_code": "64.19"},
        ]
    })
    assert response.status_code == 200
    data = response.json()
    assert data["created"] == 2
    assert data["errors"] == []


def test_bulk_create_companies_validation_error(client):
    """POST /api/companies/bulk rejects items missing required fields."""
    response = client.post("/api/companies/bulk", json={
        "items": [{"kennitala": "8880000003"}]  # missing name
    })
    assert response.status_code == 422  # Pydantic validation


def test_bulk_create_companies_exceeds_limit(client):
    """POST /api/companies/bulk rejects > 100 items."""
    items = [{"kennitala": f"00{i:08d}", "name": f"Co {i}"} for i in range(101)]
    response = client.post("/api/companies/bulk", json={"items": items})
    assert response.status_code == 422


def test_bulk_delete_companies_api(client, sample_company):
    """DELETE /api/companies/bulk deletes companies by ID."""
    response = client.request("DELETE", "/api/companies/bulk", json={
        "ids": [sample_company]
    })
    assert response.status_code == 200
    data = response.json()
    assert data["deleted"] == 1


def test_bulk_delete_companies_not_found(client):
    """DELETE /api/companies/bulk reports errors for missing IDs."""
    response = client.request("DELETE", "/api/companies/bulk", json={
        "ids": [99999]
    })
    assert response.status_code == 200
    data = response.json()
    assert data["deleted"] == 0
    assert len(data["errors"]) == 1


def test_bulk_create_reports_api(client, sample_company):
    """POST /api/reports/bulk creates multiple reports."""
    response = client.post("/api/reports/bulk", json={
        "items": [
            {
                "company_id": sample_company, "year": 2020,
                "launakostnadur": 25_000_000, "starfsmenn": 2.5,
                "source_pdf": "bulk_test.pdf",
            },
        ]
    })
    assert response.status_code == 200
    data = response.json()
    assert data["created"] == 1
    assert data["errors"] == []


def test_bulk_delete_reports_api(client):
    """DELETE /api/reports/bulk reports errors for missing IDs."""
    response = client.request("DELETE", "/api/reports/bulk", json={
        "ids": [99999]
    })
    assert response.status_code == 200
    data = response.json()
    assert data["deleted"] == 0
    assert len(data["errors"]) == 1
