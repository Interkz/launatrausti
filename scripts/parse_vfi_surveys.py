"""
Parse VFÍ (engineers/technicians) salary survey PDFs.

Extracts cross-tab salary data from the annual kjarakönnun PDFs using pdfplumber.
Data is dimensional (by sector, function, field, seniority, gender, etc.) — not by job title.

Source PDFs: pdfs/vfi/vfi_kjarakonnun_verkfraedinga_2025.pdf
             pdfs/vfi/vfi_kjarakonnun_taeknifraedinga_2025.pdf

Usage:
    python scripts/parse_vfi_surveys.py
    python scripts/parse_vfi_surveys.py --dry-run
"""

import sys
import os
import argparse
import re
from datetime import datetime

import pdfplumber

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src import database


def parse_number(s: str) -> int | None:
    """Parse '1.270' or '963' (thousands of ISK) to full ISK."""
    if not s or s.strip() in ('', '–', '-', '—'):
        return None
    cleaned = s.strip().replace('.', '').replace(',', '')
    if not cleaned.isdigit():
        return None
    return int(cleaned) * 1000


def extract_comparison_tables(pdf, page_numbers: list[int], dimension_name: str) -> list[dict]:
    """Extract Tafla 2-4 style comparison tables (dimension, fjoldi, heildargreidslur 2025/2024).

    These tables have: label, fjoldi_2025, heildargreidslur_2025, fjoldi_2024, heildargreidslur_2024, mismunur, haekkun
    """
    rows = []
    for pg_num in page_numbers:
        page = pdf.pages[pg_num]
        tables = page.extract_tables()
        for table in tables:
            for row in table:
                if not row or not row[0]:
                    continue
                label = row[0].strip().rstrip('*')
                if label in ('', 'Alls') or label.startswith('Marktækur'):
                    continue
                # Skip header rows
                if any(h in label for h in ['Fjöldi', 'Heildar', 'Hækkun', 'Mis-']):
                    continue

                fjoldi = None
                heildargreidslur = None
                try:
                    if len(row) >= 3:
                        fjoldi = int(row[1].strip().replace('.', '')) if row[1] and row[1].strip().replace('.', '').isdigit() else None
                        heildargreidslur = parse_number(row[2])
                except (ValueError, AttributeError):
                    continue

                if heildargreidslur:
                    rows.append({
                        'dimension': dimension_name,
                        'dimension_value': label,
                        'n': fjoldi,
                        'heildarlaun_medal': heildargreidslur,
                    })
    return rows


def extract_percentile_table(pdf, page_number: int, dimension_name: str) -> list[dict]:
    """Extract Tafla 5 style percentile table (cohort, fjoldi, medaltal, midgildi, p10, p25, p75, p90)."""
    rows = []
    page = pdf.pages[page_number]
    tables = page.extract_tables()

    for table in tables:
        for row in table:
            if not row or not row[0]:
                continue
            label = row[0].strip().rstrip('*')
            if not label or label in ('Alls',):
                continue
            if any(h in label for h in ['Fjöldi', 'Meðaltal', '10%', 'mark']):
                continue

            try:
                if len(row) >= 7:
                    fjoldi = int(row[1].strip().replace('.', '')) if row[1] and row[1].strip().replace('.', '').isdigit() else None
                    rows.append({
                        'dimension': dimension_name,
                        'dimension_value': label,
                        'n': fjoldi,
                        'heildarlaun_medal': parse_number(row[2]),
                        'heildarlaun_midgildi': parse_number(row[3]),
                        'p25': parse_number(row[5]),
                        'p75': parse_number(row[6]),
                    })
            except (ValueError, AttributeError, IndexError):
                continue
    return rows


def extract_wage_component_tables(pdf, page_numbers: list[int], dimension_name: str) -> list[dict]:
    """Extract Tafla 6-12 style tables with wage component breakdown.

    Columns: label, fjoldi, fost_laun, yfirvinna, bilastyrkur, dagpeningar, bonus, annad, heildargreidslur, stadalfravik
    """
    rows = []
    for pg_num in page_numbers:
        page = pdf.pages[pg_num]
        tables = page.extract_tables()
        for table in tables:
            for row in table:
                if not row or not row[0]:
                    continue
                label = row[0].strip().rstrip('*')
                if not label or label in ('Alls',):
                    continue
                if any(h in label for h in ['Fjöldi', 'Föst', 'Yfir', 'Heildar', 'Staðal']):
                    continue

                try:
                    if len(row) >= 9:
                        fjoldi = int(row[1].strip().replace('.', '')) if row[1] and row[1].strip().replace('.', '').isdigit() else None
                        fast_laun = parse_number(row[2])
                        yfirvinna = parse_number(row[3])
                        heildargreidslur = parse_number(row[8]) if len(row) > 8 else None

                        if heildargreidslur:
                            bonus_val = parse_number(row[6]) if len(row) > 6 else None
                            rows.append({
                                'dimension': dimension_name,
                                'dimension_value': label,
                                'n': fjoldi,
                                'heildarlaun_medal': heildargreidslur,
                                'fast_laun': fast_laun,
                                'yfirvinna': yfirvinna,
                                'bonus': bonus_val,
                            })
                except (ValueError, AttributeError, IndexError):
                    continue
    return rows


def process_pdf(pdf_path: str, member_type: str, survey_year: int) -> list[dict]:
    """Process one VFÍ PDF and return all extracted rows."""
    pdf = pdfplumber.open(pdf_path)
    all_rows = []

    # The page numbers vary slightly between verkfræðingar and tæknifræðingar
    # We'll use text-based detection to find the right tables

    # Strategy: extract text from each page to find table numbers, then parse
    page_texts = {}
    for i, page in enumerate(pdf.pages):
        text = page.extract_text() or ''
        page_texts[i] = text

    # Find pages with specific table titles
    for i, text in page_texts.items():
        # Tafla 2: by starfsvettvangur (employer sector)
        if 'eftir starfsvettvangi' in text.lower() and 'samanburður' in text.lower():
            rows = extract_comparison_tables(pdf, [i], 'starfsvettvangur')
            all_rows.extend(rows)

        # Tafla 3: by fagsvið (field)
        elif 'eftir fagsviði' in text.lower() and 'samanburður' in text.lower():
            rows = extract_comparison_tables(pdf, [i], 'fagsvið')
            all_rows.extend(rows)

        # Tafla 4: by starfssvið (work function)
        elif 'eftir starfssviði' in text.lower() and 'samanburður' in text.lower():
            rows = extract_comparison_tables(pdf, [i], 'starfssvið')
            all_rows.extend(rows)

        # Tafla 5: percentiles by graduation cohort
        elif ('eftir útskriftarári' in text.lower() and 'miðgildi' in text.lower()
              and '10%' in text and 'samanburður' not in text.lower()):
            rows = extract_percentile_table(pdf, i, 'útskriftarár')
            all_rows.extend(rows)

        # Tafla 7: by age
        elif 'eftir aldri' in text.lower() and 'meðaltal' in text.lower() and 'starfsvettvangi' not in text.lower():
            rows = extract_wage_component_tables(pdf, [i], 'aldur')
            all_rows.extend(rows)

        # Tafla 8: by employer sector (detailed with components)
        elif 'eftir aðalstarfsvettvangi' in text.lower() and 'föst' in text.lower():
            rows = extract_wage_component_tables(pdf, [i], 'starfsvettvangur_detail')
            all_rows.extend(rows)

        # Tafla 9: by fagsvið (detailed)
        elif 'eftir aðalfagsviði' in text.lower() and 'föst' in text.lower():
            rows = extract_wage_component_tables(pdf, [i], 'fagsvið_detail')
            all_rows.extend(rows)

        # Tafla 10: by starfssvið (detailed)
        elif 'eftir aðalstarfssviði' in text.lower() and 'föst' in text.lower():
            rows = extract_wage_component_tables(pdf, [i], 'starfssvið_detail')
            all_rows.extend(rows)

        # Tafla 11: by gender — look for Karl/Kona in the table data
        elif ('eftir kyni' in text.lower() and 'meðaltal' in text.lower()
              and ('Karl' in text or 'Kona' in text) and 'starfsvettvangi' not in text.lower()):
            rows = extract_wage_component_tables(pdf, [i], 'kyn')
            # Filter to only keep genuine gender rows
            rows = [r for r in rows if r['dimension_value'] in ('Karl', 'Kona', 'Karlar', 'Konur', 'Kynsegin / annað')]
            all_rows.extend(rows)

        # Tafla 12: by location
        elif 'eftir staðsetningu' in text.lower() and 'meðaltal' in text.lower():
            rows = extract_wage_component_tables(pdf, [i], 'staðsetning')
            all_rows.extend(rows)

    pdf.close()

    # Add member_type and survey_year to all rows
    for row in all_rows:
        row['member_type'] = member_type
        row['survey_year'] = survey_year

    return all_rows


def save_rows(rows: list[dict], source_pdf: str):
    """Save extracted rows to vfi_salary_surveys table."""
    conn = database.get_connection()
    cursor = conn.cursor()

    saved = 0
    for row in rows:
        try:
            cursor.execute("""
                INSERT INTO vfi_salary_surveys
                    (survey_year, member_type, dimension, dimension_value, n,
                     heildarlaun_medal, heildarlaun_midgildi, p25, p75,
                     fast_laun, yfirvinna, bonus, source_pdf, extracted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (survey_year, member_type, dimension, dimension_value) DO UPDATE SET
                    n = excluded.n,
                    heildarlaun_medal = excluded.heildarlaun_medal,
                    heildarlaun_midgildi = excluded.heildarlaun_midgildi,
                    p25 = excluded.p25,
                    p75 = excluded.p75,
                    fast_laun = excluded.fast_laun,
                    yfirvinna = excluded.yfirvinna,
                    bonus = excluded.bonus,
                    extracted_at = excluded.extracted_at
            """, (
                row['survey_year'], row['member_type'], row['dimension'],
                row['dimension_value'], row.get('n'),
                row.get('heildarlaun_medal'), row.get('heildarlaun_midgildi'),
                row.get('p25'), row.get('p75'),
                row.get('fast_laun'), row.get('yfirvinna'), row.get('bonus'),
                source_pdf, datetime.now(),
            ))
            saved += 1
        except Exception as e:
            print(f"    Error saving {row.get('dimension_value')}: {e}")

    conn.commit()
    conn.close()
    return saved


def main():
    parser = argparse.ArgumentParser(description="Parse VFÍ salary survey PDFs")
    parser.add_argument("--dry-run", action="store_true", help="Print data without saving")
    args = parser.parse_args()

    pdfs = [
        ("pdfs/vfi/vfi_kjarakonnun_verkfraedinga_2025.pdf", "verkfraedingur", 2025),
        ("pdfs/vfi/vfi_kjarakonnun_taeknifraedinga_2025.pdf", "taeknifraedingur", 2025),
    ]

    total_saved = 0
    for pdf_path, member_type, year in pdfs:
        full_path = os.path.join(os.path.dirname(__file__), "..", pdf_path)
        if not os.path.exists(full_path):
            print(f"SKIP: {pdf_path} not found")
            continue

        print(f"\n{'='*50}")
        print(f"Processing: {pdf_path}")
        print(f"Member type: {member_type}, Year: {year}")
        print(f"{'='*50}")

        rows = process_pdf(full_path, member_type, year)
        print(f"\nExtracted {len(rows)} rows:")

        # Group by dimension for summary
        by_dim = {}
        for r in rows:
            dim = r['dimension']
            by_dim.setdefault(dim, []).append(r)

        for dim, dim_rows in by_dim.items():
            print(f"\n  {dim} ({len(dim_rows)} rows):")
            for r in dim_rows[:5]:
                salary = r.get('heildarlaun_medal')
                salary_str = f"{salary:,}" if salary else "N/A"
                print(f"    {r['dimension_value']}: n={r.get('n')}, heildarlaun={salary_str}")
            if len(dim_rows) > 5:
                print(f"    ... ({len(dim_rows)} total)")

        if not args.dry_run:
            saved = save_rows(rows, pdf_path)
            total_saved += saved
            print(f"\n  Saved {saved} rows to database")
        else:
            print(f"\n  (dry run — {len(rows)} rows would be saved)")

    if not args.dry_run:
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM vfi_salary_surveys")
        total = cursor.fetchone()["cnt"]
        conn.close()
        print(f"\nTotal VFÍ records in database: {total}")

    print(f"\nDone! {'Would save' if args.dry_run else 'Saved'}: {total_saved if not args.dry_run else sum(len(process_pdf(os.path.join(os.path.dirname(__file__), '..', p), m, y)) for p, m, y in pdfs)} rows")


if __name__ == "__main__":
    main()
