"""
API tests for Launatrausti.

Tests all HTML pages and JSON API endpoints using Starlette's TestClient
with a populated test database.
"""

import pytest
from unittest.mock import patch

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


def test_health(client):
    """GET /health returns {"status": "ok"}."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_companies_returns_array(client):
    """GET /api/companies returns JSON with a companies array."""
    response = client.get("/api/companies")
    assert response.status_code == 200
    data = response.json()
    assert "companies" in data
    assert isinstance(data["companies"], list)


def test_api_companies_contains_seeded_data(client):
    """GET /api/companies includes the seeded company."""
    response = client.get("/api/companies")
    data = response.json()
    names = [c["name"] for c in data["companies"]]
    assert "Test Company ehf." in names


def test_api_companies_multiple(client_multi):
    """GET /api/companies returns both companies when two are seeded."""
    response = client_multi.get("/api/companies")
    data = response.json()
    names = [c["name"] for c in data["companies"]]
    assert "Test Company ehf." in names
    assert "Other Company hf." in names
    assert len(data["companies"]) >= 2


def test_api_companies_year_filter(client):
    """GET /api/companies?year=2023 returns only 2023 data."""
    response = client.get("/api/companies?year=2023")
    data = response.json()
    assert data["year"] == 2023
    for company in data["companies"]:
        assert company["year"] == 2023


def test_api_companies_empty_for_future_year(client):
    """GET /api/companies?year=2099 returns an empty array."""
    response = client.get("/api/companies?year=2099")
    data = response.json()
    assert data["companies"] == []


def test_api_company_by_id(client, sample_company):
    """GET /api/company/{id} returns company detail with reports."""
    response = client.get(f"/api/company/{sample_company}")
    assert response.status_code == 200
    data = response.json()
    assert "company" in data
    assert "reports" in data
    assert data["company"]["name"] == "Test Company ehf."
    assert data["company"]["kennitala"] == "1234567890"
    assert len(data["reports"]) == 3


def test_api_company_not_found_404(client):
    """GET /api/company/99999 returns 404 JSON for a non-existent company."""
    response = client.get("/api/company/99999")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data


def test_api_company_invalid_id_422(client):
    """GET /api/company/abc returns 422 for an invalid path parameter."""
    response = client.get("/api/company/abc")
    assert response.status_code == 422


def test_api_financials_by_id(client, sample_company):
    """GET /api/company/{id}/financials returns company financials with trends."""
    response = client.get(f"/api/company/{sample_company}/financials")
    assert response.status_code == 200
    data = response.json()
    assert "company" in data
    assert "reports" in data
    assert "trends" in data
    assert len(data["reports"]) == 3


def test_api_financials_not_found_404(client):
    """GET /api/company/99999/financials returns 404."""
    response = client.get("/api/company/99999/financials")
    assert response.status_code == 404


def test_api_financials_invalid_id_422(client):
    """GET /api/company/abc/financials returns 422."""
    response = client.get("/api/company/abc/financials")
    assert response.status_code == 422


def test_api_salary_comparison(client, sample_company):
    """GET /api/company/{id}/salary-comparison returns comparison data."""
    response = client.get(f"/api/company/{sample_company}/salary-comparison")
    assert response.status_code == 200
    data = response.json()
    assert "company_avg_salary" in data
    assert "report_year" in data


def test_api_salary_comparison_missing_company(client):
    """GET /api/company/99999/salary-comparison returns error message for missing company."""
    response = client.get("/api/company/99999/salary-comparison")
    assert response.status_code == 200
    data = response.json()
    assert "error" in data


def test_api_stats(client):
    """GET /api/stats returns platform statistics."""
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_companies" in data
    assert "total_reports" in data
    assert data["total_companies"] >= 1
    assert data["total_reports"] >= 1


def test_api_salaries(client):
    """GET /api/salaries returns survey data with categories and dates."""
    response = client.get("/api/salaries")
    assert response.status_code == 200
    data = response.json()
    assert "surveys" in data
    assert "categories" in data
    assert "dates" in data
    assert isinstance(data["surveys"], list)
    assert len(data["surveys"]) >= 1


def test_api_benchmarks(client):
    """GET /api/benchmarks returns industries array."""
    mock_wage = _mock_industry_wage()
    with (
        patch("src.main.hagstofa.get_all_benchmarks", return_value=[mock_wage]),
        patch("src.main.hagstofa.get_national_average", return_value=mock_wage),
    ):
        response = client.get("/api/benchmarks")
        assert response.status_code == 200
        data = response.json()
        assert "industries" in data
        assert isinstance(data["industries"], list)
        assert len(data["industries"]) == 1
        assert data["industries"][0]["code"] == "J"
        assert "national_average" in data
        assert "source" in data
