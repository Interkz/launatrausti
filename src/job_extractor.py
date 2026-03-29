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
        r'(\d{3}(?:\.\d{3})+)\s*[-\u2013]\s*(\d{3}(?:\.\d{3})+)\s*(?:kr|ISK)?',
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
