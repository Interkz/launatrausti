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


def test_health_returns_json_with_required_fields(client):
    """GET /health returns JSON with status, uptime, database, timestamp, version."""
    response = client.get("/health")
    data = response.json()
    assert "status" in data
    assert "uptime_seconds" in data
    assert "database" in data
    assert "timestamp" in data
    assert "version" in data


def test_health_status_healthy_when_db_ok(client):
    """GET /health returns 200 with status 'healthy' when DB is reachable."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"


def test_health_uptime_is_positive(client):
    """Uptime should be a non-negative number of seconds."""
    response = client.get("/health")
    data = response.json()
    assert isinstance(data["uptime_seconds"], (int, float))
    assert data["uptime_seconds"] >= 0


def test_health_timestamp_is_iso_format(client):
    """Timestamp should be a valid ISO 8601 string."""
    from datetime import datetime
    response = client.get("/health")
    data = response.json()
    # Should not raise
    datetime.fromisoformat(data["timestamp"])


def test_health_version_matches_version_file(client):
    """Version should match the VERSION file contents."""
    from pathlib import Path
    version_file = Path(__file__).parent.parent / "VERSION"
    expected = version_file.read_text().strip()
    response = client.get("/health")
    data = response.json()
    assert data["version"] == expected


def test_health_unhealthy_returns_503(test_db):
    """GET /health returns 503 when database is unreachable."""
    with patch.object(db, "DB_PATH", test_db):
        c = TestClient(app, raise_server_exceptions=False)
        # Simulate DB failure by pointing to an invalid path
        with patch.object(db, "DB_PATH", "/nonexistent/path/db.sqlite"):
            response = c.get("/health")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "unhealthy"
            assert data["database"] == "disconnected"
