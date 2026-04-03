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
from src.hagstofa import IndustryWage, ISAT_TO_HAGSTOFA, INDUSTRY_NAMES_EN


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


def test_financials_page_redirects(client, sample_company):
    """GET /company/{id}/financials redirects to company page."""
    response = client.get(f"/company/{sample_company}/financials", follow_redirects=False)
    assert response.status_code == 301


def test_launaleynd_removed(client):
    """GET /launaleynd returns 404 (page removed)."""
    response = client.get("/launaleynd")
    assert response.status_code == 404


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
# JSON API: /api/companies
# ---------------------------------------------------------------------------


def test_api_companies_returns_list(client):
    """GET /api/companies returns JSON with a non-empty companies list."""
    response = client.get("/api/companies")
    assert response.status_code == 200
    data = response.json()
    assert "companies" in data
    assert len(data["companies"]) >= 1


def test_api_companies_year_filter(client):
    """GET /api/companies?year=2023 filters to the requested year."""
    response = client.get("/api/companies?year=2023")
    assert response.status_code == 200
    data = response.json()
    assert data["year"] == 2023
    for company in data["companies"]:
        assert company["year"] == 2023


def test_api_companies_ranked_descending(client):
    """Companies are returned in descending avg_salary order."""
    response = client.get("/api/companies")
    data = response.json()
    salaries = [c["avg_salary"] for c in data["companies"]]
    assert salaries == sorted(salaries, reverse=True)


# ---------------------------------------------------------------------------
# JSON API: /api/company/{id}
# ---------------------------------------------------------------------------


def test_api_company_detail_json(client, sample_company):
    """GET /api/company/{id} returns company and reports for an existing company."""
    response = client.get(f"/api/company/{sample_company}")
    assert response.status_code == 200
    data = response.json()
    assert data["company"]["kennitala"] == "1234567890"
    assert data["company"]["name"] == "Test Company ehf."
    assert len(data["reports"]) == 3


def test_api_company_detail_404(client):
    """GET /api/company/99999 returns 404 for non-existent company."""
    response = client.get("/api/company/99999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# JSON API: /api/benchmarks (mocked hagstofa)
# ---------------------------------------------------------------------------


def test_api_benchmarks_json(client):
    """GET /api/benchmarks returns structured benchmark data."""
    wages = [
        _mock_industry_wage("J", "Upplysingar og fjarskipti", 2023),
        _mock_industry_wage("K", "Fjarmala- og vatryggingastarfsemi", 2023),
    ]
    national = _mock_industry_wage("0", "Allar atvinnugreinar", 2023)
    with (
        patch("src.main.hagstofa.get_all_benchmarks", return_value=wages),
        patch("src.main.hagstofa.get_national_average", return_value=national),
    ):
        response = client.get("/api/benchmarks?year=2023")
    assert response.status_code == 200
    data = response.json()
    assert data["year"] == 2023
    assert data["source"] == "Hagstofa Íslands (Statistics Iceland)"
    assert data["national_average"]["monthly"] == 800_000
    assert data["national_average"]["annual"] == 9_600_000
    assert len(data["industries"]) == 2
    assert data["industries"][0]["code"] == "J"


def test_api_benchmarks_no_data(client):
    """GET /api/benchmarks returns null national_average when hagstofa has no data."""
    with (
        patch("src.main.hagstofa.get_all_benchmarks", return_value=[]),
        patch("src.main.hagstofa.get_national_average", return_value=None),
    ):
        response = client.get("/api/benchmarks?year=2020")
    assert response.status_code == 200
    data = response.json()
    assert data["national_average"] is None
    assert data["industries"] == []


# ---------------------------------------------------------------------------
# JSON API: /api/company/{id}/financials — 404 case
# ---------------------------------------------------------------------------


def test_api_company_financials_404(client):
    """GET /api/company/99999/financials returns 404."""
    response = client.get("/api/company/99999/financials")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Calculation verification: avg_salary = launakostnadur / starfsmenn
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("laun,staff,expected_avg", [
    (84_000_000, 7.0, 12_000_000),
    (72_000_000, 6.0, 12_000_000),
    (60_000_000, 5.0, 12_000_000),
    (100_000_000, 1.0, 100_000_000),
    (50_000_000, 3.0, 16_666_666),
])
def test_avg_salary_calculation(test_db, laun, staff, expected_avg):
    """Verify avg_salary = launakostnadur // starfsmenn for known inputs."""
    with patch.object(db, "DB_PATH", test_db):
        cid = db.get_or_create_company("9876543210", "Calc Test ehf.")
        db.save_annual_report(cid, 2023, laun, staff, "calc_test.pdf")
        detail = db.get_company_detail(cid)
        assert detail["reports"][0]["avg_salary"] == expected_avg


@pytest.mark.parametrize("laun,staff", [
    (50_000_000, 0.0),
])
def test_avg_salary_zero_employees(test_db, laun, staff):
    """avg_salary should be 0 when starfsmenn is 0 (division guard)."""
    with patch.object(db, "DB_PATH", test_db):
        cid = db.get_or_create_company("8765432109", "Zero Staff ehf.")
        db.save_annual_report(cid, 2023, laun, staff, "zero.pdf")
        detail = db.get_company_detail(cid)
        assert detail["reports"][0]["avg_salary"] == 0


# ---------------------------------------------------------------------------
# Financials CAGR trend calculation
# ---------------------------------------------------------------------------


def test_financials_cagr_trends(client, sample_company):
    """GET /api/company/{id}/financials returns CAGR trends for multi-year data."""
    response = client.get(f"/api/company/{sample_company}/financials")
    data = response.json()
    assert "trends" in data
    # 3 years of data (2021-2023) → trends should have salary_cagr
    assert "salary_cagr" in data["trends"]
    # 2021: 60M/5=12M, 2023: 84M/7=12M → CAGR = 0.0
    assert data["trends"]["salary_cagr"] == pytest.approx(0.0, abs=0.001)
    # Revenue CAGR: 200M → 300M over 2 years = (300/200)^(1/2) - 1 ≈ 0.2247
    assert "revenue_cagr" in data["trends"]
    assert data["trends"]["revenue_cagr"] == pytest.approx(0.2247, abs=0.001)
