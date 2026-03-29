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
            logger.debug("Skipping job %s: description too short", job.get("source_id"))
            continue

        if dry_run:
            logger.info("[DRY RUN] Would extract: %s — %s",
                        job.get("source_id"), job.get("title", "")[:50])
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
            logger.error("Failed to extract job %s: %s", job.get("source_id"), e)

        time.sleep(RATE_LIMIT)

    if conn:
        conn.close()

    logger.info("Extraction complete: %d processed out of %d", processed, len(jobs))
    return processed


def main():
    parser = argparse.ArgumentParser(
        description="Extract structured fields from job listings via Claude API"
    )
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
