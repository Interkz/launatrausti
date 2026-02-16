import pytest
from datetime import datetime
from unittest.mock import patch
import src.database as db


def test_create_company(test_db):
    with patch.object(db, "DB_PATH", test_db):
        cid = db.get_or_create_company("9999999999", "New Corp", "64.20")
        assert cid is not None
        assert cid > 0
        # Creating again returns same ID
        cid2 = db.get_or_create_company("9999999999", "New Corp Updated")
        assert cid2 == cid


def test_save_annual_report(test_db, sample_company):
    with patch.object(db, "DB_PATH", test_db):
        rid = db.save_annual_report(
            company_id=sample_company,
            year=2023,
            launakostnadur=100_000_000,
            starfsmenn=10.0,
            source_pdf="test.pdf",
            tekjur=500_000_000,
            hagnadur=50_000_000,
            source_type="pdf",
            confidence=0.9,
        )
        assert rid is not None
        detail = db.get_company_detail(sample_company)
        assert len(detail["reports"]) == 1
        assert detail["reports"][0]["avg_salary"] == 10_000_000


def test_get_ranked_companies_excludes_sample(test_db):
    with patch.object(db, "DB_PATH", test_db):
        # Create two companies
        real_id = db.get_or_create_company("1111111111", "Real Company")
        sample_id = db.get_or_create_company("2222222222", "Sample Company")

        db.save_annual_report(real_id, 2023, 50_000_000, 5.0, "real.pdf")
        db.save_annual_report(sample_id, 2023, 80_000_000, 4.0, "sample_data")

        # Flag sample data
        db.flag_sample_data()

        # With exclude_sample=True (default), only real company appears
        ranked = db.get_ranked_companies(year=2023, exclude_sample=True)
        names = [r["name"] for r in ranked]
        assert "Real Company" in names
        assert "Sample Company" not in names

        # With exclude_sample=False, both appear
        ranked_all = db.get_ranked_companies(year=2023, exclude_sample=False)
        names_all = [r["name"] for r in ranked_all]
        assert "Sample Company" in names_all


def test_save_vr_survey(test_db):
    with patch.object(db, "DB_PATH", test_db):
        survey = db.VRSalarySurvey(
            id=None,
            survey_date="2025-09",
            starfsheiti="Forritari",
            starfsstett="Taekni",
            medaltal=900000,
            midgildi=880000,
            p25=750000,
            p75=1050000,
            fjoldi_svara=100,
            source_pdf="vr_test.pdf",
            extracted_at=datetime.now(),
        )
        sid = db.save_vr_survey(survey)
        assert sid is not None

        surveys = db.get_vr_surveys()
        assert len(surveys) == 1
        assert surveys[0]["starfsheiti"] == "Forritari"


def test_get_vr_surveys_filter_by_category(test_db, sample_vr_surveys):
    with patch.object(db, "DB_PATH", test_db):
        taekni = db.get_vr_surveys(category="Taekni")
        assert len(taekni) == 2  # Hugbunadarverkfraedingur + Kerfisstjori

        stjornun = db.get_vr_surveys(category="Stjornun")
        assert len(stjornun) == 2  # Verkefnastjori + Markadsstjori


def test_get_company_financials(test_db, sample_reports):
    with patch.object(db, "DB_PATH", test_db):
        fin = db.get_company_financials(sample_reports)
        assert fin is not None
        assert fin["company"]["name"] == "Test Company ehf."
        assert len(fin["reports"]) == 3
        assert "trends" in fin


def test_flag_sample_data(test_db):
    with patch.object(db, "DB_PATH", test_db):
        cid = db.get_or_create_company("3333333333", "Fake Corp")
        db.save_annual_report(cid, 2023, 50_000_000, 3.0, "sample_data")
        db.save_annual_report(cid, 2022, 40_000_000, 3.0, "sample_data")

        count = db.flag_sample_data()
        assert count == 2


def test_delete_sample_data(test_db):
    with patch.object(db, "DB_PATH", test_db):
        # Create a company with only sample data
        sample_cid = db.get_or_create_company("4444444444", "All Fake")
        db.save_annual_report(sample_cid, 2023, 50_000_000, 3.0, "sample_data")

        # Create a company with real data
        real_cid = db.get_or_create_company("5555555555", "Real Deal")
        db.save_annual_report(real_cid, 2023, 60_000_000, 4.0, "real_report.pdf")

        db.flag_sample_data()
        reports_del, companies_del = db.delete_sample_data()
        assert reports_del == 1
        assert companies_del == 1  # All Fake should be orphaned and deleted

        # Verify Real Deal still exists
        detail = db.get_company_detail(real_cid)
        assert detail is not None
        assert len(detail["reports"]) == 1


def test_get_platform_stats(test_db, sample_reports, sample_vr_surveys):
    with patch.object(db, "DB_PATH", test_db):
        stats = db.get_platform_stats()
        assert stats["total_companies"] >= 1
        assert stats["total_reports"] >= 3
        assert stats["total_vr_surveys"] == 5
