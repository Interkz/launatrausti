import sqlite3
import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

# Handle Vercel's read-only filesystem
# On Vercel, we copy the bundled database to /tmp for read access
BUNDLED_DB = Path(__file__).parent.parent / "launatrausti.db"

if os.environ.get("VERCEL"):
    DB_PATH = Path("/tmp/launatrausti.db")
    # Copy bundled database to /tmp if it doesn't exist
    if not DB_PATH.exists() and BUNDLED_DB.exists():
        shutil.copy(BUNDLED_DB, DB_PATH)
else:
    DB_PATH = BUNDLED_DB


@dataclass
class Company:
    id: Optional[int]
    kennitala: str
    name: str
    isat_code: Optional[str] = None


@dataclass
class AnnualReport:
    id: Optional[int]
    company_id: int
    year: int
    launakostnadur: int  # Total wage costs in ISK
    starfsmenn: float  # Average employee count
    tekjur: Optional[int]  # Revenue in ISK
    avg_salary: int  # Calculated: launakostnadur / starfsmenn
    source_pdf: str
    extracted_at: datetime


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kennitala TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            isat_code TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS annual_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            year INTEGER NOT NULL,
            launakostnadur INTEGER NOT NULL,
            starfsmenn REAL NOT NULL,
            tekjur INTEGER,
            avg_salary INTEGER NOT NULL,
            source_pdf TEXT NOT NULL,
            extracted_at DATETIME NOT NULL,
            FOREIGN KEY (company_id) REFERENCES companies (id),
            UNIQUE (company_id, year)
        )
    """)

    conn.commit()
    conn.close()


def get_or_create_company(kennitala: str, name: str, isat_code: Optional[str] = None) -> int:
    """Get existing company or create new one. Returns company ID."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM companies WHERE kennitala = ?", (kennitala,))
    row = cursor.fetchone()

    if row:
        company_id = row["id"]
        # Update name if changed
        cursor.execute(
            "UPDATE companies SET name = ?, isat_code = COALESCE(?, isat_code) WHERE id = ?",
            (name, isat_code, company_id)
        )
    else:
        cursor.execute(
            "INSERT INTO companies (kennitala, name, isat_code) VALUES (?, ?, ?)",
            (kennitala, name, isat_code)
        )
        company_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return company_id


def save_annual_report(
    company_id: int,
    year: int,
    launakostnadur: int,
    starfsmenn: float,
    source_pdf: str,
    tekjur: Optional[int] = None
) -> int:
    """Save or update annual report. Returns report ID."""
    conn = get_connection()
    cursor = conn.cursor()

    avg_salary = int(launakostnadur / starfsmenn) if starfsmenn > 0 else 0

    cursor.execute("""
        INSERT INTO annual_reports
            (company_id, year, launakostnadur, starfsmenn, tekjur, avg_salary, source_pdf, extracted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (company_id, year) DO UPDATE SET
            launakostnadur = excluded.launakostnadur,
            starfsmenn = excluded.starfsmenn,
            tekjur = excluded.tekjur,
            avg_salary = excluded.avg_salary,
            source_pdf = excluded.source_pdf,
            extracted_at = excluded.extracted_at
    """, (company_id, year, launakostnadur, starfsmenn, tekjur, avg_salary, source_pdf, datetime.now()))

    report_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return report_id


def get_ranked_companies(year: Optional[int] = None, limit: int = 100):
    """Get companies ranked by average salary."""
    conn = get_connection()
    cursor = conn.cursor()

    if year:
        cursor.execute("""
            SELECT
                c.id, c.kennitala, c.name, c.isat_code,
                ar.year, ar.launakostnadur, ar.starfsmenn, ar.avg_salary, ar.tekjur
            FROM companies c
            JOIN annual_reports ar ON c.id = ar.company_id
            WHERE ar.year = ?
            ORDER BY ar.avg_salary DESC
            LIMIT ?
        """, (year, limit))
    else:
        # Get most recent report per company
        cursor.execute("""
            SELECT
                c.id, c.kennitala, c.name, c.isat_code,
                ar.year, ar.launakostnadur, ar.starfsmenn, ar.avg_salary, ar.tekjur
            FROM companies c
            JOIN annual_reports ar ON c.id = ar.company_id
            WHERE ar.year = (
                SELECT MAX(ar2.year) FROM annual_reports ar2 WHERE ar2.company_id = c.id
            )
            ORDER BY ar.avg_salary DESC
            LIMIT ?
        """, (limit,))

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_company_detail(company_id: int):
    """Get company with all annual reports."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
    company = cursor.fetchone()

    if not company:
        conn.close()
        return None

    cursor.execute("""
        SELECT * FROM annual_reports
        WHERE company_id = ?
        ORDER BY year DESC
    """, (company_id,))
    reports = cursor.fetchall()

    conn.close()

    return {
        "company": dict(company),
        "reports": [dict(r) for r in reports]
    }


def get_available_years():
    """Get list of years with data."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT year FROM annual_reports ORDER BY year DESC")
    years = [row["year"] for row in cursor.fetchall()]
    conn.close()
    return years


# Initialize database on import
init_db()
