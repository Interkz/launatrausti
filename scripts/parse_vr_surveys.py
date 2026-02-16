#!/usr/bin/env python3
"""
VR launarannsokn (salary survey) PDF parser.

Downloads VR salary survey PDFs and extracts job title salary data
using pdfplumber for text extraction and Claude API for structured parsing.

Usage:
    python scripts/parse_vr_surveys.py --all
    python scripts/parse_vr_surveys.py --all --dry-run
    python scripts/parse_vr_surveys.py --download-only
    python scripts/parse_vr_surveys.py --file pdfs/vr/launarannsokn_september_2025.pdf --date 2025-09
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import anthropic
import pdfplumber
import requests

from src.database import (
    ScrapeLogEntry,
    VRSalarySurvey,
    save_scrape_log,
    save_vr_survey,
)

# Known VR salary survey PDF URLs, keyed by survey date (YYYY-MM)
VR_SURVEY_URLS = {
    "2025-09": "https://www.vr.is/media/2f3e21zj/launarannsokn_september_2025.pdf",
    "2024-09": "https://www.vr.is/media/n4ed1zfs/launatafla_vefur.pdf",
    "2024-02": "https://www.vr.is/media/ogvfb001/launarannsokn_tafla_februar2024.pdf",
    "2023-02": "https://www.vr.is/media/y10ihrjt/tafla_launarannsokn.pdf",
}

# Default output directory for downloaded PDFs
DEFAULT_PDF_DIR = Path(__file__).parent.parent / "pdfs" / "vr"

EXTRACTION_PROMPT = """You are extracting salary data from an Icelandic VR launarannsokn (salary survey) PDF.
The PDF contains a table with job titles and salary statistics.

Extract ALL rows from the table. Return a JSON array where each entry has:
{
    "starfsheiti": "Job title in Icelandic",
    "starfsstett": "Job category (e.g. Skrifstofufólk, Sérfræðingar, Stjórnendur)",
    "medaltal": monthly_mean_salary_ISK_integer,
    "midgildi": monthly_median_salary_ISK_integer_or_null,
    "p25": 25th_percentile_ISK_integer_or_null,
    "p75": 75th_percentile_ISK_integer_or_null,
    "fjoldi": number_of_respondents_integer_or_null
}

Numbers in Icelandic use dots for thousands (1.000.000). Convert to plain integers.
If a column is missing from the table, use null.
Return ONLY the JSON array, no other text.

Here is the extracted text from the PDF:
"""


def download_vr_pdfs(output_dir: Optional[Path] = None) -> dict[str, Path]:
    """Download all known VR survey PDFs to the output directory.

    Skips PDFs that already exist locally.

    Args:
        output_dir: Directory to save PDFs. Defaults to pdfs/vr/.

    Returns:
        Dict mapping survey_date to local PDF path.
    """
    output_dir = output_dir or DEFAULT_PDF_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    downloaded = {}

    for survey_date, url in VR_SURVEY_URLS.items():
        filename = url.split("/")[-1]
        local_path = output_dir / filename

        if local_path.exists():
            print(f"  [skip] {survey_date}: {filename} (already exists)")
            downloaded[survey_date] = local_path
            continue

        print(f"  [download] {survey_date}: {filename} ...", end=" ", flush=True)
        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            local_path.write_bytes(response.content)
            print(f"OK ({len(response.content) / 1024:.0f} KB)")
            downloaded[survey_date] = local_path
        except requests.RequestException as e:
            print(f"FAILED: {e}")

    return downloaded


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract all text from a PDF using pdfplumber."""
    text_parts = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)

    return "\n\n".join(text_parts)


def parse_claude_json(response_text: str) -> list[dict]:
    """Parse JSON from Claude response, handling markdown code block wrapping."""
    text = response_text.strip()

    # Handle ```json ... ``` wrapping
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    return json.loads(text.strip())


def parse_vr_survey(
    pdf_path: Path,
    survey_date: str,
    api_key: Optional[str] = None,
) -> list[VRSalarySurvey]:
    """Parse a VR salary survey PDF and return structured data.

    1. Extracts text from the PDF with pdfplumber.
    2. Sends text to Claude API with a VR-specific extraction prompt.
    3. Parses the JSON response into VRSalarySurvey objects.

    Args:
        pdf_path: Path to the VR survey PDF file.
        survey_date: Survey date string, e.g. "2025-09".
        api_key: Optional Anthropic API key (falls back to ANTHROPIC_API_KEY env var).

    Returns:
        List of VRSalarySurvey dataclass instances.
    """
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Step 1: Extract text
    text = extract_text_from_pdf(pdf_path)
    if not text.strip():
        raise ValueError(f"No text could be extracted from PDF: {pdf_path}")

    # Truncate if extremely long (keep most relevant content)
    max_chars = 30000
    if len(text) > max_chars:
        text = text[:max_chars]

    # Step 2: Call Claude API
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable not set. "
            "Set it or pass --api-key."
        )

    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": EXTRACTION_PROMPT + text,
            }
        ],
    )

    response_text = message.content[0].text.strip()

    # Step 3: Parse JSON response into VRSalarySurvey objects
    try:
        rows = parse_claude_json(response_text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Failed to parse Claude response as JSON: {e}\n"
            f"Response preview: {response_text[:500]}"
        )

    now = datetime.now()
    source_pdf = str(pdf_path)
    surveys = []

    for row in rows:
        starfsheiti = row.get("starfsheiti")
        medaltal = row.get("medaltal")

        if not starfsheiti or not medaltal:
            # Skip rows missing required fields
            continue

        survey = VRSalarySurvey(
            id=None,
            survey_date=survey_date,
            starfsheiti=starfsheiti,
            starfsstett=row.get("starfsstett"),
            medaltal=int(medaltal),
            midgildi=int(row["midgildi"]) if row.get("midgildi") is not None else None,
            p25=int(row["p25"]) if row.get("p25") is not None else None,
            p75=int(row["p75"]) if row.get("p75") is not None else None,
            fjoldi_svara=int(row["fjoldi"]) if row.get("fjoldi") is not None else None,
            source_pdf=source_pdf,
            extracted_at=now,
        )
        surveys.append(survey)

    return surveys


def _extract_year_from_date(survey_date: str) -> Optional[int]:
    """Extract the year from a survey_date string like '2025-09'."""
    try:
        return int(survey_date.split("-")[0])
    except (ValueError, IndexError):
        return None


def _update_scrape_log(
    survey_date: str,
    status: str,
    pdf_path: Optional[str] = None,
    error_message: Optional[str] = None,
) -> int:
    """Create or update a scrape log entry for a VR survey."""
    now = datetime.now()
    entry = ScrapeLogEntry(
        id=None,
        source="vr_survey",
        identifier=survey_date,
        year=_extract_year_from_date(survey_date),
        status=status,
        pdf_path=pdf_path,
        error_message=error_message,
        created_at=now,
        updated_at=now,
    )
    return save_scrape_log(entry)


def download_and_parse_all(
    output_dir: Optional[Path] = None,
    dry_run: bool = False,
    api_key: Optional[str] = None,
) -> dict[str, list[VRSalarySurvey]]:
    """Download all VR survey PDFs, parse each, and save to database.

    Args:
        output_dir: Directory for PDFs. Defaults to pdfs/vr/.
        dry_run: If True, print results but do not save to database.
        api_key: Optional Anthropic API key.

    Returns:
        Dict mapping survey_date to list of parsed VRSalarySurvey objects.
    """
    print("Downloading VR salary survey PDFs...")
    downloaded = download_vr_pdfs(output_dir)

    if not downloaded:
        print("No PDFs downloaded or found. Exiting.")
        return {}

    all_results = {}

    for survey_date, pdf_path in sorted(downloaded.items()):
        print(f"\nParsing {survey_date}: {pdf_path.name}")
        _update_scrape_log(survey_date, "running", pdf_path=str(pdf_path))

        try:
            surveys = parse_vr_survey(pdf_path, survey_date, api_key=api_key)
            print(f"  Extracted {len(surveys)} job titles")

            if dry_run:
                _print_surveys(surveys)
                print("  [dry-run] Not saved to database")
            else:
                saved_count = 0
                for survey in surveys:
                    save_vr_survey(survey)
                    saved_count += 1
                print(f"  Saved {saved_count} records to database")

            _update_scrape_log(
                survey_date, "success", pdf_path=str(pdf_path)
            )
            all_results[survey_date] = surveys

        except Exception as e:
            print(f"  ERROR: {e}")
            _update_scrape_log(
                survey_date, "failed",
                pdf_path=str(pdf_path),
                error_message=str(e),
            )

    return all_results


def _print_surveys(surveys: list[VRSalarySurvey]) -> None:
    """Print parsed survey data in a readable table format."""
    if not surveys:
        print("  (no data extracted)")
        return

    # Header
    print(f"  {'Starfsheiti':<35} {'Stett':<20} {'Medaltal':>10} {'Midgildi':>10} {'P25':>10} {'P75':>10} {'Fjoldi':>7}")
    print(f"  {'-'*35} {'-'*20} {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*7}")

    for s in surveys:
        heiti = (s.starfsheiti[:33] + "..") if len(s.starfsheiti) > 35 else s.starfsheiti
        stett = (s.starfsstett[:18] + "..") if s.starfsstett and len(s.starfsstett) > 20 else (s.starfsstett or "")
        midgildi = f"{s.midgildi:>10,}" if s.midgildi is not None else f"{'--':>10}"
        p25 = f"{s.p25:>10,}" if s.p25 is not None else f"{'--':>10}"
        p75 = f"{s.p75:>10,}" if s.p75 is not None else f"{'--':>10}"
        fjoldi = f"{s.fjoldi_svara:>7}" if s.fjoldi_svara is not None else f"{'--':>7}"
        print(f"  {heiti:<35} {stett:<20} {s.medaltal:>10,} {midgildi} {p25} {p75} {fjoldi}")


def main():
    parser = argparse.ArgumentParser(
        description="Download and parse VR launarannsokn (salary survey) PDFs"
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Download and parse all known VR survey PDFs",
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="Parse a single PDF file (requires --date)",
    )
    parser.add_argument(
        "--date",
        type=str,
        help="Survey date for --file, e.g. '2025-09'",
    )
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Download PDFs without parsing",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Parse and display results without saving to database",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=f"Directory for downloaded PDFs (default: {DEFAULT_PDF_DIR})",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Anthropic API key (default: ANTHROPIC_API_KEY env var)",
    )

    args = parser.parse_args()

    # Validate argument combinations
    if args.file and not args.date:
        parser.error("--file requires --date (e.g. --date 2025-09)")

    if not args.all and not args.file and not args.download_only:
        parser.print_help()
        sys.exit(1)

    # --- Download only ---
    if args.download_only:
        print("Downloading VR salary survey PDFs...")
        downloaded = download_vr_pdfs(args.output_dir)
        print(f"\n{len(downloaded)} PDF(s) available in {args.output_dir or DEFAULT_PDF_DIR}")
        return

    # --- Single file ---
    if args.file:
        if not args.file.exists():
            print(f"Error: File not found: {args.file}")
            sys.exit(1)

        print(f"Parsing {args.file} (date: {args.date})")
        _update_scrape_log(args.date, "running", pdf_path=str(args.file))

        try:
            surveys = parse_vr_survey(args.file, args.date, api_key=args.api_key)
            print(f"Extracted {len(surveys)} job titles\n")
            _print_surveys(surveys)

            if args.dry_run:
                print("\n[dry-run] Not saved to database")
            else:
                saved_count = 0
                for survey in surveys:
                    save_vr_survey(survey)
                    saved_count += 1
                print(f"\nSaved {saved_count} records to database")

            _update_scrape_log(args.date, "success", pdf_path=str(args.file))

        except Exception as e:
            print(f"Error: {e}")
            _update_scrape_log(
                args.date, "failed",
                pdf_path=str(args.file),
                error_message=str(e),
            )
            sys.exit(1)

        return

    # --- All surveys ---
    if args.all:
        results = download_and_parse_all(
            output_dir=args.output_dir,
            dry_run=args.dry_run,
            api_key=args.api_key,
        )

        total = sum(len(v) for v in results.values())
        print(f"\nDone. Processed {len(results)} PDF(s), {total} total job titles.")


if __name__ == "__main__":
    main()
