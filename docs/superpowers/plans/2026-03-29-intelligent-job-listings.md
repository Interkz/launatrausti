# Intelligent Job Listings — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add salary-enriched job listings from Alfred.is and Island.is Starfatorg, with AI-extracted structured fields, company matching, and a filterable search page.

**Architecture:** Three scrapers feed job listings into a `job_listings` table. Claude API extracts structured fields (hours, benefits, remote). A company matcher links employers to existing companies. A salary engine pre-computes estimated salaries from company financials, VR surveys, and Hagstofa data. A new `/jobs` page displays the results with filtering.

**Tech Stack:** FastAPI, SQLite, httpx (Alfred API), requests (Starfatorg GraphQL), anthropic (Claude API for extraction), Jinja2 templates.

**Spec:** `docs/superpowers/specs/2026-03-29-intelligent-job-listings-design.md`

---

## File Map

### New Files
| File | Responsibility |
|------|---------------|
| `src/job_extractor.py` | Claude API prompt + parse for extracting structured fields from job descriptions |
| `src/company_matcher.py` | Match employer names to companies table; discover new companies via Skatturinn API |
| `src/salary_engine.py` | Compute estimated salary from 4 data sources (job text, company avg, VR, Hagstofa) |
| `scripts/scrape_jobs.py` | Unified CLI: scrape Alfred + Starfatorg, deactivate stale jobs |
| `scripts/extract_jobs.py` | CLI: run AI extraction on unextracted job listings |
| `scripts/match_companies.py` | CLI: match unmatched job employers to companies |
| `scripts/estimate_salaries.py` | CLI: pre-compute salary estimates for all active jobs |
| `src/templates/jobs.html` | Job search/filter page template |
| `tests/test_jobs.py` | All job-related tests |
| `.github/workflows/data-pipeline.yml` | Daily cron pipeline |

### Modified Files
| File | Changes |
|------|---------|
| `src/database.py` | Add `job_listings` table, `JobListing` dataclass, 8 query functions |
| `src/main.py` | Add `/jobs`, `/api/jobs` routes; add jobs section to company detail |
| `src/templates/company.html` | Add "Laus storf" section showing matched jobs |
| `src/templates/base.html` | Add "Storf" nav link |
| `scripts/run_pipeline.py` | Add stages 8-11, update TOTAL_STAGES to 11 |
| `requirements.txt` | Add `httpx>=0.27.0` |
| `tests/conftest.py` | Add `sample_jobs` fixture |

---

## Task 1: Database Schema — `job_listings` table

**Files:**
- Modify: `src/database.py`
- Test: `tests/test_jobs.py`

- [ ] **Step 1: Write failing test for job_listings table creation**

In `tests/test_jobs.py`:
```python
"""Tests for job listings feature."""
import json
from datetime import datetime
from unittest.mock import patch
import pytest
import src.database as db


def test_job_listings_table_exists(test_db):
    """job_listings table should be created by init_db."""
    with patch.object(db, "DB_PATH", test_db):
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='job_listings'")
        assert cursor.fetchone() is not None
        conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/emiltrausti/launatrausti && pytest tests/test_jobs.py::test_job_listings_table_exists -v`
Expected: FAIL (table doesn't exist yet)

- [ ] **Step 3: Add job_listings table to init_db()**

In `src/database.py`, add the `JobListing` dataclass after `ScrapeLogEntry`:

```python
@dataclass
class JobListing:
    id: Optional[int]
    source: str
    source_id: Optional[str]
    title: str
    employer_name: str
    company_id: Optional[int]
    location: Optional[str]
    location_lat: Optional[float]
    location_lon: Optional[float]
    employment_type: Optional[str]
    description_raw: Optional[str]
    source_url: Optional[str]
    posted_date: Optional[str]
    deadline: Optional[str]
    work_hours: Optional[str]
    remote_policy: Optional[str]
    salary_text: Optional[str]
    salary_lower: Optional[int]
    salary_upper: Optional[int]
    benefits: Optional[str]
    union_name: Optional[str]
    languages: Optional[str]
    education_required: Optional[str]
    experience_years: Optional[str]
    estimated_salary: Optional[int]
    salary_source: Optional[str]
    salary_confidence: Optional[float]
    salary_details: Optional[str]
    extracted_at: Optional[str]
    is_active: bool = True
```

In `init_db()`, after the `hagstofa_occupations` table creation, add:

```python
cursor.execute("""
    CREATE TABLE IF NOT EXISTS job_listings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        source_id TEXT,
        title TEXT NOT NULL,
        employer_name TEXT NOT NULL,
        company_id INTEGER,
        location TEXT,
        location_lat REAL,
        location_lon REAL,
        employment_type TEXT,
        description_raw TEXT,
        source_url TEXT,
        posted_date TEXT,
        deadline TEXT,
        work_hours TEXT,
        remote_policy TEXT,
        salary_text TEXT,
        salary_lower INTEGER,
        salary_upper INTEGER,
        benefits TEXT,
        union_name TEXT,
        languages TEXT,
        education_required TEXT,
        experience_years TEXT,
        estimated_salary INTEGER,
        salary_source TEXT,
        salary_confidence REAL,
        salary_details TEXT,
        extracted_at TEXT,
        is_active BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT (datetime('now')),
        updated_at DATETIME DEFAULT (datetime('now')),
        UNIQUE(source, source_id)
    )
""")

cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_company ON job_listings(company_id)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_active ON job_listings(is_active)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_source ON job_listings(source)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_deadline ON job_listings(deadline)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_salary ON job_listings(estimated_salary)")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/emiltrausti/launatrausti && pytest tests/test_jobs.py::test_job_listings_table_exists -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /home/emiltrausti/launatrausti
git add src/database.py tests/test_jobs.py
git commit -m "feat: add job_listings table schema and JobListing dataclass"
```

---

## Task 2: Database Query Functions

**Files:**
- Modify: `src/database.py`
- Test: `tests/test_jobs.py`

- [ ] **Step 1: Write failing tests for save_job_listing and query functions**

Append to `tests/test_jobs.py`:
```python
def test_save_job_listing_insert(test_db):
    """save_job_listing should insert a new job and return its id."""
    with patch.object(db, "DB_PATH", test_db):
        listing = db.JobListing(
            id=None, source="alfred", source_id="abc123",
            title="Software Developer", employer_name="Test Company ehf.",
            company_id=None, location="Reykjavik", location_lat=64.1466,
            location_lon=-21.9426, employment_type="full-time",
            description_raw="A great job", source_url="https://alfred.is/jobs/abc123",
            posted_date="2026-03-01", deadline="2026-04-01",
            work_hours=None, remote_policy=None, salary_text=None,
            salary_lower=None, salary_upper=None, benefits=None,
            union_name=None, languages=None, education_required=None,
            experience_years=None, estimated_salary=None, salary_source=None,
            salary_confidence=None, salary_details=None, extracted_at=None,
            is_active=True,
        )
        job_id = db.save_job_listing(listing)
        assert job_id > 0


def test_save_job_listing_upsert(test_db):
    """save_job_listing should update on conflict (same source + source_id)."""
    with patch.object(db, "DB_PATH", test_db):
        listing = db.JobListing(
            id=None, source="alfred", source_id="abc123",
            title="Software Developer", employer_name="Test ehf.",
            company_id=None, location="Reykjavik", location_lat=None,
            location_lon=None, employment_type="full-time",
            description_raw="V1", source_url=None,
            posted_date="2026-03-01", deadline=None,
            work_hours=None, remote_policy=None, salary_text=None,
            salary_lower=None, salary_upper=None, benefits=None,
            union_name=None, languages=None, education_required=None,
            experience_years=None, estimated_salary=None, salary_source=None,
            salary_confidence=None, salary_details=None, extracted_at=None,
            is_active=True,
        )
        id1 = db.save_job_listing(listing)
        listing.title = "Senior Software Developer"
        listing.description_raw = "V2"
        id2 = db.save_job_listing(listing)
        # Should update, not insert new row
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM job_listings WHERE source='alfred' AND source_id='abc123'")
        assert cursor.fetchone()["cnt"] == 1
        cursor.execute("SELECT title FROM job_listings WHERE source='alfred' AND source_id='abc123'")
        assert cursor.fetchone()["title"] == "Senior Software Developer"
        conn.close()


def test_get_active_jobs_filters(test_db):
    """get_active_jobs should filter by salary, location, etc."""
    with patch.object(db, "DB_PATH", test_db):
        for i, (title, salary, loc) in enumerate([
            ("Job A", 700000, "Reykjavik"),
            ("Job B", 500000, "Akureyri"),
            ("Job C", 900000, "Reykjavik"),
        ]):
            listing = db.JobListing(
                id=None, source="alfred", source_id=f"job{i}",
                title=title, employer_name="Co", company_id=None,
                location=loc, location_lat=None, location_lon=None,
                employment_type="full-time", description_raw="desc",
                source_url=None, posted_date="2026-03-01", deadline=None,
                work_hours=None, remote_policy=None, salary_text=None,
                salary_lower=None, salary_upper=None, benefits=None,
                union_name=None, languages=None, education_required=None,
                experience_years=None, estimated_salary=salary,
                salary_source="test", salary_confidence=0.8,
                salary_details="test", extracted_at=None, is_active=True,
            )
            db.save_job_listing(listing)

        # Filter by salary min
        jobs = db.get_active_jobs(salary_min=600000)
        assert len(jobs) == 2
        # Filter by location
        jobs = db.get_active_jobs(location="Reykjavik")
        assert len(jobs) == 2
        # Pagination
        jobs = db.get_active_jobs(limit=1, offset=0)
        assert len(jobs) == 1


def test_get_company_jobs(test_db, sample_company):
    """get_company_jobs should return jobs matched to a company."""
    with patch.object(db, "DB_PATH", test_db):
        listing = db.JobListing(
            id=None, source="alfred", source_id="matched1",
            title="Dev", employer_name="Test Company ehf.",
            company_id=sample_company, location=None, location_lat=None,
            location_lon=None, employment_type=None, description_raw=None,
            source_url=None, posted_date=None, deadline=None,
            work_hours=None, remote_policy=None, salary_text=None,
            salary_lower=None, salary_upper=None, benefits=None,
            union_name=None, languages=None, education_required=None,
            experience_years=None, estimated_salary=None, salary_source=None,
            salary_confidence=None, salary_details=None, extracted_at=None,
            is_active=True,
        )
        db.save_job_listing(listing)
        jobs = db.get_company_jobs(sample_company)
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Dev"


def test_deactivate_stale_jobs(test_db):
    """deactivate_stale_jobs should mark missing and old jobs as inactive."""
    with patch.object(db, "DB_PATH", test_db):
        for sid, deadline in [("fresh", "2026-12-01"), ("expired", "2025-01-01"), ("gone", "2026-12-01")]:
            listing = db.JobListing(
                id=None, source="alfred", source_id=sid,
                title=f"Job {sid}", employer_name="Co",
                company_id=None, location=None, location_lat=None,
                location_lon=None, employment_type=None, description_raw=None,
                source_url=None, posted_date="2026-01-01", deadline=deadline,
                work_hours=None, remote_policy=None, salary_text=None,
                salary_lower=None, salary_upper=None, benefits=None,
                union_name=None, languages=None, education_required=None,
                experience_years=None, estimated_salary=None, salary_source=None,
                salary_confidence=None, salary_details=None, extracted_at=None,
                is_active=True,
            )
            db.save_job_listing(listing)

        # "gone" is no longer in active_source_ids
        db.deactivate_stale_jobs("alfred", ["fresh", "expired"])
        jobs = db.get_active_jobs()
        # "fresh" stays (in active list, future deadline)
        # "expired" stays in active list but has past deadline — deactivated by deadline check
        # "gone" not in active list — deactivated
        active_ids = [j["source_id"] for j in jobs]
        assert "fresh" in active_ids
        assert "gone" not in active_ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/emiltrausti/launatrausti && pytest tests/test_jobs.py -v`
Expected: FAIL (functions don't exist yet)

- [ ] **Step 3: Implement query functions in database.py**

Add these functions to `src/database.py` after the existing query functions:

```python
def save_job_listing(listing: JobListing) -> int:
    """Insert or update a job listing. Returns the row id."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO job_listings
            (source, source_id, title, employer_name, company_id,
             location, location_lat, location_lon, employment_type,
             description_raw, source_url, posted_date, deadline,
             work_hours, remote_policy, salary_text, salary_lower, salary_upper,
             benefits, union_name, languages, education_required, experience_years,
             estimated_salary, salary_source, salary_confidence, salary_details,
             extracted_at, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (source, source_id) DO UPDATE SET
            title = excluded.title,
            employer_name = excluded.employer_name,
            company_id = COALESCE(excluded.company_id, job_listings.company_id),
            location = excluded.location,
            location_lat = excluded.location_lat,
            location_lon = excluded.location_lon,
            employment_type = excluded.employment_type,
            description_raw = excluded.description_raw,
            source_url = excluded.source_url,
            posted_date = excluded.posted_date,
            deadline = excluded.deadline,
            updated_at = datetime('now')
    """, (listing.source, listing.source_id, listing.title, listing.employer_name,
          listing.company_id, listing.location, listing.location_lat, listing.location_lon,
          listing.employment_type, listing.description_raw, listing.source_url,
          listing.posted_date, listing.deadline,
          listing.work_hours, listing.remote_policy, listing.salary_text,
          listing.salary_lower, listing.salary_upper, listing.benefits,
          listing.union_name, listing.languages, listing.education_required,
          listing.experience_years, listing.estimated_salary, listing.salary_source,
          listing.salary_confidence, listing.salary_details, listing.extracted_at,
          1 if listing.is_active else 0))

    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_active_jobs(
    salary_min: Optional[int] = None,
    salary_max: Optional[int] = None,
    location: Optional[str] = None,
    employment_type: Optional[str] = None,
    remote_policy: Optional[str] = None,
    source: Optional[str] = None,
    company_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Get active job listings with optional filters and pagination."""
    conn = get_connection()
    cursor = conn.cursor()

    where = ["is_active = 1"]
    params = []

    if salary_min is not None:
        where.append("estimated_salary >= ?")
        params.append(salary_min)
    if salary_max is not None:
        where.append("estimated_salary <= ?")
        params.append(salary_max)
    if location:
        where.append("location LIKE ?")
        params.append(f"%{location}%")
    if employment_type:
        where.append("employment_type = ?")
        params.append(employment_type)
    if remote_policy:
        where.append("remote_policy = ?")
        params.append(remote_policy)
    if source:
        where.append("source = ?")
        params.append(source)
    if company_id is not None:
        where.append("company_id = ?")
        params.append(company_id)

    where_sql = " AND ".join(where)
    params.extend([limit, offset])

    cursor.execute(f"""
        SELECT * FROM job_listings
        WHERE {where_sql}
        ORDER BY estimated_salary DESC NULLS LAST, posted_date DESC
        LIMIT ? OFFSET ?
    """, params)

    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_company_jobs(company_id: int) -> list[dict]:
    """Get active job listings for a specific company."""
    return get_active_jobs(company_id=company_id, limit=100)


def get_unextracted_jobs(limit: int = 100) -> list[dict]:
    """Get active jobs that haven't been through AI extraction yet."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM job_listings
        WHERE extracted_at IS NULL AND is_active = 1
        ORDER BY created_at ASC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unmatched_jobs() -> list[dict]:
    """Get active jobs with no company_id match."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM job_listings
        WHERE company_id IS NULL AND is_active = 1
        ORDER BY employer_name
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_jobs_needing_salary_estimate() -> list[dict]:
    """Get active jobs where estimated_salary is NULL."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM job_listings
        WHERE estimated_salary IS NULL AND is_active = 1
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def deactivate_stale_jobs(source: str, active_source_ids: list[str]) -> int:
    """Mark jobs as inactive if removed from source, past deadline, or >90 days old.
    Returns count of deactivated jobs."""
    conn = get_connection()
    cursor = conn.cursor()
    deactivated = 0

    # 1. Deactivate jobs not in active source list
    if active_source_ids:
        placeholders = ",".join("?" for _ in active_source_ids)
        cursor.execute(f"""
            UPDATE job_listings SET is_active = 0, updated_at = datetime('now')
            WHERE source = ? AND is_active = 1 AND source_id NOT IN ({placeholders})
        """, [source] + active_source_ids)
        deactivated += cursor.rowcount

    # 2. Deactivate jobs past deadline
    cursor.execute("""
        UPDATE job_listings SET is_active = 0, updated_at = datetime('now')
        WHERE is_active = 1 AND deadline IS NOT NULL AND deadline < date('now')
    """)
    deactivated += cursor.rowcount

    # 3. Deactivate jobs older than 90 days
    cursor.execute("""
        UPDATE job_listings SET is_active = 0, updated_at = datetime('now')
        WHERE is_active = 1 AND posted_date IS NOT NULL
        AND posted_date < date('now', '-90 days')
    """)
    deactivated += cursor.rowcount

    conn.commit()
    conn.close()
    return deactivated


def get_job_stats() -> dict:
    """Get job listing statistics."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as cnt FROM job_listings WHERE is_active = 1")
    active = cursor.fetchone()["cnt"]
    cursor.execute("SELECT COUNT(*) as cnt FROM job_listings WHERE company_id IS NOT NULL AND is_active = 1")
    matched = cursor.fetchone()["cnt"]
    cursor.execute("SELECT COUNT(*) as cnt FROM job_listings WHERE extracted_at IS NOT NULL AND is_active = 1")
    extracted = cursor.fetchone()["cnt"]
    cursor.execute("SELECT COUNT(*) as cnt FROM job_listings WHERE estimated_salary IS NOT NULL AND is_active = 1")
    with_salary = cursor.fetchone()["cnt"]
    cursor.execute("SELECT COUNT(DISTINCT source) as cnt FROM job_listings")
    sources = cursor.fetchone()["cnt"]

    conn.close()
    return {
        "active_jobs": active,
        "matched_jobs": matched,
        "extracted_jobs": extracted,
        "jobs_with_salary": with_salary,
        "job_sources": sources,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/emiltrausti/launatrausti && pytest tests/test_jobs.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite for regression**

Run: `cd /home/emiltrausti/launatrausti && pytest -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
cd /home/emiltrausti/launatrausti
git add src/database.py tests/test_jobs.py
git commit -m "feat: add job_listings query functions — save, filter, deactivate"
```

---

## Task 3: Alfred.is Job Scraper

**Files:**
- Create: `scripts/scrape_jobs.py`
- Test: `tests/test_jobs.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Add httpx to requirements.txt**

Append `httpx>=0.27.0` to `requirements.txt`.

- [ ] **Step 2: Install httpx**

Run: `cd /home/emiltrausti/launatrausti && pip install httpx>=0.27.0`

- [ ] **Step 3: Write failing test for Alfred scraper parsing**

Append to `tests/test_jobs.py`:
```python
def test_parse_alfred_job():
    """parse_alfred_job should convert Alfred API response to JobListing."""
    # Import after module exists
    from scripts.scrape_jobs import parse_alfred_job

    raw = {
        "id": "abc-123",
        "title": "Hugbunadarverkfraedingur",
        "brand": {"name": "Acme ehf.", "slug": "acme-ehf"},
        "location": {"name": "Reykjavik", "latitude": 64.15, "longitude": -21.94},
        "employmentType": {"name": "Full-time"},
        "jobType": {"name": "Information Technology"},
        "description": "<p>Great job opportunity</p>",
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
    assert listing.source_url == "https://alfred.is/starf/acme-ehf/abc-123"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd /home/emiltrausti/launatrausti && pytest tests/test_jobs.py::test_parse_alfred_job -v`

- [ ] **Step 5: Implement scrape_jobs.py**

Create `scripts/scrape_jobs.py`:
```python
#!/usr/bin/env python3
"""
Job listing scraper for Launatrausti.

Scrapes job listings from:
- Alfred.is (public REST API)
- Island.is Starfatorg (public GraphQL)

Usage:
    python scripts/scrape_jobs.py                    # Scrape all sources
    python scripts/scrape_jobs.py --source alfred    # Only Alfred
    python scripts/scrape_jobs.py --source starfatorg # Only Starfatorg
    python scripts/scrape_jobs.py --dry-run          # Preview without saving
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
import requests
from src.database import (
    JobListing, save_job_listing, deactivate_stale_jobs,
    get_job_stats, init_db,
)

logger = logging.getLogger(__name__)

ALFRED_API_URL = "https://userapi.alfred.is/api/v2/jobs"
ALFRED_PAGE_SIZE = 50
ALFRED_RATE_LIMIT = 1.0  # seconds between requests

STARFATORG_URL = "https://island.is/api/graphql"


# ---------------------------------------------------------------------------
# Alfred.is
# ---------------------------------------------------------------------------

def parse_alfred_job(raw: dict) -> JobListing:
    """Convert an Alfred API job object to a JobListing."""
    brand = raw.get("brand") or {}
    location = raw.get("location") or {}
    emp_type = raw.get("employmentType") or {}
    deadline = raw.get("applicationDeadline")
    created = raw.get("createdAt")

    # Build source URL from brand slug + job id
    slug = brand.get("slug", "")
    job_id = str(raw.get("id", ""))
    source_url = f"https://alfred.is/starf/{slug}/{job_id}" if slug else None

    return JobListing(
        id=None,
        source="alfred",
        source_id=job_id,
        title=raw.get("title", ""),
        employer_name=brand.get("name", "Unknown"),
        company_id=None,
        location=location.get("name"),
        location_lat=location.get("latitude"),
        location_lon=location.get("longitude"),
        employment_type=emp_type.get("name"),
        description_raw=raw.get("description", ""),
        source_url=source_url,
        posted_date=created[:10] if created else None,
        deadline=deadline[:10] if deadline else None,
        work_hours=None,
        remote_policy=None,
        salary_text=None,
        salary_lower=None,
        salary_upper=None,
        benefits=None,
        union_name=None,
        languages=None,
        education_required=None,
        experience_years=None,
        estimated_salary=None,
        salary_source=None,
        salary_confidence=None,
        salary_details=None,
        extracted_at=None,
        is_active=True,
    )


def scrape_alfred(dry_run: bool = False) -> list[str]:
    """Scrape all jobs from Alfred.is API. Returns list of source_ids seen."""
    logger.info("Scraping Alfred.is jobs...")
    seen_ids = []
    page = 1
    total_saved = 0

    with httpx.Client(timeout=30.0) as client:
        while True:
            logger.info("  Fetching page %d (size=%d)...", page, ALFRED_PAGE_SIZE)
            try:
                resp = client.get(
                    ALFRED_API_URL,
                    params={"page": page, "size": ALFRED_PAGE_SIZE, "translate": "false"},
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.error("  Failed to fetch page %d: %s", page, e)
                break

            jobs = data if isinstance(data, list) else data.get("jobs", data.get("data", []))
            if not jobs:
                break

            for raw_job in jobs:
                listing = parse_alfred_job(raw_job)
                seen_ids.append(listing.source_id)
                if not dry_run:
                    save_job_listing(listing)
                    total_saved += 1

            logger.info("  Page %d: %d jobs", page, len(jobs))

            if len(jobs) < ALFRED_PAGE_SIZE:
                break

            page += 1
            time.sleep(ALFRED_RATE_LIMIT)

    logger.info("Alfred.is: %d jobs scraped, %d saved", len(seen_ids), total_saved)
    return seen_ids


# ---------------------------------------------------------------------------
# Island.is Starfatorg
# ---------------------------------------------------------------------------

STARFATORG_LIST_QUERY = """
query {
  icelandicGovernmentInstitutionVacancies(input: {}) {
    vacancies {
      id
      title
      institutionName
      intro
      applicationDeadlineFrom
      applicationDeadlineTo
      fieldOfWork
      locations
    }
  }
}
"""

STARFATORG_DETAIL_QUERY = """
query($id: String!) {
  icelandicGovernmentInstitutionVacancyById(id: $id) {
    id
    title
    institutionName
    intro
    applicationDeadlineFrom
    applicationDeadlineTo
    fieldOfWork
    locations
    salaryTerms
    jobPercentage
    qualificationRequirements
    tasksAndResponsibilities
  }
}
"""


def parse_starfatorg_job(raw: dict) -> JobListing:
    """Convert a Starfatorg vacancy to a JobListing."""
    deadline_to = raw.get("applicationDeadlineTo")
    deadline_from = raw.get("applicationDeadlineFrom")
    deadline = (deadline_to or deadline_from or "")[:10] if (deadline_to or deadline_from) else None

    locations = raw.get("locations") or []
    location = locations[0] if locations else None

    # Combine all text fields for description
    parts = []
    for field in ["intro", "tasksAndResponsibilities", "qualificationRequirements", "salaryTerms"]:
        val = raw.get(field)
        if val:
            parts.append(val)
    description = "\n\n".join(parts)

    return JobListing(
        id=None,
        source="starfatorg",
        source_id=str(raw.get("id", "")),
        title=raw.get("title", ""),
        employer_name=raw.get("institutionName", "Unknown"),
        company_id=None,
        location=location,
        location_lat=None,
        location_lon=None,
        employment_type=None,
        description_raw=description,
        source_url=f"https://island.is/starfatorg/{raw.get('id', '')}",
        posted_date=None,
        deadline=deadline,
        work_hours=None,
        remote_policy=None,
        salary_text=raw.get("salaryTerms"),
        salary_lower=None,
        salary_upper=None,
        benefits=None,
        union_name=None,
        languages=None,
        education_required=None,
        experience_years=None,
        estimated_salary=None,
        salary_source=None,
        salary_confidence=None,
        salary_details=None,
        extracted_at=None,
        is_active=True,
    )


def scrape_starfatorg(dry_run: bool = False) -> list[str]:
    """Scrape government vacancies from Island.is Starfatorg. Returns source_ids."""
    logger.info("Scraping Island.is Starfatorg...")
    seen_ids = []
    total_saved = 0

    session = requests.Session()

    # Fetch vacancy list
    try:
        resp = session.post(
            STARFATORG_URL,
            json={"query": STARFATORG_LIST_QUERY},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
    except Exception as e:
        logger.error("Failed to fetch Starfatorg vacancies: %s", e)
        return []

    vacancies = (
        result.get("data", {})
        .get("icelandicGovernmentInstitutionVacancies", {})
        .get("vacancies", [])
    )
    logger.info("  Found %d vacancies", len(vacancies))

    # Fetch details for each vacancy (salaryTerms, etc.)
    for i, v in enumerate(vacancies, 1):
        vid = v.get("id")
        if not vid:
            continue

        try:
            detail_resp = session.post(
                STARFATORG_URL,
                json={"query": STARFATORG_DETAIL_QUERY, "variables": {"id": str(vid)}},
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            detail_resp.raise_for_status()
            detail_data = detail_resp.json()
            detail = (
                detail_data.get("data", {})
                .get("icelandicGovernmentInstitutionVacancyById", {})
            )
            if detail:
                v.update(detail)
        except Exception as e:
            logger.warning("  Failed to fetch detail for %s: %s", vid, e)

        listing = parse_starfatorg_job(v)
        seen_ids.append(listing.source_id)
        if not dry_run:
            save_job_listing(listing)
            total_saved += 1

        if i % 50 == 0:
            logger.info("  Processed %d/%d vacancies", i, len(vacancies))
            time.sleep(0.5)

    logger.info("Starfatorg: %d vacancies scraped, %d saved", len(seen_ids), total_saved)
    return seen_ids


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scrape job listings for Launatrausti")
    parser.add_argument("--source", choices=["alfred", "starfatorg", "all"], default="all")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    init_db()

    sources = [args.source] if args.source != "all" else ["alfred", "starfatorg"]

    for source in sources:
        if source == "alfred":
            seen = scrape_alfred(dry_run=args.dry_run)
            if not args.dry_run and seen:
                deactivated = deactivate_stale_jobs("alfred", seen)
                logger.info("Deactivated %d stale Alfred jobs", deactivated)
        elif source == "starfatorg":
            seen = scrape_starfatorg(dry_run=args.dry_run)
            if not args.dry_run and seen:
                deactivated = deactivate_stale_jobs("starfatorg", seen)
                logger.info("Deactivated %d stale Starfatorg jobs", deactivated)

    # Print stats
    stats = get_job_stats()
    print(f"\nJob stats: {stats['active_jobs']} active, "
          f"{stats['matched_jobs']} matched, "
          f"{stats['extracted_jobs']} extracted")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd /home/emiltrausti/launatrausti && pytest tests/test_jobs.py::test_parse_alfred_job -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
cd /home/emiltrausti/launatrausti
git add scripts/scrape_jobs.py requirements.txt tests/test_jobs.py
git commit -m "feat: add Alfred + Starfatorg job scrapers"
```

---

## Task 4: Job Field Extractor (Claude API)

**Files:**
- Create: `src/job_extractor.py`
- Create: `scripts/extract_jobs.py`
- Test: `tests/test_jobs.py`

- [ ] **Step 1: Write failing test for job extraction parsing**

Append to `tests/test_jobs.py`:
```python
def test_parse_job_extraction_response():
    """parse_extraction_response should handle Claude JSON output."""
    from src.job_extractor import parse_extraction_response

    raw_json = '{"work_hours": "8:00-16:00", "remote_policy": "hybrid", "salary_text": null, "salary_lower": null, "salary_upper": null, "benefits": ["lunch", "gym"], "union_name": "VR", "languages": ["is", "en"], "education_required": "university", "experience_years": "3-5"}'
    result = parse_extraction_response(raw_json)
    assert result["work_hours"] == "8:00-16:00"
    assert result["remote_policy"] == "hybrid"
    assert result["benefits"] == ["lunch", "gym"]
    assert result["languages"] == ["is", "en"]


def test_parse_job_extraction_response_markdown_wrapped():
    """Should handle Claude wrapping JSON in markdown code blocks."""
    from src.job_extractor import parse_extraction_response

    raw = '```json\n{"work_hours": "flexible", "remote_policy": "remote", "salary_text": "750k", "salary_lower": 750000, "salary_upper": null, "benefits": [], "union_name": null, "languages": ["is"], "education_required": null, "experience_years": null}\n```'
    result = parse_extraction_response(raw)
    assert result["work_hours"] == "flexible"
    assert result["salary_lower"] == 750000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/emiltrausti/launatrausti && pytest tests/test_jobs.py::test_parse_job_extraction_response -v`

- [ ] **Step 3: Create src/job_extractor.py**

```python
"""
Job listing field extractor using Claude API.

Extracts structured fields (work hours, remote policy, salary, benefits, etc.)
from raw job description text. Same pattern as src/extractor.py.
"""

import json
import os
import re
from typing import Optional

import anthropic


JOB_EXTRACTION_PROMPT = """You are an expert at extracting structured information from Icelandic and English job listings.

Extract the following fields from this job listing text. Return ONLY valid JSON, no other text.

Fields to extract:
1. work_hours: Working hours if mentioned (e.g., "8:00-16:00", "flexible", "shift work"). null if not mentioned.
2. remote_policy: One of "remote", "hybrid", "onsite", or null if not mentioned. Look for "fjarvinnu", "heimavinna", "remote", "hybrid", "a starfsstod".
3. salary_text: The exact salary text if any salary/compensation is mentioned. null if not mentioned.
4. salary_lower: Lower bound of salary range in ISK per month (integer). null if not mentioned. Convert from annual if needed.
5. salary_upper: Upper bound of salary range in ISK per month (integer). null if not mentioned.
6. benefits: Array of benefit keywords found. Use these standard keys: "lunch", "gym", "pension_extra", "flexible_hours", "stock_options", "car_allowance", "phone_allowance", "education_budget", "health_insurance", "dental", "parental_leave_extra", "vacation_extra". Empty array if none mentioned.
7. union_name: Name of the union if mentioned (e.g., "VR", "Efling", "SI"). null if not mentioned.
8. languages: Array of required language codes (e.g., ["is", "en", "da"]). Empty array if not mentioned.
9. education_required: One of "phd", "masters", "university", "trade_school", "secondary", "none", or null if not mentioned.
10. experience_years: Experience requirement as a range string (e.g., "0-2", "3-5", "5+", "10+"). null if not mentioned.

Important:
- Icelandic salary numbers use dots for thousands (750.000 = 750000)
- "Laun samkvaemi kjarasamningi" means "salary per collective agreement" — this is NOT a specific salary, return null for salary fields
- Return null for any field you cannot confidently extract
- Benefits must use ONLY the standard keys listed above

Return JSON in this exact format:
{
    "work_hours": "string or null",
    "remote_policy": "string or null",
    "salary_text": "string or null",
    "salary_lower": "integer or null",
    "salary_upper": "integer or null",
    "benefits": [],
    "union_name": "string or null",
    "languages": [],
    "education_required": "string or null",
    "experience_years": "string or null"
}

Job listing text:
"""


def parse_extraction_response(response_text: str) -> dict:
    """Parse Claude's JSON response, handling markdown code blocks."""
    text = response_text.strip()

    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    return json.loads(text.strip())


def extract_job_fields(description: str, api_key: Optional[str] = None) -> dict:
    """Use Claude to extract structured fields from a job description.

    Returns a dict with keys matching the JOB_EXTRACTION_PROMPT output format.
    """
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)

    # Strip HTML tags for cleaner extraction
    clean_text = re.sub(r'<[^>]+>', ' ', description)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()

    # Truncate if too long
    if len(clean_text) > 8000:
        clean_text = clean_text[:8000]

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        messages=[{"role": "user", "content": JOB_EXTRACTION_PROMPT + clean_text}],
    )

    return parse_extraction_response(message.content[0].text)


def extract_salary_regex(text: str) -> tuple[Optional[int], Optional[int], Optional[str]]:
    """Regex fallback for obvious salary patterns. Returns (lower, upper, raw_text).

    Handles patterns like:
    - "750.000 - 900.000 kr"
    - "750.000 kr/man"
    - "Laun: 850.000"
    """
    clean = re.sub(r'<[^>]+>', ' ', text)

    # Pattern: "NNN.NNN - NNN.NNN" (with optional kr/man suffix)
    range_match = re.search(
        r'(\d{3}(?:\.\d{3})+)\s*[-–]\s*(\d{3}(?:\.\d{3})+)\s*(?:kr|ISK)?',
        clean,
    )
    if range_match:
        lower = int(range_match.group(1).replace('.', ''))
        upper = int(range_match.group(2).replace('.', ''))
        if 200_000 <= lower <= 3_000_000 and 200_000 <= upper <= 5_000_000:
            return lower, upper, range_match.group(0).strip()

    # Pattern: single "NNN.NNN kr" after salary-related word
    single_match = re.search(
        r'(?:[Ll]aun|[Mm]anadarlaun|[Ss]alary)[^\d]{0,20}(\d{3}(?:\.\d{3})+)\s*(?:kr|ISK)?',
        clean,
    )
    if single_match:
        val = int(single_match.group(1).replace('.', ''))
        if 200_000 <= val <= 5_000_000:
            return val, None, single_match.group(0).strip()

    return None, None, None
```

- [ ] **Step 4: Create scripts/extract_jobs.py**

```python
#!/usr/bin/env python3
"""
Extract structured fields from job listing descriptions using Claude API.

Usage:
    python scripts/extract_jobs.py              # Extract all unextracted jobs
    python scripts/extract_jobs.py --limit 10   # Limit to 10 jobs
    python scripts/extract_jobs.py --dry-run    # Preview without calling API
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import get_connection, get_unextracted_jobs, init_db
from src.job_extractor import extract_job_fields, extract_salary_regex

logger = logging.getLogger(__name__)
RATE_LIMIT = 0.5  # seconds between API calls


def extract_all(limit: int = 100, dry_run: bool = False) -> int:
    """Run AI extraction on unextracted job listings. Returns count processed."""
    jobs = get_unextracted_jobs(limit=limit)
    logger.info("Found %d unextracted jobs (limit=%d)", len(jobs), limit)

    processed = 0
    conn = get_connection() if not dry_run else None

    for i, job in enumerate(jobs, 1):
        description = job.get("description_raw", "")
        if not description or len(description.strip()) < 20:
            logger.debug("Skipping job %s: description too short", job["source_id"])
            continue

        if dry_run:
            logger.info("[DRY RUN] Would extract: %s — %s", job["source_id"], job["title"][:50])
            continue

        try:
            # Try regex first (free, instant)
            lower, upper, salary_text = extract_salary_regex(description)

            # Then Claude API for full extraction
            fields = extract_job_fields(description)

            # Regex salary overrides Claude if Claude returned null
            if lower and not fields.get("salary_lower"):
                fields["salary_lower"] = lower
                fields["salary_upper"] = upper
                fields["salary_text"] = salary_text

            # Update job in DB
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE job_listings SET
                    work_hours = ?,
                    remote_policy = ?,
                    salary_text = ?,
                    salary_lower = ?,
                    salary_upper = ?,
                    benefits = ?,
                    union_name = ?,
                    languages = ?,
                    education_required = ?,
                    experience_years = ?,
                    extracted_at = ?
                WHERE id = ?
            """, (
                fields.get("work_hours"),
                fields.get("remote_policy"),
                fields.get("salary_text") or salary_text,
                fields.get("salary_lower") or lower,
                fields.get("salary_upper") or upper,
                json.dumps(fields.get("benefits", [])),
                fields.get("union_name"),
                json.dumps(fields.get("languages", [])),
                fields.get("education_required"),
                fields.get("experience_years"),
                datetime.now().isoformat(),
                job["id"],
            ))
            conn.commit()
            processed += 1

            if i % 10 == 0:
                logger.info("Processed %d/%d jobs", i, len(jobs))

        except Exception as e:
            logger.error("Failed to extract job %s: %s", job["source_id"], e)

        time.sleep(RATE_LIMIT)

    if conn:
        conn.close()

    logger.info("Extraction complete: %d processed out of %d", processed, len(jobs))
    return processed


def main():
    parser = argparse.ArgumentParser(description="Extract structured fields from job listings")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    init_db()
    extract_all(limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/emiltrausti/launatrausti && pytest tests/test_jobs.py -v -k "extraction"`

- [ ] **Step 6: Commit**

```bash
cd /home/emiltrausti/launatrausti
git add src/job_extractor.py scripts/extract_jobs.py tests/test_jobs.py
git commit -m "feat: add job field extractor — Claude API + regex fallback"
```

---

## Task 5: Company Matcher

**Files:**
- Create: `src/company_matcher.py`
- Create: `scripts/match_companies.py`
- Test: `tests/test_jobs.py`

- [ ] **Step 1: Write failing test for company name matching**

Append to `tests/test_jobs.py`:
```python
def test_normalize_company_name():
    """normalize_company_name should strip legal suffixes and normalize."""
    from src.company_matcher import normalize_company_name

    assert normalize_company_name("Acme ehf.") == "acme"
    assert normalize_company_name("Landsbankinn hf") == "landsbankinn"
    assert normalize_company_name("Reykjavikurborg") == "reykjavikurborg"
    assert normalize_company_name("  Foo  Bar  sf  ") == "foo bar"


def test_match_company_exact(test_db, sample_company):
    """match_employer_to_company should find exact name matches."""
    from src.company_matcher import match_employer_to_company

    with patch.object(db, "DB_PATH", test_db):
        result = match_employer_to_company("Test Company ehf.")
        assert result is not None
        assert result == sample_company
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/emiltrausti/launatrausti && pytest tests/test_jobs.py -v -k "company_name or match_company"`

- [ ] **Step 3: Create src/company_matcher.py**

```python
"""
Company name matching for job listings.

Matches employer names from job listings to companies in the database.
Strategy: exact match -> normalized match -> Skatturinn API lookup.
"""

import logging
import re
import unicodedata
from typing import Optional

from .database import get_connection

logger = logging.getLogger(__name__)

# Legal suffixes to strip when normalizing
LEGAL_SUFFIXES = re.compile(
    r'\b(ehf\.?|hf\.?|sf\.?|ses\.?|ohf\.?|bs\.?|svf\.?|slhf\.?|ltd\.?|inc\.?)\s*$',
    re.IGNORECASE,
)


def normalize_company_name(name: str) -> str:
    """Normalize a company name for matching.

    Strips legal suffixes, lowercases, removes accents, collapses whitespace.
    """
    name = name.strip()
    name = LEGAL_SUFFIXES.sub('', name).strip()
    name = name.lower()
    # Remove punctuation except spaces
    name = re.sub(r'[^\w\s]', '', name)
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def _strip_accents(text: str) -> str:
    """Remove accents/diacritics from text."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def match_employer_to_company(employer_name: str) -> Optional[int]:
    """Try to match an employer name to a company in the database.

    Returns company_id if found, None otherwise.

    Strategy:
    1. Exact case-insensitive match on companies.name
    2. Normalized match (strip legal suffixes, compare)
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Strategy 1: Exact match (case-insensitive)
    cursor.execute(
        "SELECT id FROM companies WHERE LOWER(name) = LOWER(?)",
        (employer_name,),
    )
    row = cursor.fetchone()
    if row:
        conn.close()
        return row["id"]

    # Strategy 2: Normalized match
    normalized = normalize_company_name(employer_name)
    if not normalized:
        conn.close()
        return None

    cursor.execute("SELECT id, name FROM companies")
    for company_row in cursor.fetchall():
        if normalize_company_name(company_row["name"]) == normalized:
            conn.close()
            return company_row["id"]

    # Strategy 3: Accent-stripped match
    normalized_ascii = _strip_accents(normalized)
    cursor.execute("SELECT id, name FROM companies")
    for company_row in cursor.fetchall():
        if _strip_accents(normalize_company_name(company_row["name"])) == normalized_ascii:
            conn.close()
            return company_row["id"]

    conn.close()
    return None


def match_all_unmatched() -> dict:
    """Match all unmatched job listings to companies.

    Returns stats: {matched: int, unmatched: int, new_employers: list[str]}
    """
    from .database import get_unmatched_jobs

    jobs = get_unmatched_jobs()
    logger.info("Found %d unmatched jobs", len(jobs))

    # Group by employer name to avoid redundant lookups
    by_employer: dict[str, list[int]] = {}
    for job in jobs:
        name = job["employer_name"]
        by_employer.setdefault(name, []).append(job["id"])

    matched = 0
    unmatched_employers = []

    conn = get_connection()
    cursor = conn.cursor()

    for employer_name, job_ids in by_employer.items():
        company_id = match_employer_to_company(employer_name)

        if company_id:
            placeholders = ",".join("?" for _ in job_ids)
            cursor.execute(
                f"UPDATE job_listings SET company_id = ? WHERE id IN ({placeholders})",
                [company_id] + job_ids,
            )
            matched += len(job_ids)
            logger.debug("Matched '%s' -> company_id=%d (%d jobs)", employer_name, company_id, len(job_ids))
        else:
            unmatched_employers.append(employer_name)

    conn.commit()
    conn.close()

    logger.info("Matching complete: %d matched, %d unmatched employers",
                matched, len(unmatched_employers))

    return {
        "matched": matched,
        "unmatched": len(jobs) - matched,
        "new_employers": unmatched_employers[:50],  # Cap for display
    }
```

- [ ] **Step 4: Create scripts/match_companies.py**

```python
#!/usr/bin/env python3
"""
Match job listing employers to companies in the database.

Usage:
    python scripts/match_companies.py
    python scripts/match_companies.py --verbose
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import init_db
from src.company_matcher import match_all_unmatched

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Match job employers to companies")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    init_db()
    stats = match_all_unmatched()

    print(f"\nMatching results:")
    print(f"  Matched: {stats['matched']}")
    print(f"  Unmatched: {stats['unmatched']}")
    if stats["new_employers"]:
        print(f"  Top unmatched employers:")
        for name in stats["new_employers"][:20]:
            print(f"    - {name}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/emiltrausti/launatrausti && pytest tests/test_jobs.py -v -k "company_name or match_company"`

- [ ] **Step 6: Commit**

```bash
cd /home/emiltrausti/launatrausti
git add src/company_matcher.py scripts/match_companies.py tests/test_jobs.py
git commit -m "feat: add company matcher — exact, normalized, accent-stripped matching"
```

---

## Task 6: Salary Estimation Engine

**Files:**
- Create: `src/salary_engine.py`
- Create: `scripts/estimate_salaries.py`
- Test: `tests/test_jobs.py`

- [ ] **Step 1: Write failing tests for salary estimation**

Append to `tests/test_jobs.py`:
```python
def test_estimate_salary_from_job_text(test_db):
    """Salary from job listing text takes highest priority."""
    from src.salary_engine import estimate_job_salary

    with patch.object(db, "DB_PATH", test_db):
        job = {"salary_lower": 750000, "salary_upper": 900000, "company_id": None, "title": "Dev"}
        result = estimate_job_salary(job)
        assert result["estimate"] == 825000  # midpoint
        assert result["source"] == "job_listing"


def test_estimate_salary_from_company(test_db, sample_reports):
    """Company avg salary is used when job has no salary text."""
    from src.salary_engine import estimate_job_salary

    with patch.object(db, "DB_PATH", test_db):
        job = {"salary_lower": None, "salary_upper": None, "company_id": sample_reports, "title": "Dev"}
        result = estimate_job_salary(job)
        assert result["estimate"] > 0
        assert result["source"] == "company_avg"


def test_estimate_salary_no_data(test_db):
    """Returns None when no salary data is available."""
    from src.salary_engine import estimate_job_salary

    with patch.object(db, "DB_PATH", test_db):
        job = {"salary_lower": None, "salary_upper": None, "company_id": None, "title": "Random Unknown Job"}
        result = estimate_job_salary(job)
        assert result["estimate"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/emiltrausti/launatrausti && pytest tests/test_jobs.py -v -k "estimate_salary"`

- [ ] **Step 3: Create src/salary_engine.py**

```python
"""
Salary estimation engine for job listings.

Computes estimated salary from multiple sources, prioritized:
1. Job listing text (if salary numbers found)
2. Company financials (avg_salary from annual reports)
3. VR kjarakannanir (occupation-specific, matched by title)
4. Hagstofa industry average (by company's ISAT code)
"""

import logging
import re
import unicodedata
from typing import Optional

from .database import get_connection

logger = logging.getLogger(__name__)

# Icelandic stop words for title matching
STOP_WORDS = {"og", "i", "a", "vid", "fyrir", "med", "um", "til", "fra", "sem", "er", "ad", "the", "and", "or", "of", "in", "at", "for", "with"}


def _normalize_title(title: str) -> set[str]:
    """Normalize a job title to a set of tokens for matching."""
    text = title.lower().strip()
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r'[^\w\s]', '', text)
    tokens = set(text.split())
    return tokens - STOP_WORDS


def _jaccard(a: set, b: set) -> float:
    """Jaccard similarity between two sets."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def estimate_job_salary(job: dict) -> dict:
    """Estimate salary for a job listing from available data.

    Args:
        job: dict with keys from job_listings table

    Returns:
        {estimate: int|None, source: str|None, confidence: float, details: str}
    """
    # Priority 1: Job listing itself
    lower = job.get("salary_lower")
    upper = job.get("salary_upper")
    if lower:
        estimate = (lower + (upper or lower)) // 2
        return {
            "estimate": estimate,
            "source": "job_listing",
            "confidence": 0.9,
            "details": f"from job listing ({lower:,}-{(upper or lower):,} kr/mo)",
        }

    conn = get_connection()
    cursor = conn.cursor()

    # Priority 2: Company financials
    company_id = job.get("company_id")
    if company_id:
        cursor.execute("""
            SELECT avg_salary, year FROM annual_reports
            WHERE company_id = ?
            ORDER BY year DESC LIMIT 1
        """, (company_id,))
        row = cursor.fetchone()
        if row and row["avg_salary"]:
            monthly = row["avg_salary"] // 12
            conn.close()
            return {
                "estimate": monthly,
                "source": "company_avg",
                "confidence": 0.7,
                "details": f"company avg ({row['year']})",
            }

    # Priority 3: VR survey (title matching)
    title = job.get("title", "")
    if title:
        title_tokens = _normalize_title(title)
        if title_tokens:
            cursor.execute("""
                SELECT starfsheiti, medaltal FROM vr_salary_surveys
                WHERE survey_date = (SELECT MAX(survey_date) FROM vr_salary_surveys)
            """)
            best_match = None
            best_score = 0.0
            for vr_row in cursor.fetchall():
                vr_tokens = _normalize_title(vr_row["starfsheiti"])
                score = _jaccard(title_tokens, vr_tokens)
                if score > best_score:
                    best_score = score
                    best_match = vr_row

            if best_match and best_score >= 0.4:
                conn.close()
                return {
                    "estimate": best_match["medaltal"],
                    "source": "vr_survey",
                    "confidence": round(min(best_score, 0.8), 2),
                    "details": f"VR: {best_match['starfsheiti']}",
                }

    # Priority 4: Hagstofa industry average (if company has ISAT code)
    if company_id:
        cursor.execute("""
            SELECT c.isat_code FROM companies c WHERE c.id = ?
        """, (company_id,))
        company_row = cursor.fetchone()
        if company_row and company_row["isat_code"]:
            # Import hagstofa inline to avoid circular imports
            from . import hagstofa
            isat = company_row["isat_code"]
            # Try current year, then previous
            for year in [2024, 2023]:
                benchmark = hagstofa.get_industry_benchmark(isat, year)
                if benchmark:
                    conn.close()
                    return {
                        "estimate": benchmark.monthly_wage,
                        "source": "hagstofa",
                        "confidence": 0.4,
                        "details": f"industry avg ({benchmark.industry_name}, {year})",
                    }

    conn.close()
    return {
        "estimate": None,
        "source": None,
        "confidence": 0.0,
        "details": "no salary data available",
    }


def estimate_all_jobs() -> int:
    """Pre-compute salary estimates for all active jobs. Returns count updated."""
    from .database import get_jobs_needing_salary_estimate

    jobs = get_jobs_needing_salary_estimate()
    logger.info("Computing salary estimates for %d jobs", len(jobs))

    conn = get_connection()
    cursor = conn.cursor()
    updated = 0

    for job in jobs:
        result = estimate_job_salary(job)
        if result["estimate"]:
            cursor.execute("""
                UPDATE job_listings SET
                    estimated_salary = ?,
                    salary_source = ?,
                    salary_confidence = ?,
                    salary_details = ?
                WHERE id = ?
            """, (result["estimate"], result["source"], result["confidence"],
                  result["details"], job["id"]))
            updated += 1

    conn.commit()
    conn.close()
    logger.info("Updated salary estimates for %d jobs", updated)
    return updated
```

- [ ] **Step 4: Create scripts/estimate_salaries.py**

```python
#!/usr/bin/env python3
"""
Pre-compute salary estimates for all active job listings.

Usage:
    python scripts/estimate_salaries.py
    python scripts/estimate_salaries.py --verbose
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import init_db
from src.salary_engine import estimate_all_jobs

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Estimate salaries for job listings")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    init_db()
    updated = estimate_all_jobs()
    print(f"\nUpdated salary estimates for {updated} jobs")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/emiltrausti/launatrausti && pytest tests/test_jobs.py -v -k "estimate_salary"`

- [ ] **Step 6: Commit**

```bash
cd /home/emiltrausti/launatrausti
git add src/salary_engine.py scripts/estimate_salaries.py tests/test_jobs.py
git commit -m "feat: add salary estimation engine — 4-source priority with VR title matching"
```

---

## Task 7: Pipeline Integration

**Files:**
- Modify: `scripts/run_pipeline.py`

- [ ] **Step 1: Add stages 8-11 to run_pipeline.py**

Update `TOTAL_STAGES = 11` and add the 4 new stage functions following the existing pattern. Add new stage functions `run_stage_8` through `run_stage_11`, each calling the respective script via `run_script()`. Update `stage_functions` dict and CLI epilog.

Key changes:
- `TOTAL_STAGES = 11`
- Stage 8: `scripts/scrape_jobs.py`
- Stage 9: `scripts/extract_jobs.py`
- Stage 10: `scripts/match_companies.py`
- Stage 11: `scripts/estimate_salaries.py`
- Add `--skip-jobs` CLI flag to skip stages 8-11

- [ ] **Step 2: Run pipeline stage 8 dry-run to verify**

Run: `cd /home/emiltrausti/launatrausti && python scripts/run_pipeline.py --stage 8 --dry-run`
Expected: Prints banner, runs scrape_jobs.py --dry-run without error

- [ ] **Step 3: Commit**

```bash
cd /home/emiltrausti/launatrausti
git add scripts/run_pipeline.py
git commit -m "feat: add pipeline stages 8-11 for job scraping, extraction, matching, salary estimation"
```

---

## Task 8: UI — `/jobs` Page

**Files:**
- Create: `src/templates/jobs.html`
- Modify: `src/main.py`
- Modify: `src/templates/base.html`
- Test: `tests/test_jobs.py`

- [ ] **Step 1: Write failing test for /jobs route**

Append to `tests/test_jobs.py`:
```python
from httpx import AsyncClient, ASGITransport
import pytest


@pytest.mark.anyio
async def test_jobs_page_loads(test_db):
    """GET /jobs should return 200."""
    with patch.object(db, "DB_PATH", test_db):
        from src.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/jobs")
            assert resp.status_code == 200
            assert "Storf" in resp.text or "Jobs" in resp.text


@pytest.mark.anyio
async def test_api_jobs(test_db):
    """GET /api/jobs should return JSON with jobs list."""
    with patch.object(db, "DB_PATH", test_db):
        from src.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/jobs")
            assert resp.status_code == 200
            data = resp.json()
            assert "jobs" in data
```

- [ ] **Step 2: Add "Storf" nav link to base.html**

Find the `<nav>` element in `src/templates/base.html` and add a link for "Storf" alongside the existing nav items.

- [ ] **Step 3: Add routes to main.py**

Add `/jobs` HTML route and `/api/jobs` JSON route to `src/main.py`, following the existing pattern with `templates.TemplateResponse` and optional query params.

- [ ] **Step 4: Create jobs.html template**

Create `src/templates/jobs.html` extending `base.html`, using the existing Lumon design system classes (`.content-with-sidebar`, `.filter-sidebar`, `.card`, `.stat-card`, `.salary`, `.badge`). Include:
- Stats bar (active jobs, with salary estimate, sources)
- Filter sidebar (salary min/max, location, employment type, remote, source)
- Job card grid with: title, employer, estimated salary, location, employment type, benefits badges, deadline
- Pagination
- Empty state

- [ ] **Step 5: Run tests to verify routes work**

Run: `cd /home/emiltrausti/launatrausti && pytest tests/test_jobs.py -v -k "jobs_page or api_jobs"`

- [ ] **Step 6: Visually verify the page**

Run: `cd /home/emiltrausti/launatrausti && timeout 5 uvicorn src.main:app --port 8080 || true`
Then fetch: `curl -s http://localhost:8080/jobs | head -50`

- [ ] **Step 7: Commit**

```bash
cd /home/emiltrausti/launatrausti
git add src/templates/jobs.html src/templates/base.html src/main.py tests/test_jobs.py
git commit -m "feat: add /jobs page — salary-enriched job search with filters"
```

---

## Task 9: Company Page Job Section

**Files:**
- Modify: `src/templates/company.html`
- Modify: `src/main.py`

- [ ] **Step 1: Add jobs to company detail context**

In `src/main.py`, inside the `company_detail` route, add a call to `database.get_company_jobs(company_id)` and pass the result as `jobs` in the template context.

- [ ] **Step 2: Add "Laus storf" section to company.html**

Read `src/templates/company.html`, find an appropriate location (after the reports/benchmarks section), and add a new card section:
- Title: "Laus storf" (Open Positions)
- Lists active job listings for this company
- Each job shows: title, estimated salary, employment type, deadline, link to source
- Empty state: "Engin laus storf skrad" (No open positions listed)

- [ ] **Step 3: Commit**

```bash
cd /home/emiltrausti/launatrausti
git add src/main.py src/templates/company.html
git commit -m "feat: show open job listings on company detail pages"
```

---

## Task 10: GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/data-pipeline.yml`

- [ ] **Step 1: Create the workflow file**

```yaml
name: Data Pipeline

on:
  schedule:
    - cron: '0 6 * * *'  # Daily at 06:00 UTC
  workflow_dispatch: {}   # Manual trigger

jobs:
  pipeline:
    runs-on: ubuntu-latest
    timeout-minutes: 60

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install httpx>=0.27.0 playwright
          playwright install chromium --with-deps

      - name: Run job scrapers (stages 8-11)
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          SKATTURINN_API_KEY: ${{ secrets.SKATTURINN_API_KEY }}
        run: |
          python scripts/scrape_jobs.py
          python scripts/extract_jobs.py
          python scripts/match_companies.py
          python scripts/estimate_salaries.py

      - name: Run financial pipeline (stages 1-7)
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          SKATTURINN_API_KEY: ${{ secrets.SKATTURINN_API_KEY }}
        run: python scripts/run_pipeline.py --skip-scrape

      - name: Print stats
        run: python scripts/run_pipeline.py --stage 7

      - name: Commit database changes
        run: |
          git config user.name "Launatrausti Bot"
          git config user.email "bot@launatrausti.is"
          git add launatrausti.db
          git diff --cached --quiet || git commit -m "data: daily pipeline update $(date +%Y-%m-%d)"
          git push
```

- [ ] **Step 2: Commit**

```bash
cd /home/emiltrausti/launatrausti
mkdir -p .github/workflows
git add .github/workflows/data-pipeline.yml
git commit -m "ci: add daily data pipeline workflow — scrape, extract, match, deploy"
```

---

## Task 11: Integration Test + Final Verification

**Files:**
- Modify: `tests/conftest.py`
- Test: all tests

- [ ] **Step 1: Add sample_jobs fixture to conftest.py**

```python
@pytest.fixture
def sample_jobs(test_db, sample_company):
    """Insert sample job listings."""
    with patch.object(db, "DB_PATH", test_db):
        for i, (title, salary, source) in enumerate([
            ("Software Developer", 800000, "alfred"),
            ("Project Manager", 700000, "alfred"),
            ("Government Analyst", 650000, "starfatorg"),
        ]):
            listing = db.JobListing(
                id=None, source=source, source_id=f"test-{i}",
                title=title, employer_name="Test Company ehf.",
                company_id=sample_company, location="Reykjavik",
                location_lat=None, location_lon=None,
                employment_type="full-time", description_raw=f"Job description for {title}",
                source_url=None, posted_date="2026-03-01", deadline="2026-06-01",
                work_hours=None, remote_policy=None, salary_text=None,
                salary_lower=None, salary_upper=None, benefits=None,
                union_name=None, languages=None, education_required=None,
                experience_years=None, estimated_salary=salary,
                salary_source="test", salary_confidence=0.8,
                salary_details="test data", extracted_at=None, is_active=True,
            )
            db.save_job_listing(listing)
        return sample_company
```

- [ ] **Step 2: Run full test suite**

Run: `cd /home/emiltrausti/launatrausti && pytest -v`
Expected: ALL PASS

- [ ] **Step 3: Start the app and verify pages load**

Run: `cd /home/emiltrausti/launatrausti && uvicorn src.main:app --port 8080 &`
Then check: `curl -s http://localhost:8080/jobs | grep -c "Storf"` (should be > 0)
And: `curl -s http://localhost:8080/api/jobs | python3 -c "import sys,json; d=json.load(sys.stdin); print('jobs' in d)"`
Kill: `kill %1`

- [ ] **Step 4: Final commit**

```bash
cd /home/emiltrausti/launatrausti
git add tests/conftest.py
git commit -m "test: add sample_jobs fixture and integration tests"
```

---

## Verification Checklist

After all tasks complete, verify:

1. `pytest -v` — all tests pass
2. `uvicorn src.main:app --port 8080` — app starts
3. `GET /jobs` — page renders with Lumon design
4. `GET /api/jobs` — returns JSON
5. `python scripts/scrape_jobs.py --dry-run` — no errors
6. `python scripts/run_pipeline.py --stage 8 --dry-run` — pipeline stage works
7. Company detail pages show "Laus storf" section
8. Nav bar includes "Storf" link
