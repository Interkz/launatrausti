"""
Extract financial data from annual report PDFs using pdfplumber + regex.
No API needed — all processing is local.

Extracts:
- Launakostnaður (total wage costs) / Laun og launatengd gjöld
- Meðaltal ársverka / Starfsmenn (employee count)
- Tekjur / Rekstrartekjur (revenue)
- Hagnaður (profit)

Usage:
    python scripts/extract_pdf_local.py pdfs/4710080280_2023.pdf
    python scripts/extract_pdf_local.py --batch pdfs/
    python scripts/extract_pdf_local.py --batch pdfs/ --save
"""

import sys
import os
import re
import argparse
from pathlib import Path
from datetime import datetime

import pdfplumber

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def parse_icelandic_number(text: str) -> int:
    """Parse Icelandic number format: '15.145' or '15,145' → 15145 (millions)."""
    cleaned = text.strip().replace(".", "").replace(",", "").replace(" ", "")
    # Handle parentheses (negative numbers)
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    try:
        return int(cleaned)
    except ValueError:
        return None


def extract_financials(pdf_path: Path) -> dict:
    """Extract key financial data from an annual report PDF."""
    pdf = pdfplumber.open(pdf_path)
    result = {
        "launakostnadur": None,
        "starfsmenn": None,
        "tekjur": None,
        "hagnadur": None,
        "rekstrarkostnadur": None,
        "confidence": 0.0,
        "notes": [],
    }

    all_text = ""
    for page in pdf.pages:
        text = page.extract_text()
        if text:
            all_text += text + "\n"

    # --- Launakostnaður / Laun og launatengd gjöld ---
    # Strategy 1: Regex on full text
    patterns_laun = [
        # "Samtals 15.145 13.832" (total wages section)
        r"(?:Samtals|Alls)\s+([\d.]+)\s+([\d.]+)\s*\n.*?(?:Me[ðd]altal|[Áá]rsverk)",
        # "12 Laun og launatengd gjöld (15.145) (13.832)" in income statement
        r"Laun og launatengd gj[öo]ld\s+\(?([\d.]+)\)?\s+\(?([\d.]+)\)?",
        # Direct match
        r"Launakostna[ðd]ur\s+([\d.]+)\s+([\d.]+)",
        # Launagreiðslur line
        r"Launagrei[ðd]slur\s+([\d.]+)\s+([\d.]+)",
        # Dotted-line format: "Laun og tengd gjöld ............... 13.934 12.760"
        r"Laun og tengd gj[öo]ld\s*\.+([\d.]+)\s+([\d.]+)",
    ]

    for pattern in patterns_laun:
        match = re.search(pattern, all_text)
        if match:
            val = parse_icelandic_number(match.group(1))
            if val and val > 100:  # Sanity: wage costs should be > 100M
                result["launakostnadur"] = val * 1_000_000
                result["notes"].append(f"Launakostnaður matched: {match.group(0)[:80]}")
                break

    # Strategy 2: Word-level extraction for dotted-line PDFs
    if not result["launakostnadur"]:
        for page in pdf.pages:
            words = page.extract_words()
            for i, w in enumerate(words):
                wtext = w["text"].lower()
                if ("laun og tengd" in wtext or
                    (wtext == "laun" and i + 2 < len(words) and
                     words[i+1]["text"] == "og" and "tengd" in words[i+2]["text"])):
                    # Find numbers on the same line (similar y coordinate)
                    y = w["top"]
                    line_nums = []
                    for w2 in words:
                        if abs(w2["top"] - y) < 5 and re.match(r"[\d.]+$", w2["text"]) and len(w2["text"]) > 2:
                            line_nums.append(w2["text"])
                    if not line_nums:
                        # Check next line (numbers might be on the row below the heading)
                        for w2 in words:
                            if 10 < w2["top"] - y < 20 and re.match(r"[\d.]+$", w2["text"]) and len(w2["text"]) > 2:
                                line_nums.append(w2["text"])
                    if line_nums:
                        val = parse_icelandic_number(line_nums[0])
                        if val and val > 100:
                            result["launakostnadur"] = val * 1_000_000
                            result["notes"].append(f"Launakostnaður (word-level): {line_nums[0]} from line with 'Laun og tengd'")
                            break
            if result["launakostnadur"]:
                break

    # --- Starfsmenn / Ársverka ---
    patterns_staff = [
        r"Me[ðd]altal [áa]rsverka[^0-9]*([\d.]+)\s",
        r"Me[ðd]alfj[öo]ldi st[öo][ðd]ugilda[^0-9]*([\d.]+)",
        r"Me[ðd]alfj[öo]ldi starfsmanna[^0-9]*([\d.]+)\s",
        r"[Áá]rsverk [íi] [áa]rslok[^0-9]*([\d.]+)\s",
        r"Starfsmenn[^0-9]*([\d.]+)\s",
        r"(\d{2,5})\s+starfsmenn",
    ]

    for pattern in patterns_staff:
        match = re.search(pattern, all_text)
        if match:
            val = parse_icelandic_number(match.group(1))
            if val and 5 < val < 50000:
                result["starfsmenn"] = val
                result["notes"].append(f"Starfsmenn matched: {match.group(0)[:80]}")
                break

    # --- Tekjur ---
    patterns_tekjur = [
        r"Hreinar vaxtatekjur\s+([\d.]+)\s+([\d.]+)",  # Banks
        r"Rekstrartekjur\s+([\d.]+)\s+([\d.]+)",
        r"Tekjur\s+samtals\s+([\d.]+)\s+([\d.]+)",
        r"Sala [áa] vörum\s+([\d.]+)\s+([\d.]+)",
    ]

    for pattern in patterns_tekjur:
        match = re.search(pattern, all_text)
        if match:
            val = parse_icelandic_number(match.group(1))
            if val and val > 10:
                result["tekjur"] = val * 1_000_000
                result["notes"].append(f"Tekjur matched: {match.group(0)[:80]}")
                break

    # --- Hagnaður ---
    patterns_hagnadur = [
        r"Hagnaður \(?tapi?\)? (?:ársins|tímabilsins)\s+\(?([\d.]+)\)?\s",
        r"Hagna[ðd]ur [áa]rsins\s+\(?([\d.]+)\)?\s",
    ]

    for pattern in patterns_hagnadur:
        match = re.search(pattern, all_text)
        if match:
            val = parse_icelandic_number(match.group(1))
            if val:
                result["hagnadur"] = val * 1_000_000
                result["notes"].append(f"Hagnaður matched: {match.group(0)[:80]}")
                break

    # --- Confidence score ---
    found = sum(1 for k in ["launakostnadur", "starfsmenn", "tekjur"] if result[k])
    result["confidence"] = found / 3.0

    pdf.close()
    return result


def extract_metadata_from_filename(filename: str) -> dict:
    """Extract kennitala and year from filename like '4710080280_2023.pdf'."""
    match = re.match(r"(\d{10})_(\d{4})", filename)
    if match:
        return {"kennitala": match.group(1), "year": int(match.group(2))}

    # Try alternative format: 4710080280_Landsbankinn_hf._ars_2023.pdf
    match = re.match(r"(\d{10})_.*?(\d{4})\.pdf", filename)
    if match:
        return {"kennitala": match.group(1), "year": int(match.group(2))}

    return {}


def main():
    parser = argparse.ArgumentParser(description="Extract financial data from annual report PDFs")
    parser.add_argument("pdf", nargs="?", help="Single PDF to extract")
    parser.add_argument("--batch", type=str, help="Directory of PDFs to extract")
    parser.add_argument("--save", action="store_true", help="Save results to database")
    args = parser.parse_args()

    pdfs = []
    if args.pdf:
        pdfs = [Path(args.pdf)]
    elif args.batch:
        pdfs = sorted(Path(args.batch).glob("*.pdf"))
        pdfs = [p for p in pdfs if not p.name.startswith(".")]
    else:
        print("Specify a PDF file or --batch directory")
        sys.exit(1)

    for pdf_path in pdfs:
        meta = extract_metadata_from_filename(pdf_path.name)
        kennitala = meta.get("kennitala", "?")
        year = meta.get("year", "?")

        print(f"\n{'='*60}")
        print(f"{pdf_path.name} (kt: {kennitala}, year: {year})")
        print(f"{'='*60}")

        result = extract_financials(pdf_path)

        if result["launakostnadur"]:
            print(f"  Launakostnaður:  {result['launakostnadur']:>15,} kr")
        else:
            print(f"  Launakostnaður:  NOT FOUND")

        if result["starfsmenn"]:
            print(f"  Starfsmenn:      {result['starfsmenn']:>15,}")
        else:
            print(f"  Starfsmenn:      NOT FOUND")

        if result["launakostnadur"] and result["starfsmenn"]:
            avg = result["launakostnadur"] // result["starfsmenn"]
            monthly = avg // 12
            print(f"  Avg salary:      {avg:>15,} kr/year ({monthly:,} kr/month)")

        if result["tekjur"]:
            print(f"  Tekjur:          {result['tekjur']:>15,} kr")

        if result["hagnadur"]:
            print(f"  Hagnaður:        {result['hagnadur']:>15,} kr")

        print(f"  Confidence:      {result['confidence']:.0%}")
        for note in result["notes"]:
            print(f"  > {note}")

        if args.save and result["launakostnadur"] and result["starfsmenn"] and kennitala != "?" and year != "?":
            from src.database import get_or_create_company, save_annual_report
            company_id = get_or_create_company(kennitala, kennitala)
            save_annual_report(
                company_id=company_id,
                year=year,
                launakostnadur=result["launakostnadur"],
                starfsmenn=result["starfsmenn"],
                source_pdf=pdf_path.name,
                tekjur=result["tekjur"],
                hagnadur=result["hagnadur"],
                source_type="pdf_local",
                confidence=result["confidence"],
            )
            print(f"  SAVED to database")


if __name__ == "__main__":
    main()
