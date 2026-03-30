"""
Company name matching for job listings.

Matches employer names from job listings to companies in the database.
Strategy: exact match -> normalized match -> accent-stripped match.
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

    Strips legal suffixes, lowercases, removes punctuation, collapses whitespace.
    """
    name = name.strip()
    name = LEGAL_SUFFIXES.sub('', name).strip()
    name = name.lower()
    name = re.sub(r'[^\w\s]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def _strip_accents(text: str) -> str:
    """Remove accents/diacritics from text."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def match_employer_to_company(employer_name: str) -> Optional[int]:
    """Try to match an employer name to a company in the database.

    Returns company_id if found, None otherwise.
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

    # Strategy 2: Normalized match (strip legal suffixes)
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

    # Strategy 4: Containment match (one name contains the other)
    # Handles "Reykjavíkurborg - Velferðarsvið" -> "Reykjavíkurborg"
    if len(normalized) >= 5:
        cursor.execute("SELECT id, name FROM companies")
        best_id = None
        best_len = 0
        for company_row in cursor.fetchall():
            cn = normalize_company_name(company_row["name"])
            cn_ascii = _strip_accents(cn)
            # Check if company name is contained in employer name or vice versa
            if len(cn) >= 5 and (cn in normalized_ascii or normalized_ascii in cn_ascii):
                if len(cn) > best_len:
                    best_len = len(cn)
                    best_id = company_row["id"]
        if best_id:
            conn.close()
            return best_id

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
            logger.debug("Matched '%s' -> company_id=%d (%d jobs)",
                         employer_name, company_id, len(job_ids))
        else:
            unmatched_employers.append(employer_name)

    conn.commit()
    conn.close()

    logger.info("Matching complete: %d matched, %d unmatched employers",
                matched, len(unmatched_employers))

    return {
        "matched": matched,
        "unmatched": len(jobs) - matched,
        "new_employers": unmatched_employers[:50],
    }
