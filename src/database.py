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


def _column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


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


@dataclass
class VRSalarySurvey:
    id: Optional[int]
    survey_date: str
    starfsheiti: str
    starfsstett: Optional[str]
    medaltal: int
    midgildi: Optional[int]
    p25: Optional[int]
    p75: Optional[int]
    fjoldi_svara: Optional[int]
    source_pdf: str
    extracted_at: datetime


@dataclass
class ScrapeLogEntry:
    id: Optional[int]
    source: str
    identifier: str
    year: Optional[int]
    status: str
    pdf_path: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime


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

    # --- V2 Schema Extensions ---

    # Add new columns to companies (SQLite has no IF NOT EXISTS for ALTER TABLE)
    for col, col_type in [
        ("address", "TEXT"),
        ("legal_form", "TEXT"),
        ("sector", "TEXT"),
        ("employee_count_latest", "INTEGER"),
        ("updated_at", "DATETIME"),
    ]:
        if not _column_exists(cursor, "companies", col):
            cursor.execute(f"ALTER TABLE companies ADD COLUMN {col} {col_type}")

    # Add new columns to annual_reports
    for col, col_def in [
        ("hagnadur", "INTEGER"),
        ("rekstrarkostnadur", "INTEGER"),
        ("eiginfjarhlufall", "REAL"),
        ("laun_hlutfall_tekna", "REAL"),
        ("source_type", "TEXT DEFAULT 'pdf'"),
        ("confidence", "REAL DEFAULT 1.0"),
        ("is_sample", "BOOLEAN DEFAULT 0"),
    ]:
        if not _column_exists(cursor, "annual_reports", col):
            cursor.execute(f"ALTER TABLE annual_reports ADD COLUMN {col} {col_def}")

    # New tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vr_salary_surveys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            survey_date TEXT NOT NULL,
            starfsheiti TEXT NOT NULL,
            starfsstett TEXT,
            medaltal INTEGER NOT NULL,
            midgildi INTEGER,
            p25 INTEGER,
            p75 INTEGER,
            fjoldi_svara INTEGER,
            source_pdf TEXT NOT NULL,
            extracted_at DATETIME NOT NULL,
            UNIQUE(survey_date, starfsheiti)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scrape_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            identifier TEXT NOT NULL,
            year INTEGER,
            status TEXT NOT NULL CHECK(status IN ('pending', 'downloaded', 'extracted', 'failed')),
            pdf_path TEXT,
            error_message TEXT,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            UNIQUE(source, identifier, year)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS data_flags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            record_id INTEGER NOT NULL,
            flag_type TEXT NOT NULL CHECK(flag_type IN ('sample_data', 'low_confidence', 'outlier', 'stale')),
            message TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_annual_reports_year ON annual_reports(year)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_annual_reports_avg_salary ON annual_reports(avg_salary DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_companies_isat ON companies(isat_code)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_companies_sector ON companies(sector)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vr_surveys_date ON vr_salary_surveys(survey_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vr_surveys_stett ON vr_salary_surveys(starfsstett)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_scrape_log_status ON scrape_log(status)")

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
    tekjur: Optional[int] = None,
    hagnadur: Optional[int] = None,
    rekstrarkostnadur: Optional[int] = None,
    eiginfjarhlufall: Optional[float] = None,
    source_type: str = 'pdf',
    confidence: float = 1.0
) -> int:
    """Save or update annual report. Returns report ID."""
    conn = get_connection()
    cursor = conn.cursor()

    avg_salary = int(launakostnadur / starfsmenn) if starfsmenn > 0 else 0
    laun_hlutfall_tekna = launakostnadur / tekjur if tekjur and tekjur > 0 else None

    cursor.execute("""
        INSERT INTO annual_reports
            (company_id, year, launakostnadur, starfsmenn, tekjur, avg_salary,
             source_pdf, extracted_at, hagnadur, rekstrarkostnadur,
             eiginfjarhlufall, laun_hlutfall_tekna, source_type, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (company_id, year) DO UPDATE SET
            launakostnadur = excluded.launakostnadur,
            starfsmenn = excluded.starfsmenn,
            tekjur = excluded.tekjur,
            avg_salary = excluded.avg_salary,
            source_pdf = excluded.source_pdf,
            extracted_at = excluded.extracted_at,
            hagnadur = excluded.hagnadur,
            rekstrarkostnadur = excluded.rekstrarkostnadur,
            eiginfjarhlufall = excluded.eiginfjarhlufall,
            laun_hlutfall_tekna = excluded.laun_hlutfall_tekna,
            source_type = excluded.source_type,
            confidence = excluded.confidence
    """, (company_id, year, launakostnadur, starfsmenn, tekjur, avg_salary,
          source_pdf, datetime.now(), hagnadur, rekstrarkostnadur,
          eiginfjarhlufall, laun_hlutfall_tekna, source_type, confidence))

    report_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return report_id


def get_ranked_companies(
    year: Optional[int] = None,
    limit: int = 100,
    sector: Optional[str] = None,
    isat_prefix: Optional[str] = None,
    exclude_sample: bool = True
):
    """Get companies ranked by average salary."""
    conn = get_connection()
    cursor = conn.cursor()

    where_clauses = []
    params = []

    if year:
        where_clauses.append("ar.year = ?")
        params.append(year)
    else:
        where_clauses.append("""ar.year = (
            SELECT MAX(ar2.year) FROM annual_reports ar2 WHERE ar2.company_id = c.id
        )""")

    if sector:
        where_clauses.append("c.sector = ?")
        params.append(sector)

    if isat_prefix:
        where_clauses.append("c.isat_code LIKE ?")
        params.append(f"{isat_prefix}%")

    if exclude_sample:
        where_clauses.append("(ar.is_sample = 0 OR ar.is_sample IS NULL)")

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    params.append(limit)

    cursor.execute(f"""
        SELECT
            c.id, c.kennitala, c.name, c.isat_code,
            ar.year, ar.launakostnadur, ar.starfsmenn, ar.avg_salary, ar.tekjur
        FROM companies c
        JOIN annual_reports ar ON c.id = ar.company_id
        WHERE {where_sql}
        ORDER BY ar.avg_salary DESC
        LIMIT ?
    """, params)

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


def get_company_financials(company_id: int) -> dict:
    """Returns company with all annual reports including new fields, plus trends."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
    company = cursor.fetchone()
    if not company:
        conn.close()
        return {}

    cursor.execute("""
        SELECT * FROM annual_reports
        WHERE company_id = ?
        ORDER BY year ASC
    """, (company_id,))
    reports = cursor.fetchall()
    conn.close()

    reports_list = [dict(r) for r in reports]
    trends = {}

    if len(reports_list) >= 2:
        first = reports_list[0]
        last = reports_list[-1]
        n_years = last["year"] - first["year"]
        if n_years > 0:
            if first["avg_salary"] and first["avg_salary"] > 0 and last["avg_salary"]:
                trends["salary_cagr"] = round(
                    (last["avg_salary"] / first["avg_salary"]) ** (1 / n_years) - 1, 4
                )
            if (first.get("tekjur") and first["tekjur"] > 0
                    and last.get("tekjur") and last["tekjur"] > 0):
                trends["revenue_cagr"] = round(
                    (last["tekjur"] / first["tekjur"]) ** (1 / n_years) - 1, 4
                )

    return {
        "company": dict(company),
        "reports": reports_list,
        "trends": trends,
    }


def get_vr_surveys(
    category: Optional[str] = None,
    survey_date: Optional[str] = None
) -> list[dict]:
    """Get VR salary survey data, optionally filtered by starfsstett or survey_date."""
    conn = get_connection()
    cursor = conn.cursor()

    where_clauses = []
    params = []

    if category:
        where_clauses.append("starfsstett = ?")
        params.append(category)
    if survey_date:
        where_clauses.append("survey_date = ?")
        params.append(survey_date)

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    cursor.execute(f"""
        SELECT * FROM vr_salary_surveys
        WHERE {where_sql}
        ORDER BY survey_date DESC, medaltal DESC
    """, params)

    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_vr_categories() -> list[str]:
    """Get distinct starfsstett values from VR surveys."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT starfsstett FROM vr_salary_surveys
        WHERE starfsstett IS NOT NULL
        ORDER BY starfsstett
    """)
    categories = [row["starfsstett"] for row in cursor.fetchall()]
    conn.close()
    return categories


def get_salary_comparison(company_id: int) -> dict:
    """Compare company avg salary to VR survey data. Returns comparison dict."""
    conn = get_connection()
    cursor = conn.cursor()

    # Get the most recent annual report for this company
    cursor.execute("""
        SELECT ar.avg_salary, ar.year FROM annual_reports ar
        WHERE ar.company_id = ?
        ORDER BY ar.year DESC LIMIT 1
    """, (company_id,))
    report = cursor.fetchone()
    if not report:
        conn.close()
        return {"error": "No annual report found for company"}

    company_avg = report["avg_salary"]
    report_year = report["year"]

    # Get VR survey averages (most recent survey date)
    cursor.execute("""
        SELECT survey_date, AVG(medaltal) as vr_avg, MIN(medaltal) as vr_min,
               MAX(medaltal) as vr_max, COUNT(*) as survey_count
        FROM vr_salary_surveys
        GROUP BY survey_date
        ORDER BY survey_date DESC
        LIMIT 1
    """)
    vr_row = cursor.fetchone()
    conn.close()

    if not vr_row:
        return {
            "company_avg_salary": company_avg,
            "report_year": report_year,
            "vr_data": None,
            "message": "No VR survey data available for comparison",
        }

    vr_avg = vr_row["vr_avg"]
    diff_pct = round((company_avg - vr_avg) / vr_avg * 100, 1) if vr_avg else None

    return {
        "company_avg_salary": company_avg,
        "report_year": report_year,
        "vr_survey_date": vr_row["survey_date"],
        "vr_avg": round(vr_avg) if vr_avg else None,
        "vr_min": vr_row["vr_min"],
        "vr_max": vr_row["vr_max"],
        "vr_survey_count": vr_row["survey_count"],
        "diff_pct": diff_pct,
    }


def get_platform_stats() -> dict:
    """Total companies, reports, VR surveys, scrape log entries, sources, coverage."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as cnt FROM companies")
    total_companies = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(*) as cnt FROM annual_reports")
    total_reports = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(*) as cnt FROM vr_salary_surveys")
    total_vr_surveys = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(*) as cnt FROM scrape_log")
    total_scrape_entries = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(DISTINCT source) as cnt FROM scrape_log")
    total_sources = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(DISTINCT source_pdf) as cnt FROM annual_reports")
    report_sources = cursor.fetchone()["cnt"]

    cursor.execute("SELECT MIN(year) as min_y, MAX(year) as max_y FROM annual_reports")
    year_row = cursor.fetchone()
    year_range = (year_row["min_y"], year_row["max_y"]) if year_row["min_y"] else (None, None)

    conn.close()

    return {
        "total_companies": total_companies,
        "total_reports": total_reports,
        "total_vr_surveys": total_vr_surveys,
        "total_scrape_entries": total_scrape_entries,
        "total_sources": total_sources,
        "report_sources": report_sources,
        "year_range": year_range,
    }


def save_vr_survey(survey: VRSalarySurvey) -> int:
    """Insert or update VR survey record (UPSERT on survey_date + starfsheiti)."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO vr_salary_surveys
            (survey_date, starfsheiti, starfsstett, medaltal, midgildi, p25, p75,
             fjoldi_svara, source_pdf, extracted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (survey_date, starfsheiti) DO UPDATE SET
            starfsstett = excluded.starfsstett,
            medaltal = excluded.medaltal,
            midgildi = excluded.midgildi,
            p25 = excluded.p25,
            p75 = excluded.p75,
            fjoldi_svara = excluded.fjoldi_svara,
            source_pdf = excluded.source_pdf,
            extracted_at = excluded.extracted_at
    """, (survey.survey_date, survey.starfsheiti, survey.starfsstett,
          survey.medaltal, survey.midgildi, survey.p25, survey.p75,
          survey.fjoldi_svara, survey.source_pdf, survey.extracted_at))

    survey_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return survey_id


def save_scrape_log(entry: ScrapeLogEntry) -> int:
    """Insert or update scrape log entry (UPSERT on source + identifier + year)."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO scrape_log
            (source, identifier, year, status, pdf_path, error_message, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (source, identifier, year) DO UPDATE SET
            status = excluded.status,
            pdf_path = excluded.pdf_path,
            error_message = excluded.error_message,
            updated_at = excluded.updated_at
    """, (entry.source, entry.identifier, entry.year, entry.status,
          entry.pdf_path, entry.error_message, entry.created_at, entry.updated_at))

    entry_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return entry_id


def get_pending_scrapes(source: str) -> list[ScrapeLogEntry]:
    """Get all entries with status='pending' for a source."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM scrape_log
        WHERE source = ? AND status = 'pending'
        ORDER BY created_at ASC
    """, (source,))

    rows = cursor.fetchall()
    conn.close()

    return [
        ScrapeLogEntry(
            id=row["id"],
            source=row["source"],
            identifier=row["identifier"],
            year=row["year"],
            status=row["status"],
            pdf_path=row["pdf_path"],
            error_message=row["error_message"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def bulk_create_companies(
    items: list[dict],
) -> dict:
    """Create multiple companies in a single transaction.

    Each item should have: kennitala, name, and optionally isat_code.
    Returns {"created": count, "errors": [{"index": i, "error": msg}, ...]}.
    """
    conn = get_connection()
    cursor = conn.cursor()
    created = 0
    errors = []

    try:
        for i, item in enumerate(items):
            try:
                kennitala = item["kennitala"]
                name = item["name"]
                isat_code = item.get("isat_code")

                cursor.execute(
                    "SELECT id FROM companies WHERE kennitala = ?", (kennitala,)
                )
                existing = cursor.fetchone()
                if existing:
                    errors.append({"index": i, "kennitala": kennitala, "error": f"Company with kennitala {kennitala} already exists"})
                    continue

                cursor.execute(
                    "INSERT INTO companies (kennitala, name, isat_code) VALUES (?, ?, ?)",
                    (kennitala, name, isat_code),
                )
                created += 1
            except KeyError as e:
                errors.append({"index": i, "error": f"Missing required field: {e}"})
            except Exception as e:
                errors.append({"index": i, "error": str(e)})

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {"created": created, "errors": errors}


def bulk_delete_companies(ids: list[int]) -> dict:
    """Delete multiple companies by ID in a single transaction.

    Also deletes associated annual_reports (cascade).
    Returns {"deleted": count, "errors": [{"index": i, "error": msg}, ...]}.
    """
    conn = get_connection()
    cursor = conn.cursor()
    deleted = 0
    errors = []

    try:
        for i, company_id in enumerate(ids):
            try:
                cursor.execute("SELECT id FROM companies WHERE id = ?", (company_id,))
                if not cursor.fetchone():
                    errors.append({"index": i, "id": company_id, "error": f"Company {company_id} not found"})
                    continue

                cursor.execute(
                    "DELETE FROM annual_reports WHERE company_id = ?", (company_id,)
                )
                cursor.execute("DELETE FROM companies WHERE id = ?", (company_id,))
                deleted += 1
            except Exception as e:
                errors.append({"index": i, "id": company_id, "error": str(e)})

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {"deleted": deleted, "errors": errors}


def bulk_create_reports(items: list[dict]) -> dict:
    """Create multiple annual reports in a single transaction.

    Each item should have: company_id, year, launakostnadur, starfsmenn, source_pdf.
    Optional: tekjur, hagnadur, rekstrarkostnadur, eiginfjarhlufall, source_type, confidence.
    Returns {"created": count, "errors": [{"index": i, "error": msg}, ...]}.
    """
    conn = get_connection()
    cursor = conn.cursor()
    created = 0
    errors = []

    try:
        for i, item in enumerate(items):
            try:
                company_id = item["company_id"]
                year = item["year"]
                launakostnadur = item["launakostnadur"]
                starfsmenn = item["starfsmenn"]
                source_pdf = item["source_pdf"]
                tekjur = item.get("tekjur")
                hagnadur = item.get("hagnadur")
                rekstrarkostnadur = item.get("rekstrarkostnadur")
                eiginfjarhlufall = item.get("eiginfjarhlufall")
                source_type = item.get("source_type", "pdf")
                confidence = item.get("confidence", 1.0)

                # Validate company exists
                cursor.execute(
                    "SELECT id FROM companies WHERE id = ?", (company_id,)
                )
                if not cursor.fetchone():
                    errors.append({"index": i, "error": f"Company {company_id} not found"})
                    continue

                if starfsmenn <= 0:
                    errors.append({"index": i, "error": "starfsmenn must be > 0"})
                    continue

                avg_salary = int(launakostnadur / starfsmenn)
                laun_hlutfall_tekna = (
                    launakostnadur / tekjur if tekjur and tekjur > 0 else None
                )

                cursor.execute(
                    """INSERT INTO annual_reports
                        (company_id, year, launakostnadur, starfsmenn, tekjur, avg_salary,
                         source_pdf, extracted_at, hagnadur, rekstrarkostnadur,
                         eiginfjarhlufall, laun_hlutfall_tekna, source_type, confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (company_id, year) DO UPDATE SET
                        launakostnadur = excluded.launakostnadur,
                        starfsmenn = excluded.starfsmenn,
                        tekjur = excluded.tekjur,
                        avg_salary = excluded.avg_salary,
                        source_pdf = excluded.source_pdf,
                        extracted_at = excluded.extracted_at,
                        hagnadur = excluded.hagnadur,
                        rekstrarkostnadur = excluded.rekstrarkostnadur,
                        eiginfjarhlufall = excluded.eiginfjarhlufall,
                        laun_hlutfall_tekna = excluded.laun_hlutfall_tekna,
                        source_type = excluded.source_type,
                        confidence = excluded.confidence
                    """,
                    (
                        company_id, year, launakostnadur, starfsmenn, tekjur,
                        avg_salary, source_pdf, datetime.now(), hagnadur,
                        rekstrarkostnadur, eiginfjarhlufall, laun_hlutfall_tekna,
                        source_type, confidence,
                    ),
                )
                created += 1
            except KeyError as e:
                errors.append({"index": i, "error": f"Missing required field: {e}"})
            except Exception as e:
                errors.append({"index": i, "error": str(e)})

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {"created": created, "errors": errors}


def bulk_delete_reports(ids: list[int]) -> dict:
    """Delete multiple annual reports by ID in a single transaction.

    Returns {"deleted": count, "errors": [{"index": i, "error": msg}, ...]}.
    """
    conn = get_connection()
    cursor = conn.cursor()
    deleted = 0
    errors = []

    try:
        for i, report_id in enumerate(ids):
            try:
                cursor.execute(
                    "SELECT id FROM annual_reports WHERE id = ?", (report_id,)
                )
                if not cursor.fetchone():
                    errors.append({"index": i, "id": report_id, "error": f"Report {report_id} not found"})
                    continue

                cursor.execute(
                    "DELETE FROM annual_reports WHERE id = ?", (report_id,)
                )
                deleted += 1
            except Exception as e:
                errors.append({"index": i, "id": report_id, "error": str(e)})

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {"deleted": deleted, "errors": errors}


def flag_sample_data() -> int:
    """Mark all annual_reports where source_pdf='sample_data' with is_sample=1. Returns count."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE annual_reports SET is_sample = 1
        WHERE source_pdf = 'sample_data'
    """)

    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count


def delete_sample_data() -> tuple[int, int]:
    """Delete reports where is_sample=1, then delete companies with no remaining reports.
    Returns (reports_deleted, companies_deleted)."""
    conn = get_connection()
    cursor = conn.cursor()

    # Delete sample reports
    cursor.execute("DELETE FROM annual_reports WHERE is_sample = 1")
    reports_deleted = cursor.rowcount

    # Delete orphaned companies (no remaining reports)
    cursor.execute("""
        DELETE FROM companies
        WHERE id NOT IN (SELECT DISTINCT company_id FROM annual_reports)
    """)
    companies_deleted = cursor.rowcount

    conn.commit()
    conn.close()
    return (reports_deleted, companies_deleted)


# Initialize database on import
init_db()
