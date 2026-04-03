"""
Extract SSF (financial sector) salary data from launareiknivel.is.

Uses the WordPress AJAX endpoint to fetch salary distributions for each job title.
The data is from SSF's annual kjarakönnun (salary survey).

Data: ~60 financial sector job titles with full salary distributions.
Source: https://www.launareiknivel.is/
Legal: No TOS, no robots.txt restrictions on data pages (checked 2026-04-03).

Usage:
    python scripts/parse_ssf_surveys.py
    python scripts/parse_ssf_surveys.py --year 2025
    python scripts/parse_ssf_surveys.py --dry-run
"""

import sys
import os
import argparse
import time
import re
import statistics

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src import database
from src.database import VRSalarySurvey
from datetime import datetime

SITE_URL = "https://www.launareiknivel.is/"
AJAX_URL = "https://www.launareiknivel.is/wp-admin/admin-ajax.php"


def get_job_titles() -> list[tuple[str, str]]:
    """Fetch the page and extract all job title options."""
    resp = requests.get(SITE_URL, timeout=30)
    resp.raise_for_status()
    html = resp.text

    job_select = re.search(r"<select[^>]*name='job'[^>]*>(.*?)</select>", html, re.DOTALL)
    if not job_select:
        raise ValueError("Could not find job select element on page")

    pattern = r"<option value='([^']+)'[^>]*>\s*([^<]+?)\s*</option>"
    options = re.findall(pattern, job_select.group(1))
    return [(slug, name.strip()) for slug, name in options if slug and slug != '-1']


def fetch_salary_data(job_slug: str, year: str = "2025") -> dict:
    """Fetch salary distribution for a job title from the AJAX endpoint."""
    data = (
        f"job={job_slug}&year={year}&education=-1&experience=-1"
        f"&management=-1&compare_years=false&action=docalculation"
    )
    resp = requests.post(
        AJAX_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def parse_salary_string(s: str) -> int | None:
    """Parse '907.265 kr.' or '1.145.134 kr.' to integer ISK."""
    if not s:
        return None
    cleaned = re.sub(r'[^\d]', '', s.replace('.', ''))
    if not cleaned:
        return None
    # The format uses dots as thousand separators but the values
    # on launareiknivel.is are displayed in thousands with dot separator
    # e.g. "907.265 kr." means 907,265 ISK
    # But we need to check: the raw alldata array has values like 600000
    # So "907.265 kr." = 907265 ISK (dots are thousand separators)
    return int(cleaned) if cleaned else None


def compute_percentiles(data: list[int]) -> dict:
    """Compute salary statistics from raw distribution."""
    if not data or len(data) < 3:
        return {}
    sorted_data = sorted(data)
    n = len(sorted_data)
    return {
        "medaltal": round(statistics.mean(sorted_data)),
        "midgildi": round(statistics.median(sorted_data)),
        "p25": sorted_data[max(0, n // 4 - 1)],
        "p75": sorted_data[min(n - 1, 3 * n // 4)],
        "fjoldi": n,
    }


def main():
    parser = argparse.ArgumentParser(description="Extract SSF financial sector salary data")
    parser.add_argument("--year", type=str, default="2025", help="Survey year (default: 2025)")
    parser.add_argument("--dry-run", action="store_true", help="Print data without saving")
    args = parser.parse_args()

    print(f"Fetching SSF salary data for {args.year}")
    print(f"Source: {SITE_URL}")

    # Get job titles
    jobs = get_job_titles()
    print(f"Found {len(jobs)} job titles\n")

    saved = 0
    skipped = 0

    for i, (slug, name) in enumerate(jobs):
        print(f"  [{i+1}/{len(jobs)}] {name}...", end=" ", flush=True)

        try:
            result = fetch_salary_data(slug, args.year)
        except Exception as e:
            print(f"ERROR: {e}")
            continue

        if result.get("error_code") == "less10":
            print("SKIP (fewer than 10 responses)")
            skipped += 1
            continue

        alldata = result.get("alldata", [])
        if not alldata:
            print("SKIP (no data)")
            skipped += 1
            continue

        stats = compute_percentiles(alldata)
        if not stats:
            print("SKIP (insufficient data)")
            skipped += 1
            continue

        avg_str = result.get("avg", "")
        median_str = result.get("median", "")
        avg_from_api = parse_salary_string(avg_str)
        median_from_api = parse_salary_string(median_str)

        # Prefer API-reported avg/median over computed
        medaltal = avg_from_api or stats["medaltal"]
        midgildi = median_from_api or stats["midgildi"]

        print(f"OK — avg {medaltal:,} / median {midgildi:,} / n={stats['fjoldi']}")

        if args.dry_run:
            continue

        # Save to vr_salary_surveys table (same schema, different source)
        survey_date = f"{args.year}-SSF"
        survey = VRSalarySurvey(
            id=None,
            survey_date=survey_date,
            starfsheiti=name,
            starfsstett="Fjármálageirinn",
            medaltal=medaltal,
            midgildi=midgildi,
            p25=stats["p25"],
            p75=stats["p75"],
            fjoldi_svara=stats["fjoldi"],
            source_pdf="ssf_launareiknivel",
            extracted_at=datetime.now(),
        )
        database.save_vr_survey(survey)
        saved += 1

        # Be polite — 1 second between requests
        time.sleep(1)

    print(f"\nDone! Saved: {saved}, Skipped: {skipped}")

    if not args.dry_run:
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM vr_salary_surveys WHERE source_pdf = 'ssf_launareiknivel'"
        )
        total = cursor.fetchone()["cnt"]
        conn.close()
        print(f"Total SSF records in database: {total}")


if __name__ == "__main__":
    main()
