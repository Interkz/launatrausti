import json
import os
import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import pdfplumber
import anthropic


@dataclass
class ExtractedData:
    company_name: str
    kennitala: Optional[str]
    year: int
    launakostnadur: int  # Wage costs in ISK
    starfsmenn: float  # Average employee count
    tekjur: Optional[int]  # Revenue in ISK
    confidence: float  # 0-1 confidence score
    raw_text_snippet: str  # For debugging


EXTRACTION_PROMPT = """You are an expert at extracting financial data from Icelandic annual reports (ársreikningar).

Extract the following fields from this annual report text. Return ONLY valid JSON, no other text.

Fields to extract:
1. company_name: The company name (look for "nafn" or at the top of the document)
2. kennitala: The company's national ID (10 digit number, format: XXXXXX-XXXX or XXXXXXXXXX)
3. year: The fiscal year this report covers (look for "reikningsár" or year in title)
4. launakostnadur: Total wage/salary costs in ISK (look for "launakostnaður", "laun og launatengd gjöld", "starfsmannakostnaður")
5. starfsmenn: Average number of employees (look for "meðalfjöldi starfsmanna", "fjöldi stöðugilda", "starfsmenn að meðaltali")
6. tekjur: Total revenue/income in ISK (look for "rekstrartekjur", "tekjur", "heildartekjur")

Important:
- Numbers in Icelandic use dots for thousands (1.000.000) and commas for decimals (1,5)
- Convert all numbers to integers (ISK) or floats (employees)
- If a value is in thousands (þús.kr. or þúsund), multiply by 1000
- If a value is in millions (m.kr. or milljónir), multiply by 1000000
- If you cannot find a field with confidence, use null
- Include a confidence score (0-1) for the overall extraction

Return JSON in this exact format:
{
    "company_name": "string",
    "kennitala": "string or null",
    "year": integer,
    "launakostnadur": integer,
    "starfsmenn": float,
    "tekjur": integer or null,
    "confidence": float
}

Annual report text:
"""


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract all text from a PDF file."""
    text_parts = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)

    return "\n\n".join(text_parts)


def parse_with_claude(text: str, api_key: Optional[str] = None) -> dict:
    """Use Claude to extract structured data from annual report text."""
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)

    # Truncate text if too long (keep first and last parts which usually have key info)
    max_chars = 30000
    if len(text) > max_chars:
        half = max_chars // 2
        text = text[:half] + "\n\n[...middle section truncated...]\n\n" + text[-half:]

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": EXTRACTION_PROMPT + text
            }
        ]
    )

    response_text = message.content[0].text.strip()

    # Try to parse JSON from response
    try:
        # Handle case where Claude might wrap in markdown code blocks
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]

        return json.loads(response_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse Claude response as JSON: {e}\nResponse: {response_text}")


def extract_from_pdf(pdf_path: Path, api_key: Optional[str] = None) -> ExtractedData:
    """Extract financial data from an annual report PDF."""
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Extract text
    text = extract_text_from_pdf(pdf_path)

    if not text.strip():
        raise ValueError(f"No text could be extracted from PDF: {pdf_path}")

    # Parse with Claude
    data = parse_with_claude(text, api_key)

    # Validate required fields
    if not data.get("launakostnadur"):
        raise ValueError("Could not extract launakostnadur (wage costs) from PDF")
    if not data.get("starfsmenn"):
        raise ValueError("Could not extract starfsmenn (employee count) from PDF")
    if not data.get("year"):
        raise ValueError("Could not extract year from PDF")

    # Try to extract kennitala from filename if not found in text
    kennitala = data.get("kennitala")
    if not kennitala:
        # Try filename pattern: {kennitala}_{year}.pdf
        match = re.search(r'(\d{10})', pdf_path.stem)
        if match:
            kennitala = match.group(1)

    return ExtractedData(
        company_name=data.get("company_name", "Unknown"),
        kennitala=kennitala,
        year=int(data["year"]),
        launakostnadur=int(data["launakostnadur"]),
        starfsmenn=float(data["starfsmenn"]),
        tekjur=int(data["tekjur"]) if data.get("tekjur") else None,
        confidence=float(data.get("confidence", 0.5)),
        raw_text_snippet=text[:500]  # Keep first 500 chars for debugging
    )


def extract_from_pdf_simple(pdf_path: Path) -> dict:
    """
    Simple extraction without Claude API - uses regex patterns.
    Fallback for when API is not available or for testing.
    """
    text = extract_text_from_pdf(pdf_path)

    result = {
        "company_name": None,
        "kennitala": None,
        "year": None,
        "launakostnadur": None,
        "starfsmenn": None,
        "tekjur": None,
    }

    # Try to find kennitala (10 digits)
    kt_match = re.search(r'(\d{6})-?(\d{4})', text)
    if kt_match:
        result["kennitala"] = kt_match.group(1) + kt_match.group(2)

    # Try to find year (4 digit year, likely 2020-2024)
    year_match = re.search(r'20(2[0-4])', text)
    if year_match:
        result["year"] = int("20" + year_match.group(1))

    # Try to find launakostnaður
    laun_patterns = [
        r'[Ll]aunakostna[ðd]ur[^\d]*?([\d\.]+)',
        r'[Ll]aun og launatengd gjöld[^\d]*?([\d\.]+)',
        r'[Ss]tarfsmannakostna[ðd]ur[^\d]*?([\d\.]+)',
    ]
    for pattern in laun_patterns:
        match = re.search(pattern, text)
        if match:
            num_str = match.group(1).replace('.', '')
            result["launakostnadur"] = int(num_str)
            break

    # Try to find employee count
    emp_patterns = [
        r'[Mm]e[ðd]alfj[öo]ldi starfsmanna[^\d]*?([\d,]+)',
        r'[Ff]j[öo]ldi st[öo][ðd]ugilda[^\d]*?([\d,]+)',
        r'[Ss]tarfsmenn a[ðd] me[ðd]altali[^\d]*?([\d,]+)',
    ]
    for pattern in emp_patterns:
        match = re.search(pattern, text)
        if match:
            num_str = match.group(1).replace(',', '.')
            result["starfsmenn"] = float(num_str)
            break

    return result
