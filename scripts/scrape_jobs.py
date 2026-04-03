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
ALFRED_BASE_URL = "https://alfred.is"
STARFATORG_URL = "https://island.is/api/graphql"


# ---------------------------------------------------------------------------
# Alfred.is
# ---------------------------------------------------------------------------


def parse_alfred_job(raw: dict) -> JobListing:
    """Convert an Alfred public page job object to a JobListing.

    Uses Next.js data route fields: id, slug, title, brand{name, slug, logo},
    employmentType (list), addresses[{formatted, lat, lon}], deadline, published.
    We store only minimal metadata + link back — no full descriptions (legal).
    """
    brand = raw.get("brand") or {}
    job_id = str(raw.get("id", ""))

    # Employment type: list of strings like ["FULL_TIME"]
    emp_types = raw.get("employmentType") or raw.get("jobTypes") or []
    if isinstance(emp_types, list) and emp_types:
        emp_type = str(emp_types[0])
    elif isinstance(emp_types, str):
        emp_type = emp_types
    else:
        emp_type = None

    # Location from addresses array
    addresses = raw.get("addresses") or []
    location_name = None
    location_lat = None
    location_lon = None
    if addresses and isinstance(addresses, list) and isinstance(addresses[0], dict):
        addr = addresses[0]
        location_name = addr.get("formatted") or addr.get("streetName")
        location_lat = addr.get("lat")
        location_lon = addr.get("lon") or addr.get("lng")

    # Source URL — always link back to Alfred
    job_slug = raw.get("slug", "")
    source_url = f"https://alfred.is/starf/{job_slug}" if job_slug else f"https://alfred.is/starf/{job_id}"

    # Employer logo from brand
    employer_logo = brand.get("logo") or None

    # Dates
    deadline_raw = raw.get("deadline") or raw.get("applicationDeadline")
    deadline = deadline_raw[:10] if deadline_raw else None

    created_raw = raw.get("published") or raw.get("created")
    posted_date = created_raw[:10] if created_raw else None

    # Minimal description only — do NOT store full bodyhtml/description
    # Just store a short summary for search purposes
    desc = raw.get("description") or ""
    short_desc = desc[:200] if desc else ""

    return JobListing(
        id=None,
        source="alfred",
        source_id=job_id,
        title=raw.get("title", ""),
        employer_name=brand.get("name", "Unknown"),
        location=location_name,
        location_lat=location_lat,
        location_lon=location_lon,
        employment_type=emp_type,
        description_raw=short_desc,
        source_url=source_url,
        posted_date=posted_date,
        deadline=deadline,
        salary_text=None,
        employer_logo=employer_logo,
        is_active=True,
    )


def _get_alfred_build_id(client: httpx.Client) -> str:
    """Fetch Alfred.is main page and extract the Next.js buildId."""
    resp = client.get(f"{ALFRED_BASE_URL}/storf")
    resp.raise_for_status()
    import re
    # Look for buildId in __NEXT_DATA__ JSON
    match = re.search(r'"buildId"\s*:\s*"([^"]+)"', resp.text)
    if match:
        return match.group(1)
    raise RuntimeError("Could not find Alfred.is Next.js buildId")


def scrape_alfred(dry_run: bool = False) -> list[str]:
    """Scrape Alfred.is job listings.

    Uses userapi.alfred.is (separate subdomain, no robots.txt) for full pagination.
    Falls back to Next.js data route if the API is unreachable.
    Stores only minimal metadata — no full descriptions (legal risk mitigation).
    Always links back to alfred.is/starf/{slug}.

    Returns a list of source_ids for all jobs seen (used to deactivate stale entries).
    """
    source_ids: list[str] = []
    page = 1
    page_size = 100

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        while True:
            log.info("Alfred: fetching page %d (size=%d)", page, page_size)
            try:
                resp = client.get(
                    ALFRED_API_URL,
                    params={"page": page, "size": page_size, "translate": "false"},
                )
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, Exception) as e:
                # Fallback to Next.js data route (only gets first 27 jobs)
                log.warning("Alfred API failed (%s), trying Next.js fallback", e)
                try:
                    build_id = _get_alfred_build_id(client)
                    resp = client.get(
                        f"{ALFRED_BASE_URL}/_next/data/{build_id}/jobs.json",
                    )
                    resp.raise_for_status()
                    fallback_data = resp.json()
                    data = fallback_data.get("pageProps", {}).get("jobs", {}).get("jobs", [])
                    # Wrap in list format for uniform processing
                    if isinstance(data, list):
                        for raw in data:
                            listing = parse_alfred_job(raw)
                            source_ids.append(listing.source_id)
                            if not dry_run:
                                save_job_listing(listing)
                    log.info("Alfred: fallback yielded %d jobs", len(data) if isinstance(data, list) else 0)
                except Exception as e2:
                    log.error("Alfred: both API and fallback failed: %s", e2)
                break

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
            time.sleep(1.5)  # Be respectful

    log.info("Alfred: total %d jobs scraped", len(source_ids))
    return source_ids


# ---------------------------------------------------------------------------
# Island.is Starfatorg (GraphQL)
# ---------------------------------------------------------------------------

STARFATORG_LIST_QUERY = """
{
  icelandicGovernmentInstitutionVacancies(input: {}) {
    vacancies {
      id
      title
      institutionName
      applicationDeadlineFrom
      applicationDeadlineTo
      intro
    }
  }
}
"""

STARFATORG_DETAIL_QUERY = """
query GetVacancy($id: String!) {
  icelandicGovernmentInstitutionVacancyById(id: $id) {
    id
    title
    institutionName
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

    vacancies = (
        (data.get("data") or {})
        .get("icelandicGovernmentInstitutionVacancies", {})
        .get("vacancies", [])
    )
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
            detail = (detail_data.get("data") or {}).get("icelandicGovernmentInstitutionVacancyById")
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
# Tvinna.is (RSS feed — tech jobs)
# ---------------------------------------------------------------------------

TVINNA_RSS_URL = "https://tvinna.is/feed/"


def parse_tvinna_job(entry: dict) -> JobListing:
    """Convert a Tvinna RSS entry to a JobListing."""
    title = entry.get("title", "")
    link = entry.get("link", "")
    description = entry.get("content_encoded") or entry.get("description") or ""
    pub_date_raw = entry.get("pubDate") or entry.get("published") or ""

    # Try to extract employer from content (usually mentioned in first paragraph)
    employer = "Unknown"
    if description:
        # Common patterns: "at CompanyName", "hjá CompanyName", "Company is hiring"
        import re
        # Look for "Company — " at start or similar
        for pattern in [
            r'(?:at|hjá|@)\s+([A-Z][A-Za-z\s&.]+?)(?:\s+(?:is|er|we))',
            r'^<p>([A-Z][A-Za-z\s&.]+?)\s+(?:is|are|er)',
        ]:
            m = re.search(pattern, description)
            if m:
                employer = m.group(1).strip()
                break

    # Extract source_id from URL
    source_id = link.split("/")[-2] if link.endswith("/") else link.split("/")[-1]

    # Parse date
    posted_date = None
    if pub_date_raw:
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(pub_date_raw)
            posted_date = dt.strftime("%Y-%m-%d")
        except Exception:
            pass

    return JobListing(
        id=None,
        source="tvinna",
        source_id=source_id,
        title=title,
        employer_name=employer,
        description_raw=description[:5000] if description else None,
        source_url=link,
        posted_date=posted_date,
        is_active=True,
    )


def scrape_tvinna(dry_run: bool = False) -> list[str]:
    """Scrape job listings from Tvinna.is RSS feed.
    Returns a list of source_ids for all jobs seen."""
    import xml.etree.ElementTree as ET

    source_ids: list[str] = []

    log.info("Tvinna: fetching RSS feed")
    try:
        resp = requests.get(TVINNA_RSS_URL, timeout=30)
        resp.raise_for_status()
    except Exception:
        log.error("Tvinna: failed to fetch RSS feed", exc_info=True)
        return source_ids

    root = ET.fromstring(resp.content)
    channel = root.find("channel")
    if channel is None:
        log.warning("Tvinna: no channel found in RSS")
        return source_ids

    items = channel.findall("item")
    log.info("Tvinna: found %d items", len(items))

    # Namespace for content:encoded
    ns = {"content": "http://purl.org/rss/1.0/modules/content/"}

    for item in items:
        entry = {
            "title": (item.findtext("title") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "description": (item.findtext("description") or "").strip(),
            "content_encoded": (item.findtext("content:encoded", namespaces=ns) or "").strip(),
            "pubDate": (item.findtext("pubDate") or "").strip(),
        }

        listing = parse_tvinna_job(entry)
        source_ids.append(listing.source_id)

        if dry_run:
            log.info("  [dry-run] %s @ %s", listing.title, listing.employer_name)
        else:
            save_job_listing(listing)
            log.debug("  saved: %s @ %s", listing.title, listing.employer_name)

    log.info("Tvinna: total %d jobs scraped", len(source_ids))
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
        choices=["alfred", "starfatorg", "tvinna", "all"],
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
        [args.source] if args.source != "all" else ["alfred", "starfatorg", "tvinna"]
    )

    for source in sources_to_scrape:
        try:
            if source == "alfred":
                active_ids = scrape_alfred(dry_run=args.dry_run)
            elif source == "starfatorg":
                active_ids = scrape_starfatorg(dry_run=args.dry_run)
            elif source == "tvinna":
                active_ids = scrape_tvinna(dry_run=args.dry_run)
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
