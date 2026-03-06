"""
Tests for input validation on all API endpoints.

Validates that:
- Numeric inputs have sensible min/max bounds
- String inputs are stripped and length-limited
- Validation errors return 422 with field-level details
- Icelandic error messages appear where appropriate
"""

import pytest
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient

import src.database as db
from src.main import app
from src.hagstofa import IndustryWage


@pytest.fixture
def client(test_db, sample_company, sample_reports, sample_vr_surveys):
    """Create test client with populated test database."""
    with patch.object(db, "DB_PATH", test_db):
        yield TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Year validation (used by /, /benchmarks, /api/companies, /api/benchmarks)
# ---------------------------------------------------------------------------


class TestYearValidation:
    """Year parameter must be between 1900 and 2100."""

    def test_year_too_low(self, client):
        response = client.get("/api/companies?year=1899")
        assert response.status_code == 422

    def test_year_too_high(self, client):
        response = client.get("/api/companies?year=2101")
        assert response.status_code == 422

    def test_year_valid(self, client):
        response = client.get("/api/companies?year=2023")
        assert response.status_code == 200

    def test_year_none_is_ok(self, client):
        response = client.get("/api/companies")
        assert response.status_code == 200

    def test_benchmarks_year_too_low(self, client):
        mock_wage = IndustryWage(
            industry_code="J", industry_name="Test", year=2023,
            monthly_wage=800_000, annual_wage=9_600_000,
        )
        with (
            patch("src.main.hagstofa.get_all_benchmarks", return_value=[mock_wage]),
            patch("src.main.hagstofa.get_national_average", return_value=mock_wage),
        ):
            response = client.get("/api/benchmarks?year=1800")
            assert response.status_code == 422

    def test_index_year_too_high(self, client):
        response = client.get("/?year=9999")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Limit validation (/api/companies)
# ---------------------------------------------------------------------------


class TestLimitValidation:
    """Limit parameter must be between 1 and 1000."""

    def test_limit_too_low(self, client):
        response = client.get("/api/companies?limit=0")
        assert response.status_code == 422

    def test_limit_too_high(self, client):
        response = client.get("/api/companies?limit=1001")
        assert response.status_code == 422

    def test_limit_negative(self, client):
        response = client.get("/api/companies?limit=-5")
        assert response.status_code == 422

    def test_limit_valid(self, client):
        response = client.get("/api/companies?limit=50")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Company ID validation (path parameter)
# ---------------------------------------------------------------------------


class TestCompanyIdValidation:
    """Company ID path parameter must be a positive integer."""

    def test_company_id_zero(self, client):
        response = client.get("/api/company/0")
        assert response.status_code == 422

    def test_company_id_negative(self, client):
        response = client.get("/api/company/-1")
        assert response.status_code == 422

    def test_company_id_valid_not_found(self, client):
        response = client.get("/api/company/99999")
        assert response.status_code == 404

    def test_company_id_valid_found(self, client, sample_company):
        response = client.get(f"/api/company/{sample_company}")
        assert response.status_code == 200

    def test_financials_company_id_zero(self, client):
        response = client.get("/api/company/0/financials")
        assert response.status_code == 422

    def test_salary_comparison_company_id_negative(self, client):
        response = client.get("/api/company/-1/salary-comparison")
        assert response.status_code == 422

    def test_html_company_detail_id_zero(self, client):
        response = client.get("/company/0")
        assert response.status_code == 422

    def test_html_financials_id_negative(self, client):
        response = client.get("/company/-1/financials")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# String length validation
# ---------------------------------------------------------------------------


class TestStringLengthValidation:
    """String parameters must not exceed max length."""

    def test_sector_too_long(self, client):
        long_sector = "x" * 501
        response = client.get(f"/?sector={long_sector}")
        assert response.status_code == 422

    def test_category_too_long(self, client):
        long_cat = "x" * 501
        response = client.get(f"/api/salaries?category={long_cat}")
        assert response.status_code == 422

    def test_survey_date_too_long(self, client):
        long_date = "x" * 21
        response = client.get(f"/api/salaries?survey_date={long_date}")
        assert response.status_code == 422

    def test_sector_valid_length(self, client):
        response = client.get("/?sector=tech")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Whitespace stripping
# ---------------------------------------------------------------------------


class TestWhitespaceStripping:
    """String inputs should be stripped of leading/trailing whitespace."""

    def test_sector_stripped(self, client):
        """Whitespace around sector value should be stripped."""
        response = client.get("/?sector=%20tech%20")
        assert response.status_code == 200

    def test_category_stripped(self, client):
        """Whitespace around category value should be stripped."""
        response = client.get("/api/salaries?category=%20Taekni%20")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Validation error response format
# ---------------------------------------------------------------------------


class TestValidationErrorFormat:
    """Validation errors should return structured field-level details."""

    def test_error_has_detail_field(self, client):
        response = client.get("/api/companies?year=-1")
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_error_detail_is_list(self, client):
        response = client.get("/api/companies?year=-1")
        data = response.json()
        assert isinstance(data["detail"], list)
        assert len(data["detail"]) > 0

    def test_error_detail_has_field_info(self, client):
        response = client.get("/api/companies?year=-1")
        data = response.json()
        error = data["detail"][0]
        assert "field" in error
        assert "message" in error

    def test_error_identifies_correct_field(self, client):
        response = client.get("/api/companies?year=-1")
        data = response.json()
        fields = [e["field"] for e in data["detail"]]
        assert "year" in fields

    def test_error_has_icelandic_message(self, client):
        """Validation errors should include Icelandic messages."""
        response = client.get("/api/companies?year=-1")
        data = response.json()
        error = data["detail"][0]
        assert "message_is" in error
