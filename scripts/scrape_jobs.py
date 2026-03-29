#!/usr/bin/env python3
"""
Job listing scraper for Launatrausti.

Scrapes job listings from Alfred.is (REST API) and Island.is Starfatorg (GraphQL),
stores them in the job_listings table, and deactivates stale/expired jobs.

Usage:
    # Scrape all sources
    python scripts/scrape_jobs.py

    # Scrape only Alfred.is
    python scripts/scrape_jobs.py --source alfred

    # Scrape only Starfatorg
    python scripts/scrape_jobs.py --source starfatorg

    # Dry run (fetch and parse, but don't save to DB)
    python scripts/scrape_jobs.py --dry-run

    # Verbose logging
    python scripts/scrape_jobs.py --verbose
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
import requests

from src.database import (
    JobListing,
    save_job_listing,
    deactivate_stale_jobs,
    get_job_stats,
    init_db,
)

log = logging.getLogger(__name__)

ALFRED_API_URL = "https://userapi.alfred.is/api/v2/jobs"
STARFATORG_URL = "https://island.is/api/graphql"


# ---------------------------------------------------------------------------
# Alfred.is
# ---------------------------------------------------------------------------


def parse_alfred_job(raw: dict) -> JobListing:
    """Convert an Alfred API job object to a JobListing."""
    brand = raw.get("brand") or {}
    location = raw.get("location") or {}
    emp_type = raw.get("employmentType") or {}

    brand_slug = brand.get("slug", "")
    job_id = str(raw.get("id", ""))

    source_url = f"https://alfred.is/starf/{brand_slug}/{job_id}" if brand_slug else f"https://alfred.is/starf/{job_id}"

    deadline_raw = raw.get("applicationDeadline")
    deadline = deadline_raw[:10] if deadline_raw else None

    created_raw = raw.get("createdAt")
    posted_date = created_raw[:10] if created_raw else None

    return JobListing(
        id=None,
        source="alfred",
        source_id=job_id,
        title=raw.get("title", ""),
        employer_name=brand.get("name", "Unknown"),
        location=location.get("name"),
        location_lat=location.get("latitude"),
        location_lon=location.get("longitude"),
        employment_type=emp_type.get("name"),
        description_raw=raw.get("description"),
        source_url=source_url,
        posted_date=posted_date,
        deadline=deadline,
        salary_text=None,
        is_active=True,
    )


def scrape_alfred(dry_run: bool = False) -> list[str]:
    """Paginate through the Alfred.is jobs API.

    Returns a list of source_ids for all jobs seen (used to deactivate stale entries).
    """
    source_ids: list[str] = []
    page = 1
    page_size = 50

    with httpx.Client(timeout=30) as client:
        while True:
            log.info("Alfred: fetching page %d (size=%d)", page, page_size)
            resp = client.get(
                ALFRED_API_URL,
                params={"page": page, "size": page_size, "translate": "false"},
            )
            resp.raise_for_status()
            data = resp.json()

            # Response may be a list directly or nested under a key
            if isinstance(data, list):
                jobs = data
            elif isinstance(data, dict):
                jobs = data.get("jobs") or data.get("data") or data.get("results") or []
            else:
                jobs = []

            if not jobs:
                log.info("Alfred: page %d returned no jobs, stopping.", page)
                break

            for raw in jobs:
                listing = parse_alfred_job(raw)
                source_ids.append(listing.source_id)
                if dry_run:
                    log.info("  [dry-run] %s @ %s", listing.title, listing.employer_name)
                else:
                    save_job_listing(listing)
                    log.debug("  saved: %s @ %s", listing.title, listing.employer_name)

            log.info("Alfred: page %d yielded %d jobs", page, len(jobs))

            if len(jobs) < page_size:
                break

            page += 1
            time.sleep(1)

    log.info("Alfred: total %d jobs scraped", len(source_ids))
    return source_ids


# ---------------------------------------------------------------------------
# Island.is Starfatorg (GraphQL)
# ---------------------------------------------------------------------------

STARFATORG_LIST_QUERY = """
query GetVacancies {
  starfatorgVacancies {
    id
    title
    institutionName
    locations
    applicationDeadlineFrom
    applicationDeadlineTo
    intro
  }
}
"""

STARFATORG_DETAIL_QUERY = """
query GetVacancy($id: ID!) {
  starfatorgVacancy(id: $id) {
    id
    title
    institutionName
    locations
    applicationDeadlineFrom
    applicationDeadlineTo
    intro
    salaryTerms
    jobPercentage
    qualificationRequirements
    tasksAndResponsibilities
  }
}
"""


def parse_starfatorg_job(raw: dict) -> JobListing:
    """Convert a Starfatorg vacancy object to a JobListing."""
    vacancy_id = str(raw.get("id", ""))
    locations = raw.get("locations") or []
    location_str = ", ".join(locations) if locations else None

    # Build description from available text fields
    parts = []
    for field in ("intro", "tasksAndResponsibilities", "qualificationRequirements", "salaryTerms"):
        val = raw.get(field)
        if val:
            parts.append(val)
    description_raw = "\n\n".join(parts) if parts else None

    # Deadline: prefer applicationDeadlineTo, fall back to applicationDeadlineFrom
    deadline_raw = raw.get("applicationDeadlineTo") or raw.get("applicationDeadlineFrom")
    deadline = deadline_raw[:10] if deadline_raw else None

    posted_raw = raw.get("applicationDeadlineFrom")
    posted_date = posted_raw[:10] if posted_raw else None

    job_percentage = raw.get("jobPercentage")
    work_hours = str(job_percentage) + "%" if job_percentage else None

    return JobListing(
        id=None,
        source="starfatorg",
        source_id=vacancy_id,
        title=raw.get("title", ""),
        employer_name=raw.get("institutionName", "Unknown"),
        location=location_str,
        employment_type=None,
        description_raw=description_raw,
        source_url=f"https://island.is/starfatorg/{vacancy_id}",
        posted_date=posted_date,
        deadline=deadline,
        work_hours=work_hours,
        salary_text=raw.get("salaryTerms"),
        is_active=True,
    )


def scrape_starfatorg(dry_run: bool = False) -> list[str]:
    """Query the Starfatorg GraphQL API for government job vacancies.

    Fetches the full list, then retrieves details per vacancy.
    Returns a list of source_ids for all jobs seen.
    """
    source_ids: list[str] = []
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    # Step 1: list all vacancies
    log.info("Starfatorg: fetching vacancy list")
    resp = session.post(
        STARFATORG_URL,
        json={"query": STARFATORG_LIST_QUERY},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    vacancies = (data.get("data") or {}).get("starfatorgVacancies") or []
    log.info("Starfatorg: found %d vacancies", len(vacancies))

    if not vacancies:
        return source_ids

    # Step 2: fetch detail for each vacancy
    for i, vacancy in enumerate(vacancies):
        vid = vacancy.get("id")
        if not vid:
            continue

        log.info("Starfatorg: fetching detail %d/%d (id=%s)", i + 1, len(vacancies), vid)

        try:
            detail_resp = session.post(
                STARFATORG_URL,
                json={
                    "query": STARFATORG_DETAIL_QUERY,
                    "variables": {"id": vid},
                },
                timeout=30,
            )
            detail_resp.raise_for_status()
            detail_data = detail_resp.json()
            detail = (detail_data.get("data") or {}).get("starfatorgVacancy")
        except Exception:
            log.warning("Starfatorg: failed to fetch detail for %s, using list data", vid, exc_info=True)
            detail = None

        raw = detail if detail else vacancy
        listing = parse_starfatorg_job(raw)
        source_ids.append(listing.source_id)

        if dry_run:
            log.info("  [dry-run] %s @ %s", listing.title, listing.employer_name)
        else:
            save_job_listing(listing)
            log.debug("  saved: %s @ %s", listing.title, listing.employer_name)

        if i < len(vacancies) - 1:
            time.sleep(0.5)

    log.info("Starfatorg: total %d jobs scraped", len(source_ids))
    return source_ids


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Scrape job listings from Alfred.is and Island.is Starfatorg"
    )
    parser.add_argument(
        "--source",
        choices=["alfred", "starfatorg", "all"],
        default="all",
        help="Which source(s) to scrape (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse jobs but don't save to the database",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    if not args.dry_run:
        init_db()

    sources_to_scrape = (
        [args.source] if args.source != "all" else ["alfred", "starfatorg"]
    )

    for source in sources_to_scrape:
        try:
            if source == "alfred":
                active_ids = scrape_alfred(dry_run=args.dry_run)
            elif source == "starfatorg":
                active_ids = scrape_starfatorg(dry_run=args.dry_run)
            else:
                continue

            if not args.dry_run:
                deactivated = deactivate_stale_jobs(source, active_ids)
                if deactivated:
                    log.info("%s: deactivated %d stale jobs", source, deactivated)

        except Exception:
            log.error("Error scraping %s", source, exc_info=True)

    # Print summary stats
    if not args.dry_run:
        stats = get_job_stats()
        print("\n--- Job Stats ---")
        print(f"  Active jobs:       {stats['active_jobs']}")
        print(f"  Matched to company:{stats['matched_jobs']}")
        print(f"  With salary est:   {stats['jobs_with_salary']}")
        print(f"  Sources:           {', '.join(stats.get('sources', []))}")
    else:
        print("\n[dry-run] No data saved.")


if __name__ == "__main__":
    main()
