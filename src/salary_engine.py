"""
Salary estimation engine for job listings.

Computes estimated salary from multiple sources using a blended model:

1. Job listing text (if salary numbers found) — highest confidence
2. Blended estimate: company_factor * occupation_median
   - company_factor = company_avg / national_avg (how much this company pays vs Iceland)
   - occupation_median from VR surveys or Hagstofa occupations
3. Company financials alone (avg_salary from annual reports)
4. VR kjarakannanir (occupation-specific, matched by title)
5. Hagstofa occupation data (269 occupations)
6. Hagstofa industry average (by company's ISAT code)
7. National average (last resort)
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
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _containment(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _substring_match(title: str, other: str) -> bool:
    a = unicodedata.normalize('NFKD', title.lower())
    a = ''.join(c for c in a if not unicodedata.combining(c))
    b = unicodedata.normalize('NFKD', other.lower())
    b = ''.join(c for c in b if not unicodedata.combining(c))
    return b in a or a in b


def _best_title_match(title: str, rows: list, name_key: str, score_threshold: float = 0.35) -> tuple:
    """Find best matching row by title. Returns (row, score) or (None, 0)."""
    title_tokens = _normalize_title(title)
    if not title_tokens:
        return None, 0.0

    best_row = None
    best_score = 0.0

    for row in rows:
        row_tokens = _normalize_title(row[name_key])
        # Jaccard
        score = _jaccard(title_tokens, row_tokens)
        if score > best_score:
            best_score = score
            best_row = row
        # Containment (discounted)
        c = _containment(title_tokens, row_tokens) * 0.85
        if c > best_score:
            best_score = c
            best_row = row
        # Substring
        if _substring_match(title, row[name_key]) and 0.7 > best_score:
            best_score = 0.7
            best_row = row

    if best_score >= score_threshold:
        return best_row, best_score
    return None, 0.0


def _get_occupation_salary(cursor, title: str) -> tuple:
    """Try VR surveys then Hagstofa occupations. Returns (salary, source, details, score)."""
    if not title:
        return None, None, None, 0.0

    # VR surveys
    cursor.execute("""
        SELECT starfsheiti, medaltal FROM vr_salary_surveys
        WHERE survey_date = (SELECT MAX(survey_date) FROM vr_salary_surveys)
    """)
    vr_rows = cursor.fetchall()
    vr_match, vr_score = _best_title_match(title, vr_rows, "starfsheiti")
    if vr_match:
        return vr_match["medaltal"], "vr_survey", f"VR: {vr_match['starfsheiti']}", vr_score

    # Hagstofa occupations
    cursor.execute("""
        SELECT occupation_name, median, mean FROM hagstofa_occupations
        WHERE year = (SELECT MAX(year) FROM hagstofa_occupations)
        AND median IS NOT NULL
    """)
    occ_rows = cursor.fetchall()
    occ_match, occ_score = _best_title_match(title, occ_rows, "occupation_name")
    if occ_match:
        salary = occ_match["median"] or occ_match["mean"]
        return salary, "hagstofa_occupation", f"Hagstofa: {occ_match['occupation_name']}", occ_score

    return None, None, None, 0.0


def _get_company_factor(cursor, company_id: int) -> tuple:
    """Get company pay factor relative to national average.
    Returns (factor, company_monthly, report_year) or (None, None, None)."""
    cursor.execute("""
        SELECT avg_salary, year FROM annual_reports
        WHERE company_id = ? ORDER BY year DESC LIMIT 1
    """, (company_id,))
    row = cursor.fetchone()
    if not row or not row["avg_salary"]:
        return None, None, None

    company_monthly = row["avg_salary"] // 12

    from . import hagstofa
    national = hagstofa.get_national_average(row["year"]) or hagstofa.get_national_average(2024)
    if not national or not national.monthly_wage:
        return None, company_monthly, row["year"]

    factor = company_monthly / national.monthly_wage
    return factor, company_monthly, row["year"]


def estimate_job_salary(job: dict) -> dict:
    """Estimate salary for a job listing using blended model.

    Returns:
        {estimate: int|None, source: str|None, confidence: float, details: str}
    """
    # Priority 1: Job listing itself (explicit salary)
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

    company_id = job.get("company_id")
    title = job.get("title", "")

    # Get both signals
    company_factor, company_monthly, report_year = (None, None, None)
    if company_id:
        company_factor, company_monthly, report_year = _get_company_factor(cursor, company_id)

    occ_salary, occ_source, occ_details, occ_score = _get_occupation_salary(cursor, title)

    # Priority 2: Blended estimate (company_factor * occupation_salary)
    # This is the key innovation — a programmer at a high-paying company
    # should have a higher estimate than at a low-paying one
    if company_factor and occ_salary:
        blended = int(occ_salary * company_factor)
        # Clamp to reasonable range (50%-200% of occupation salary)
        blended = max(int(occ_salary * 0.5), min(blended, int(occ_salary * 2.0)))
        confidence = min(0.85, 0.6 + occ_score * 0.2)
        conn.close()
        return {
            "estimate": blended,
            "source": "blended",
            "confidence": round(confidence, 2),
            "details": f"{occ_details} × company factor {company_factor:.2f} ({report_year})",
        }

    # Priority 3: Company average alone
    if company_monthly:
        conn.close()
        return {
            "estimate": company_monthly,
            "source": "company_avg",
            "confidence": 0.7,
            "details": f"company avg ({report_year})",
        }

    # Priority 4: Occupation salary alone (VR or Hagstofa)
    if occ_salary:
        confidence = round(min(occ_score, 0.8), 2) if occ_source == "vr_survey" else round(min(occ_score * 0.8, 0.6), 2)
        conn.close()
        return {
            "estimate": occ_salary,
            "source": occ_source,
            "confidence": confidence,
            "details": occ_details,
        }

    # Priority 5: Hagstofa industry average (if company has ISAT code)
    if company_id:
        cursor.execute("SELECT isat_code FROM companies WHERE id = ?", (company_id,))
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

    # Priority 6: National average
    from . import hagstofa
    for year in [2024, 2023]:
        national = hagstofa.get_national_average(year)
        if national:
            conn.close()
            return {
                "estimate": national.monthly_wage,
                "source": "national_avg",
                "confidence": 0.2,
                "details": f"national avg ({year})",
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
