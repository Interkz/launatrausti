import pytest
from datetime import datetime
from unittest.mock import patch
from starlette.testclient import TestClient

import src.database as db
from src.main import app


@pytest.fixture
def test_db(tmp_path):
    """Create isolated test database using tmp_path."""
    test_db_path = tmp_path / "test.db"
    with patch.object(db, "DB_PATH", test_db_path):
        db.init_db()
        yield test_db_path


@pytest.fixture
def sample_company(test_db):
    """Insert a test company and return its ID."""
    with patch.object(db, "DB_PATH", test_db):
        return db.get_or_create_company("1234567890", "Test Company ehf.", "62.01")


@pytest.fixture
def second_company(test_db):
    """Insert a second test company and return its ID."""
    with patch.object(db, "DB_PATH", test_db):
        return db.get_or_create_company("0987654321", "Other Company hf.", "64.19")


@pytest.fixture
def sample_reports(test_db, sample_company):
    """Insert 3 years of annual reports for the sample company."""
    with patch.object(db, "DB_PATH", test_db):
        for year, laun, staff, tekjur in [
            (2021, 60_000_000, 5.0, 200_000_000),
            (2022, 72_000_000, 6.0, 250_000_000),
            (2023, 84_000_000, 7.0, 300_000_000),
        ]:
            db.save_annual_report(
                company_id=sample_company,
                year=year,
                launakostnadur=laun,
                starfsmenn=staff,
                source_pdf=f"test_{year}.pdf",
                tekjur=tekjur,
            )
        return sample_company


@pytest.fixture
def second_reports(test_db, second_company):
    """Insert an annual report for the second company."""
    with patch.object(db, "DB_PATH", test_db):
        db.save_annual_report(
            company_id=second_company,
            year=2023,
            launakostnadur=120_000_000,
            starfsmenn=10.0,
            source_pdf="test_other_2023.pdf",
            tekjur=500_000_000,
        )
        return second_company


@pytest.fixture
def sample_vr_surveys(test_db):
    """Insert VR survey data for 5 job titles."""
    with patch.object(db, "DB_PATH", test_db):
        titles = [
            ("Hugbunadarverkfraedingur", "Taekni", 950000),
            ("Verkefnastjori", "Stjornun", 850000),
            ("Grafiskur honnudur", "Honnun", 650000),
            ("Kerfisstjori", "Taekni", 780000),
            ("Markadsstjori", "Stjornun", 900000),
        ]
        for title, cat, salary in titles:
            survey = db.VRSalarySurvey(
                id=None,
                survey_date="2025-09",
                starfsheiti=title,
                starfsstett=cat,
                medaltal=salary,
                midgildi=int(salary * 0.95),
                p25=int(salary * 0.8),
                p75=int(salary * 1.2),
                fjoldi_svara=50,
                source_pdf="vr_2025.pdf",
                extracted_at=datetime.now(),
            )
            db.save_vr_survey(survey)
        return 5


@pytest.fixture
def client(test_db, sample_company, sample_reports, sample_vr_surveys):
    """Create test client with populated test database."""
    with patch.object(db, "DB_PATH", test_db):
        yield TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client_multi(test_db, sample_company, sample_reports, second_company, second_reports, sample_vr_surveys):
    """Test client with two companies for list/ranking tests."""
    with patch.object(db, "DB_PATH", test_db):
        yield TestClient(app, raise_server_exceptions=False)
