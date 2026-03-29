import pytest
from datetime import datetime
from unittest.mock import patch
import src.database as db


def test_job_listings_table_exists(test_db):
    with patch.object(db, "DB_PATH", test_db):
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='job_listings'
        """)
        assert cursor.fetchone() is not None
        conn.close()


def test_save_job_listing_insert(test_db):
    with patch.object(db, "DB_PATH", test_db):
        listing = db.JobListing(
            id=None,
            source="alfred",
            source_id="job-123",
            title="Hugbunadarverkfraedingur",
            employer_name="Marel hf.",
            location="Reykjavik",
            employment_type="full_time",
            posted_date="2026-03-01",
            deadline="2026-04-15",
            estimated_salary=950000,
            salary_source="vr_match",
            salary_confidence=0.8,
        )
        job_id = db.save_job_listing(listing)
        assert job_id is not None
        assert job_id > 0

        # Verify it was saved
        jobs = db.get_active_jobs()
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Hugbunadarverkfraedingur"
        assert jobs[0]["employer_name"] == "Marel hf."
        assert jobs[0]["estimated_salary"] == 950000


def test_save_job_listing_upsert(test_db):
    with patch.object(db, "DB_PATH", test_db):
        listing = db.JobListing(
            id=None,
            source="alfred",
            source_id="job-456",
            title="Verkefnastjori",
            employer_name="CCP Games",
            location="Reykjavik",
        )
        db.save_job_listing(listing)

        # Update same source+source_id with new title
        listing_updated = db.JobListing(
            id=None,
            source="alfred",
            source_id="job-456",
            title="Senior Verkefnastjori",
            employer_name="CCP Games hf.",
            location="Hafnarfjordur",
        )
        db.save_job_listing(listing_updated)

        # Should still be one job, not two
        jobs = db.get_active_jobs()
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Senior Verkefnastjori"
        assert jobs[0]["employer_name"] == "CCP Games hf."
        assert jobs[0]["location"] == "Hafnarfjordur"


def test_save_job_listing_upsert_preserves_company_id(test_db, sample_company):
    with patch.object(db, "DB_PATH", test_db):
        # First insert with a company_id
        listing = db.JobListing(
            id=None,
            source="alfred",
            source_id="job-789",
            title="Forritari",
            employer_name="Test Company ehf.",
            company_id=sample_company,
        )
        db.save_job_listing(listing)

        # Update without company_id — existing one should be preserved
        listing_update = db.JobListing(
            id=None,
            source="alfred",
            source_id="job-789",
            title="Senior Forritari",
            employer_name="Test Company ehf.",
            company_id=None,
        )
        db.save_job_listing(listing_update)

        jobs = db.get_active_jobs()
        assert len(jobs) == 1
        assert jobs[0]["company_id"] == sample_company
        assert jobs[0]["title"] == "Senior Forritari"


def test_get_active_jobs_salary_min_filter(test_db):
    with patch.object(db, "DB_PATH", test_db):
        for title, salary in [("Low", 500000), ("Mid", 800000), ("High", 1200000)]:
            db.save_job_listing(db.JobListing(
                id=None, source="alfred", source_id=f"sal-{title}",
                title=title, employer_name="Corp",
                estimated_salary=salary,
            ))

        jobs = db.get_active_jobs(salary_min=700000)
        assert len(jobs) == 2
        titles = {j["title"] for j in jobs}
        assert titles == {"Mid", "High"}


def test_get_active_jobs_location_filter(test_db):
    with patch.object(db, "DB_PATH", test_db):
        for title, loc in [("RVK", "Reykjavik"), ("AK", "Akureyri"), ("ISA", "Isafjordur")]:
            db.save_job_listing(db.JobListing(
                id=None, source="alfred", source_id=f"loc-{title}",
                title=title, employer_name="Corp", location=loc,
            ))

        jobs = db.get_active_jobs(location="Reykjavik")
        assert len(jobs) == 1
        assert jobs[0]["title"] == "RVK"


def test_get_active_jobs_pagination(test_db):
    with patch.object(db, "DB_PATH", test_db):
        for i in range(10):
            db.save_job_listing(db.JobListing(
                id=None, source="alfred", source_id=f"page-{i}",
                title=f"Job {i}", employer_name="Corp",
                estimated_salary=1000000 - i * 10000,
            ))

        page1 = db.get_active_jobs(limit=3, offset=0)
        page2 = db.get_active_jobs(limit=3, offset=3)
        assert len(page1) == 3
        assert len(page2) == 3
        # Pages should not overlap
        ids1 = {j["id"] for j in page1}
        ids2 = {j["id"] for j in page2}
        assert ids1.isdisjoint(ids2)


def test_get_company_jobs(test_db, sample_company):
    with patch.object(db, "DB_PATH", test_db):
        # Insert jobs for the sample company
        for i in range(3):
            db.save_job_listing(db.JobListing(
                id=None, source="alfred", source_id=f"cjob-{i}",
                title=f"Company Job {i}", employer_name="Test Company ehf.",
                company_id=sample_company,
            ))
        # Insert a job for a different company
        db.save_job_listing(db.JobListing(
            id=None, source="alfred", source_id="other-1",
            title="Other Job", employer_name="Other Corp",
            company_id=999,
        ))

        jobs = db.get_company_jobs(sample_company)
        assert len(jobs) == 3
        assert all(j["company_id"] == sample_company for j in jobs)


def test_get_unextracted_jobs(test_db):
    with patch.object(db, "DB_PATH", test_db):
        # One extracted, one not
        db.save_job_listing(db.JobListing(
            id=None, source="alfred", source_id="ext-1",
            title="Extracted", employer_name="Corp",
            extracted_at="2026-03-01T12:00:00",
        ))
        db.save_job_listing(db.JobListing(
            id=None, source="alfred", source_id="ext-2",
            title="Not Extracted", employer_name="Corp",
        ))

        unextracted = db.get_unextracted_jobs()
        assert len(unextracted) == 1
        assert unextracted[0]["title"] == "Not Extracted"


def test_get_unmatched_jobs(test_db, sample_company):
    with patch.object(db, "DB_PATH", test_db):
        db.save_job_listing(db.JobListing(
            id=None, source="alfred", source_id="match-1",
            title="Matched", employer_name="Corp",
            company_id=sample_company,
        ))
        db.save_job_listing(db.JobListing(
            id=None, source="alfred", source_id="match-2",
            title="Unmatched", employer_name="Corp",
        ))

        unmatched = db.get_unmatched_jobs()
        assert len(unmatched) == 1
        assert unmatched[0]["title"] == "Unmatched"


def test_get_jobs_needing_salary_estimate(test_db):
    with patch.object(db, "DB_PATH", test_db):
        db.save_job_listing(db.JobListing(
            id=None, source="alfred", source_id="se-1",
            title="Has Salary", employer_name="Corp",
            estimated_salary=900000,
        ))
        db.save_job_listing(db.JobListing(
            id=None, source="alfred", source_id="se-2",
            title="Needs Salary", employer_name="Corp",
        ))

        needing = db.get_jobs_needing_salary_estimate()
        assert len(needing) == 1
        assert needing[0]["title"] == "Needs Salary"


def test_deactivate_stale_jobs_removed_from_source(test_db):
    with patch.object(db, "DB_PATH", test_db):
        # Create 3 jobs
        for i in range(3):
            db.save_job_listing(db.JobListing(
                id=None, source="alfred", source_id=f"stale-{i}",
                title=f"Job {i}", employer_name="Corp",
            ))

        # Only stale-0 is still active on the source
        count = db.deactivate_stale_jobs("alfred", ["stale-0"])
        assert count >= 2  # stale-1 and stale-2 deactivated

        active = db.get_active_jobs(source="alfred")
        assert len(active) == 1
        assert active[0]["source_id"] == "stale-0"


def test_deactivate_stale_jobs_past_deadline(test_db):
    with patch.object(db, "DB_PATH", test_db):
        # Past deadline job
        db.save_job_listing(db.JobListing(
            id=None, source="starfatorg", source_id="dl-1",
            title="Expired", employer_name="Corp",
            deadline="2020-01-01",
        ))
        # Future deadline job
        db.save_job_listing(db.JobListing(
            id=None, source="starfatorg", source_id="dl-2",
            title="Still Open", employer_name="Corp",
            deadline="2099-12-31",
        ))

        # Pass both IDs as active so rule (a) doesn't trigger
        count = db.deactivate_stale_jobs("starfatorg", ["dl-1", "dl-2"])
        assert count >= 1

        active = db.get_active_jobs(source="starfatorg")
        assert len(active) == 1
        assert active[0]["title"] == "Still Open"


def test_get_job_stats(test_db, sample_company):
    with patch.object(db, "DB_PATH", test_db):
        # Job with everything
        db.save_job_listing(db.JobListing(
            id=None, source="alfred", source_id="stats-1",
            title="Full Job", employer_name="Corp",
            company_id=sample_company,
            estimated_salary=900000,
            extracted_at="2026-03-01T12:00:00",
        ))
        # Job with nothing extra
        db.save_job_listing(db.JobListing(
            id=None, source="starfatorg", source_id="stats-2",
            title="Bare Job", employer_name="Corp",
        ))
        # Inactive job (should not count)
        db.save_job_listing(db.JobListing(
            id=None, source="alfred", source_id="stats-3",
            title="Inactive Job", employer_name="Corp",
            is_active=False,
        ))

        stats = db.get_job_stats()
        assert stats["active_jobs"] == 2
        assert stats["matched_jobs"] == 1
        assert stats["extracted_jobs"] == 1
        assert stats["jobs_with_salary"] == 1
        assert set(stats["job_sources"]) == {"alfred", "starfatorg"}


# ---------------------------------------------------------------------------
# Scraper parse tests
# ---------------------------------------------------------------------------


def test_parse_alfred_job():
    from scripts.scrape_jobs import parse_alfred_job

    raw = {
        "id": "abc-123",
        "title": "Hugbunadarverkfraedingur",
        "brand": {"name": "Acme ehf.", "slug": "acme-ehf"},
        "location": {"name": "Reykjavik", "latitude": 64.15, "longitude": -21.94},
        "employmentType": {"name": "Full-time"},
        "description": "<p>Great job</p>",
        "applicationDeadline": "2026-05-01T00:00:00",
        "createdAt": "2026-03-15T10:00:00",
        "jobCompensations": [],
    }
    listing = parse_alfred_job(raw)
    assert listing.source == "alfred"
    assert listing.source_id == "abc-123"
    assert listing.title == "Hugbunadarverkfraedingur"
    assert listing.employer_name == "Acme ehf."
    assert listing.location == "Reykjavik"
    assert listing.employment_type == "Full-time"
    assert "alfred.is/starf/acme-ehf/abc-123" in listing.source_url
    assert listing.deadline == "2026-05-01"
    assert listing.posted_date == "2026-03-15"
    assert listing.is_active is True


def test_parse_alfred_job_missing_brand():
    """Alfred jobs can have brand=None."""
    from scripts.scrape_jobs import parse_alfred_job

    raw = {
        "id": "no-brand-456",
        "title": "Mystery Job",
        "brand": None,
        "location": None,
        "employmentType": None,
        "description": "Some description",
        "applicationDeadline": None,
        "createdAt": None,
        "jobCompensations": [],
    }
    listing = parse_alfred_job(raw)
    assert listing.source == "alfred"
    assert listing.source_id == "no-brand-456"
    assert listing.employer_name == "Unknown"
    assert listing.location is None
    assert listing.employment_type is None
    assert listing.deadline is None
    assert listing.posted_date is None


def test_parse_starfatorg_job():
    from scripts.scrape_jobs import parse_starfatorg_job

    raw = {
        "id": "x-123",
        "title": "Verkefnastjori",
        "institutionName": "Fjarsysla rikisins",
        "locations": ["Reykjavik"],
        "applicationDeadlineFrom": "2026-03-01",
        "applicationDeadlineTo": "2026-04-15",
        "intro": "Intro text",
        "salaryTerms": "Laun samkvaemi kjarasamningi",
        "tasksAndResponsibilities": "Manage projects",
        "qualificationRequirements": "University degree",
    }
    listing = parse_starfatorg_job(raw)
    assert listing.source == "starfatorg"
    assert listing.source_id == "x-123"
    assert listing.title == "Verkefnastjori"
    assert listing.employer_name == "Fjarsysla rikisins"
    assert listing.location == "Reykjavik"
    assert listing.salary_text == "Laun samkvaemi kjarasamningi"
    assert "island.is/starfatorg/x-123" in listing.source_url
    assert listing.deadline == "2026-04-15"
    assert listing.posted_date == "2026-03-01"
    assert "Intro text" in listing.description_raw
    assert "Manage projects" in listing.description_raw
    assert "University degree" in listing.description_raw
    assert listing.is_active is True


def test_parse_starfatorg_job_minimal():
    """Starfatorg jobs with minimal fields should still parse."""
    from scripts.scrape_jobs import parse_starfatorg_job

    raw = {
        "id": "min-1",
        "title": "Starfsheiti",
        "institutionName": "Stofnun",
        "locations": [],
        "applicationDeadlineFrom": None,
        "applicationDeadlineTo": None,
        "intro": None,
        "salaryTerms": None,
        "tasksAndResponsibilities": None,
        "qualificationRequirements": None,
    }
    listing = parse_starfatorg_job(raw)
    assert listing.source == "starfatorg"
    assert listing.employer_name == "Stofnun"
    assert listing.location is None
    assert listing.salary_text is None
    assert listing.description_raw is None
    assert listing.deadline is None
