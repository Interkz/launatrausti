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
STOP_WORDS = {
    "og", "i", "a", "vid", "fyrir", "med", "um", "til", "fra",
    "sem", "er", "ad", "the", "and", "or", "of", "in", "at", "for", "with",
}


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
        cursor.execute(
            "SELECT isat_code FROM companies WHERE id = ?",
            (company_id,),
        )
        company_row = cursor.fetchone()
        if company_row and company_row["isat_code"]:
            from . import hagstofa
            isat = company_row["isat_code"]
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
    """Pre-compute salary estimates for all active jobs needing one. Returns count updated."""
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
