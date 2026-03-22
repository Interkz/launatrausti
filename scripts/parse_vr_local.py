"""
Parse VR salary survey PDFs using pdfplumber (no API needed).

Extracts per-job-title salary data from VR Launarannsókn PDFs.
Format: job title followed by 9 numbers (4 grunnlaun + 4 heildarlaun + fjöldi).
Uses heildarlaun (total wages) columns.

Usage:
    python scripts/parse_vr_local.py
    python scripts/parse_vr_local.py --pdf pdfs/vr/specific_file.pdf --date 2025-09
"""

import sys
import os
import re
import argparse
from pathlib import Path
from datetime import datetime

import pdfplumber

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.database import VRSalarySurvey, save_vr_survey

PDF_DIR = Path(__file__).parent.parent / "pdfs" / "vr"

# Known PDFs and their survey dates
KNOWN_PDFS = {
    "launarannsokn_september_2025.pdf": "2025-09",
    "launatafla_vefur.pdf": "2024-09",
    "tafla_launarannsokn.pdf": "2023-02",
}

# Category headers that appear as rows with no numbers
CATEGORY_NAMES = {
    "Skrifstofufólk", "Sölu-ogafgreiðslufólk", "Göslu-,lager-ogframleiðslustörf",
    "Stjórnendur", "Sérfræðingar", "Sérhæftstarfsfólk",
    # Garbled versions from pdfplumber encoding
    "Skrifstofuf", "S\u00f6lu-ogafgrei\u00f0sluf", "G\u00f6slu-",
    "Stj\u00f3rnendur", "S\u00e9rfr\u00e6\u00f0ingar", "S\u00e9rh\u00e6ftstarfsf",
}


def parse_vr_pdf(pdf_path: Path, survey_date: str) -> list[dict]:
    """Parse a single VR salary survey PDF. Returns list of job title rows."""
    pdf = pdfplumber.open(pdf_path)
    rows = []
    current_stett = None

    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue

        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Skip header lines
            if any(skip in line for skip in [
                "Launaranns", "Grunnlaun", "gildi", "Launat\u00f6lur",
                "heildina", "Heildarlaun"
            ]):
                continue

            # Check if this is a category header (text with no numbers)
            for cat in CATEGORY_NAMES:
                if line.startswith(cat):
                    current_stett = line
                    break

            # Match data rows: text followed by 9+ numbers
            # Numbers can be like "854", "1.033", "15.401"
            match = re.match(
                r'^(.+?)\s+'
                r'([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+'  # grunnlaun
                r'([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+'  # heildarlaun
                r'([\d.]+)',  # fjöldi
                line
            )
            if not match:
                continue

            name = match.group(1).strip()

            # Skip the "Öll laun" aggregate row
            if "ll laun" in name or name == "\u00d6lllaun":
                continue

            # Skip category headers that matched as data
            if any(name.startswith(cat[:8]) for cat in CATEGORY_NAMES):
                current_stett = name
                continue

            def to_isk(val: str) -> int:
                """Convert from thousands (e.g. '1.033' = 1,033,000 kr)."""
                cleaned = val.replace(".", "")
                return int(cleaned) * 1000

            def to_int(val: str) -> int:
                return int(val.replace(".", ""))

            rows.append({
                "survey_date": survey_date,
                "starfsheiti": name,
                "starfsstett": current_stett,
                "medaltal": to_isk(match.group(7)),   # heildarlaun meðaltal
                "midgildi": to_isk(match.group(6)),   # heildarlaun miðgildi
                "p25": to_isk(match.group(8)),         # heildarlaun 25%mörk
                "p75": to_isk(match.group(9)),         # heildarlaun 75%mörk
                "fjoldi_svara": to_int(match.group(10)),
            })

    pdf.close()
    return rows


def save_rows(rows: list[dict], source_pdf: str) -> int:
    """Save parsed rows to database. Returns count saved."""
    saved = 0
    for row in rows:
        survey = VRSalarySurvey(
            id=None,
            survey_date=row["survey_date"],
            starfsheiti=row["starfsheiti"],
            starfsstett=row["starfsstett"],
            medaltal=row["medaltal"],
            midgildi=row["midgildi"],
            p25=row["p25"],
            p75=row["p75"],
            fjoldi_svara=row["fjoldi_svara"],
            source_pdf=source_pdf,
            extracted_at=datetime.now(),
        )
        save_vr_survey(survey)
        saved += 1
    return saved


def main():
    parser = argparse.ArgumentParser(description="Parse VR salary survey PDFs locally")
    parser.add_argument("--pdf", type=str, help="Specific PDF to parse")
    parser.add_argument("--date", type=str, help="Survey date for the PDF (e.g. 2025-09)")
    args = parser.parse_args()

    total_saved = 0

    if args.pdf:
        pdf_path = Path(args.pdf)
        if not pdf_path.exists():
            print(f"File not found: {pdf_path}")
            sys.exit(1)
        date = args.date or "unknown"
        rows = parse_vr_pdf(pdf_path, date)
        saved = save_rows(rows, pdf_path.name)
        total_saved += saved
        print(f"{pdf_path.name}: {len(rows)} rows parsed, {saved} saved (date: {date})")
    else:
        # Parse all known PDFs
        for filename, date in KNOWN_PDFS.items():
            pdf_path = PDF_DIR / filename
            if not pdf_path.exists():
                print(f"  Skipping {filename} (not found)")
                continue

            rows = parse_vr_pdf(pdf_path, date)
            saved = save_rows(rows, filename)
            total_saved += saved
            print(f"{filename}: {len(rows)} rows parsed, {saved} saved (date: {date})")

    # Summary
    from src.database import get_connection
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM vr_salary_surveys")
    total = c.fetchone()["cnt"]
    c.execute("SELECT COUNT(DISTINCT starfsheiti) as cnt FROM vr_salary_surveys")
    titles = c.fetchone()["cnt"]
    c.execute("SELECT COUNT(DISTINCT survey_date) as cnt FROM vr_salary_surveys")
    dates = c.fetchone()["cnt"]
    conn.close()

    print(f"\nTotal in DB: {total} records, {titles} job titles, {dates} survey dates")


if __name__ == "__main__":
    main()
