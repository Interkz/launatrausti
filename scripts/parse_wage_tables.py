#!/usr/bin/env python3
"""
Parse ASI consolidated kauptaxtar PDF into wage_tables database.

The PDF contains wage tables for all major Icelandic unions, with:
- Launaflokkur (pay grade) → monthly salary by seniority step
- Job title → launaflokkur mapping

Source: https://www.asa.is/images/stories/KjaramalPdf/Kauptaxtar.pdf
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pdfplumber
from src.database import get_connection, init_db

PDF_PATH = Path(__file__).parent.parent / "pdfs" / "asi_kauptaxtar_2026.pdf"


def parse_wage_grades(pdf) -> list[dict]:
    """Parse launaflokkur wage tables from pages 5 (AFL/SGS monthly wages)."""
    grades = []

    # Page 5: AFL/SGS Mánaðarlaun (Launaflokkur 4-24)
    text = pdf.pages[4].extract_text()
    for line in text.split("\n"):
        m = re.match(r"Launaflokkur\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", line)
        if m:
            grade = int(m.group(1))
            wages = [int(m.group(i).replace(".", "")) for i in range(2, 6)]
            grades.append({
                "union": "AFL/SGS",
                "agreement": "SA og AFLs",
                "grade": grade,
                "start": wages[0],
                "year_1": wages[1],
                "year_3": wages[2],
                "year_5": wages[3],
                "effective_date": "2026-01-01",
            })

    # Page 39: Government/SGS (Launaflokkur 117-200)
    for page_idx in [38, 39, 40, 41, 42, 43, 44]:
        if page_idx >= len(pdf.pages):
            break
        text = pdf.pages[page_idx].extract_text() or ""
        for line in text.split("\n"):
            m = re.match(r"(\d{3})\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", line)
            if m:
                grade = int(m.group(1))
                if 100 <= grade <= 300:
                    wages = [int(m.group(i).replace(".", "")) for i in range(2, 6)]
                    grades.append({
                        "union": "BSRB/BHM",
                        "agreement": "ríkisins og SGS",
                        "grade": grade,
                        "start": wages[0],
                        "year_1": wages[1],
                        "year_3": wages[2],
                        "year_5": wages[3],
                        "effective_date": "2025-04-01",
                    })

    # Page 52+: Municipal workers
    for page_idx in range(51, min(60, len(pdf.pages))):
        text = pdf.pages[page_idx].extract_text() or ""
        if "sveitarfélaga" not in text.lower() and not re.search(r"\b1\d{2}\b.*\b\d{3}\.\d{3}\b", text):
            continue
        for line in text.split("\n"):
            m = re.match(r"(\d{3})\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", line)
            if m:
                grade = int(m.group(1))
                if 100 <= grade <= 300:
                    wages = [int(m.group(i).replace(".", "")) for i in range(2, 6)]
                    # Don't duplicate if already from government
                    existing = [g for g in grades if g["grade"] == grade and g["union"] == "Sveitarfélög"]
                    if not existing:
                        grades.append({
                            "union": "Sveitarfélög",
                            "agreement": "sveitarfélaga",
                            "grade": grade,
                            "start": wages[0],
                            "year_1": wages[1],
                            "year_3": wages[2],
                            "year_5": wages[3],
                            "effective_date": "2025-04-01",
                        })

    return grades


def parse_job_mappings(pdf) -> list[dict]:
    """Parse job title → launaflokkur mappings from pages 9-10."""
    mappings = []
    current_grade = None

    for page_idx in [8, 9]:
        text = pdf.pages[page_idx].extract_text() or ""
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Match "Launaflokkur N"
            grade_match = re.match(r"L\s*aunaflokkur\s+(\d+)", line)
            if grade_match:
                current_grade = int(grade_match.group(1))
                continue

            # Skip headers and short lines
            if current_grade and len(line) > 3 and not line.startswith("Röðun") and not line.startswith("Laun "):
                # Clean up the job title
                title = line.rstrip(".")
                if title and not title[0].isdigit():
                    mappings.append({
                        "grade": current_grade,
                        "title": title,
                    })

    return mappings


def create_tables():
    """Create wage_tables and wage_grade_mappings tables."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS wage_tables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            union_name TEXT NOT NULL,
            agreement TEXT,
            grade INTEGER NOT NULL,
            start_salary INTEGER NOT NULL,
            year_1_salary INTEGER,
            year_3_salary INTEGER,
            year_5_salary INTEGER,
            effective_date TEXT,
            UNIQUE(union_name, grade, effective_date)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS wage_grade_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grade INTEGER NOT NULL,
            job_title TEXT NOT NULL,
            union_name TEXT DEFAULT 'AFL/SGS',
            UNIQUE(grade, job_title)
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_wage_tables_grade ON wage_tables(grade)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_wage_mappings_title ON wage_grade_mappings(job_title)")

    conn.commit()
    conn.close()


def save_data(grades: list[dict], mappings: list[dict]):
    """Save parsed data to database."""
    conn = get_connection()
    cursor = conn.cursor()

    saved_grades = 0
    for g in grades:
        cursor.execute("""
            INSERT INTO wage_tables (union_name, agreement, grade, start_salary,
                year_1_salary, year_3_salary, year_5_salary, effective_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (union_name, grade, effective_date) DO UPDATE SET
                start_salary = excluded.start_salary,
                year_1_salary = excluded.year_1_salary,
                year_3_salary = excluded.year_3_salary,
                year_5_salary = excluded.year_5_salary
        """, (g["union"], g.get("agreement"), g["grade"], g["start"],
              g.get("year_1"), g.get("year_3"), g.get("year_5"), g.get("effective_date")))
        saved_grades += 1

    saved_mappings = 0
    for m in mappings:
        cursor.execute("""
            INSERT INTO wage_grade_mappings (grade, job_title)
            VALUES (?, ?)
            ON CONFLICT (grade, job_title) DO NOTHING
        """, (m["grade"], m["title"]))
        saved_mappings += 1

    conn.commit()
    conn.close()
    return saved_grades, saved_mappings


def main():
    if not PDF_PATH.exists():
        print(f"PDF not found: {PDF_PATH}")
        print("Download from: https://www.asa.is/images/stories/KjaramalPdf/Kauptaxtar.pdf")
        sys.exit(1)

    init_db()
    create_tables()

    pdf = pdfplumber.open(str(PDF_PATH))

    print("Parsing wage grades...")
    grades = parse_wage_grades(pdf)
    print(f"  Found {len(grades)} grade entries")

    print("Parsing job mappings...")
    mappings = parse_job_mappings(pdf)
    print(f"  Found {len(mappings)} job-to-grade mappings")

    pdf.close()

    print("Saving to database...")
    sg, sm = save_data(grades, mappings)
    print(f"  Saved {sg} wage grades, {sm} job mappings")

    # Print summary
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT union_name, COUNT(*), MIN(start_salary), MAX(start_salary) FROM wage_tables GROUP BY union_name")
    print("\nWage table summary:")
    for r in cursor.fetchall():
        print(f"  {r[0]:15s}: {r[1]:3d} grades, {r[2]:>10,}-{r[3]:>10,} kr/mo")

    cursor.execute("SELECT COUNT(*) FROM wage_grade_mappings")
    print(f"\nJob-to-grade mappings: {cursor.fetchone()[0]}")

    # Show some examples
    cursor.execute("""
        SELECT m.job_title, m.grade, w.start_salary, w.year_5_salary
        FROM wage_grade_mappings m
        JOIN wage_tables w ON m.grade = w.grade AND w.union_name = 'AFL/SGS'
        LIMIT 10
    """)
    print("\nExample mappings:")
    for r in cursor.fetchall():
        print(f"  {r[0][:40]:40s} grade={r[1]:2d}  {r[2]:>8,}-{r[3]:>8,} kr/mo")

    conn.close()


if __name__ == "__main__":
    main()
