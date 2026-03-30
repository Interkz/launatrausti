"""
Company name matching for job listings.

Matches employer names from job listings to companies in the database.
Strategies: exact → normalized → accent-stripped → department-stripped →
containment → word overlap.
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

# Department/division suffixes to strip (e.g., "Reykjavíkurborg - Velferðarsvið")
DEPT_SUFFIX = re.compile(r'\s*[-–—]\s+.+$')

# Common prefixes to strip (e.g., "Sumarstörf - Kópavogsbær")
JOB_PREFIXES = re.compile(
    r'^(sumarstörf|sumarstorf|summer\s*jobs?)\s*[-–—]\s*',
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
    """Remove accents/diacritics and normalize Icelandic letters."""
    # Replace Icelandic base letters that don't decompose in Unicode
    text = text.replace('ð', 'd').replace('Ð', 'D')
    text = text.replace('þ', 'th').replace('Þ', 'Th')
    text = text.replace('æ', 'ae').replace('Æ', 'Ae')
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


# Icelandic definite article suffixes (ordered by length for greedy match)
_ARTICLE_SUFFIXES = ['unum', 'anna', 'inum', 'inni', 'inu', 'ins', 'inn', 'ið', 'in', 'id']


def _strip_article(word: str) -> str:
    """Strip Icelandic definite article suffix from a word.
    E.g. 'Ráðuneytið' -> 'Ráðuneyti', 'Stofnunin' -> 'Stofnun'."""
    lower = word.lower()
    for suffix in _ARTICLE_SUFFIXES:
        if lower.endswith(suffix) and len(lower) > len(suffix) + 3:
            return word[:len(word) - len(suffix)]
    return word


def _extract_core_name(employer_name: str) -> str:
    """Extract the core organization name by stripping department suffixes and job prefixes."""
    name = JOB_PREFIXES.sub('', employer_name)
    name = DEPT_SUFFIX.sub('', name)
    return name.strip()


def _significant_words(text: str) -> set[str]:
    """Extract significant words (len >= 4) for overlap matching."""
    return {w for w in text.split() if len(w) >= 4}


def match_employer_to_company(employer_name: str) -> Optional[int]:
    """Try to match an employer name to a company in the database.

    Returns company_id if found, None otherwise.
    Uses 6 strategies with increasing fuzziness.
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

    # Load all companies once for multi-strategy matching
    cursor.execute("SELECT id, name FROM companies")
    all_companies = cursor.fetchall()
    conn.close()

    # Pre-compute normalized forms
    company_norms = []
    for c in all_companies:
        cn = normalize_company_name(c["name"])
        cn_ascii = _strip_accents(cn)
        company_norms.append((c["id"], cn, cn_ascii))

    for cid, cn, cn_ascii in company_norms:
        if cn == normalized:
            return cid

    # Strategy 3: Accent-stripped match
    normalized_ascii = _strip_accents(normalized)
    for cid, cn, cn_ascii in company_norms:
        if cn_ascii == normalized_ascii:
            return cid

    # Strategy 4: Department-stripped match
    # "Reykjavíkurborg - Velferðarsvið" → "Reykjavíkurborg"
    # "Sumarstörf - Kópavogsbær" → "Kópavogsbær"
    core = _extract_core_name(employer_name)
    if core != employer_name:
        core_norm = normalize_company_name(core)
        core_ascii = _strip_accents(core_norm)
        if core_norm:
            for cid, cn, cn_ascii in company_norms:
                if cn == core_norm or cn_ascii == core_ascii:
                    return cid

    # Strategy 4.5: Article-stripped match
    # "Dómsmálaráðuneytið" → "Dómsmálaráðuneyti" (strip -ið)
    words = employer_name.split()
    if words:
        stripped_words = [_strip_article(w) for w in words]
        article_stripped = ' '.join(stripped_words)
        if article_stripped != employer_name:
            as_norm = normalize_company_name(article_stripped)
            as_ascii = _strip_accents(as_norm)
            for cid, cn, cn_ascii in company_norms:
                if cn == as_norm or cn_ascii == as_ascii:
                    return cid
            # Also try containment with article-stripped version
            if len(as_ascii) >= 5:
                for cid, cn, cn_ascii in company_norms:
                    if len(cn_ascii) >= 5 and (cn_ascii in as_ascii or as_ascii in cn_ascii):
                        return cid

    # Strategy 5: Containment match (one name contains the other)
    if len(normalized_ascii) >= 5:
        best_id = None
        best_len = 0
        for cid, cn, cn_ascii in company_norms:
            if len(cn_ascii) >= 5 and (cn_ascii in normalized_ascii or normalized_ascii in cn_ascii):
                if len(cn_ascii) > best_len:
                    best_len = len(cn_ascii)
                    best_id = cid
        if best_id:
            return best_id

    # Strategy 6: Word overlap (for government institutions with inflected names)
    # "Heilsugæsla höfuðborgarsvæðisins" vs "Heilsugæsla á höfuðborgarsvæðinu"
    emp_words = _significant_words(normalized_ascii)
    if len(emp_words) >= 2:
        best_id = None
        best_overlap = 0
        for cid, cn, cn_ascii in company_norms:
            co_words = _significant_words(cn_ascii)
            if len(co_words) < 2:
                continue
            # Count words that share a common root (first 6 chars match)
            overlap = 0
            for ew in emp_words:
                for cw in co_words:
                    if ew[:6] == cw[:6] and len(ew) >= 5 and len(cw) >= 5:
                        overlap += 1
                        break
            # Require at least 2 word root matches and >50% of employer words matched
            if overlap >= 2 and overlap / len(emp_words) > 0.5:
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_id = cid
        if best_id:
            return best_id

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
