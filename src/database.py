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


@dataclass
class JobListing:
    id: Optional[int]
    source: str
    source_id: Optional[str]
    title: str
    employer_name: str
    company_id: Optional[int] = None
    location: Optional[str] = None
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None
    employment_type: Optional[str] = None
    description_raw: Optional[str] = None
    source_url: Optional[str] = None
    posted_date: Optional[str] = None
    deadline: Optional[str] = None
    work_hours: Optional[str] = None
    remote_policy: Optional[str] = None
    salary_text: Optional[str] = None
    salary_lower: Optional[int] = None
    salary_upper: Optional[int] = None
    benefits: Optional[str] = None
    union_name: Optional[str] = None
    languages: Optional[str] = None
    education_required: Optional[str] = None
    experience_years: Optional[str] = None
    estimated_salary: Optional[int] = None
    salary_source: Optional[str] = None
    salary_confidence: Optional[float] = None
    salary_details: Optional[str] = None
    extracted_at: Optional[str] = None
    employer_logo: Optional[str] = None
    is_active: bool = True


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
            status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'downloaded', 'extracted', 'success', 'not_found', 'already_exists', 'failed')),
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hagstofa_occupations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            isco_code TEXT NOT NULL,
            occupation_name TEXT NOT NULL,
            year INTEGER NOT NULL,
            mean INTEGER,
            median INTEGER,
            p25 INTEGER,
            p75 INTEGER,
            observation_count INTEGER,
            source TEXT DEFAULT 'hagstofa_vin02001',
            fetched_at DATETIME NOT NULL,
            salary_type TEXT DEFAULT 'heildarlaun',
            UNIQUE(isco_code, year, salary_type)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            source_id TEXT,
            title TEXT NOT NULL,
            employer_name TEXT NOT NULL,
            company_id INTEGER,
            location TEXT,
            location_lat REAL,
            location_lon REAL,
            employment_type TEXT,
            description_raw TEXT,
            source_url TEXT,
            posted_date TEXT,
            deadline TEXT,
            work_hours TEXT,
            remote_policy TEXT,
            salary_text TEXT,
            salary_lower INTEGER,
            salary_upper INTEGER,
            benefits TEXT,
            union_name TEXT,
            languages TEXT,
            education_required TEXT,
            experience_years TEXT,
            estimated_salary INTEGER,
            salary_source TEXT,
            salary_confidence REAL,
            salary_details TEXT,
            extracted_at TEXT,
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT (datetime('now')),
            updated_at DATETIME DEFAULT (datetime('now')),
            UNIQUE(source, source_id)
        )
    """)

    # Add employer_logo column to job_listings
    if not _column_exists(cursor, "job_listings", "employer_logo"):
        cursor.execute("ALTER TABLE job_listings ADD COLUMN employer_logo TEXT")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS unions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            name_en TEXT,
            federation TEXT,
            website TEXT,
            sector TEXT,
            members INTEGER,
            fee_pct REAL,
            sick_fund_pct REAL,
            holiday_fund_pct REAL,
            education_fund_pct REAL,
            rehab_fund_pct REAL,
            employer_pension_pct REAL,
            employee_pension_pct REAL,
            sick_pay_pct REAL,
            sick_pay_days INTEGER,
            holiday_homes INTEGER,
            education_grants INTEGER,
            death_benefit INTEGER,
            description TEXT,
            benefits_summary TEXT,
            wage_agreement_period TEXT,
            min_wage INTEGER,
            updated_at DATETIME DEFAULT (datetime('now'))
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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_hagstofa_occ_name ON hagstofa_occupations(occupation_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_hagstofa_occ_year ON hagstofa_occupations(year)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_hagstofa_occ_code ON hagstofa_occupations(isco_code)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_company ON job_listings(company_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_active ON job_listings(is_active)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_source ON job_listings(source)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_deadline ON job_listings(deadline)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_salary ON job_listings(estimated_salary)")

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

    # Exclude budget line items with fewer than 3 employees
    where_clauses.append("ar.starfsmenn >= 3")

    # Exclude government budget categories that aren't real employers
    budget_lines = [
        "Ýmis verkefni", "Ýmis framlög%", "Kosningar",
        "Heilbrigðismál, ýmis%", "Varnarmál", "Alþjóðleg þróunarsamvinna",
    ]
    for pattern in budget_lines:
        if "%" in pattern:
            where_clauses.append("c.name NOT LIKE ?")
        else:
            where_clauses.append("c.name != ?")
        params.append(pattern)

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    params.append(limit)

    cursor.execute(f"""
        SELECT
            c.id, c.kennitala, c.name, c.isat_code, c.sector,
            ar.year, ar.launakostnadur, ar.starfsmenn, ar.avg_salary, ar.tekjur,
            ar.source_pdf, ar.source_type
        FROM companies c
        JOIN annual_reports ar ON c.id = ar.company_id
        WHERE {where_sql}
        ORDER BY ar.avg_salary DESC
        LIMIT ?
    """, params)

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_companies_near_salary(target_monthly: int, window: int = 100000, limit: int = 10):
    """Get companies whose avg monthly salary is near the target."""
    conn = get_connection()
    cursor = conn.cursor()

    target_annual = target_monthly * 12
    low = target_annual - (window * 12)
    high = target_annual + (window * 12)

    cursor.execute("""
        SELECT
            c.id, c.kennitala, c.name, c.isat_code, c.sector,
            ar.year, ar.starfsmenn, ar.avg_salary,
            ar.avg_salary / 12 as monthly_salary,
            ABS(ar.avg_salary / 12 - ?) as distance
        FROM companies c
        JOIN annual_reports ar ON c.id = ar.company_id
            AND ar.year = (SELECT MAX(ar2.year) FROM annual_reports ar2 WHERE ar2.company_id = c.id)
        WHERE ar.avg_salary BETWEEN ? AND ?
            AND ar.starfsmenn >= 3
            AND (ar.is_sample = 0 OR ar.is_sample IS NULL)
            AND c.name NOT IN ('Ýmis verkefni', 'Varnarmál', 'Kosningar', 'Alþjóðleg þróunarsamvinna')
            AND c.name NOT LIKE 'Ýmis framlög%'
            AND c.name NOT LIKE 'Heilbrigðismál, ýmis%'
        ORDER BY distance ASC
        LIMIT ?
    """, (target_monthly, low, high, limit))

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


ISCO_MAJOR_GROUPS = {
    "1": "Stjórnendur",
    "2": "Sérfræðistörf",
    "3": "Tæknar og sérmenntað starfsfólk",
    "4": "Skrifstofustörf",
    "5": "Þjónustu-, umönnunar- og sölustörf",
    "7": "Iðnaðarmenn og sérhæft iðnverkafólk",
    "8": "Véla- og vélgæslufólk",
    "9": "Ósérhæfð störf",
}

ISCO_MAJOR_GROUPS_EN = {
    "1": "Managers",
    "2": "Professionals",
    "3": "Technicians & Associate Professionals",
    "4": "Clerical Support",
    "5": "Service & Sales",
    "7": "Craft & Trade",
    "8": "Machine Operators",
    "9": "Elementary Occupations",
}


def get_all_occupations_grouped(year: int = 2024, sort_by: str = "median", salary_type: str = "heildarlaun") -> dict:
    """Get all occupations for a year, grouped by ISCO major category, sorted by sort_by."""
    conn = get_connection()
    cursor = conn.cursor()

    order_col = sort_by if sort_by in ("mean", "median", "p75", "p25") else "median"

    cursor.execute(f"""
        SELECT isco_code, occupation_name, year, mean, median, p25, p75, observation_count, salary_type
        FROM hagstofa_occupations
        WHERE year = ? AND {order_col} IS NOT NULL AND salary_type = ?
            AND LENGTH(REPLACE(REPLACE(isco_code, '*', ''), ' ', '')) >= 4
        ORDER BY {order_col} DESC
    """, (year, salary_type))

    rows = cursor.fetchall()
    conn.close()

    groups = {}
    for row in rows:
        r = dict(row)
        code = r["isco_code"].strip()
        first_char = code[0] if code else "?"
        # Map non-ISCO codes to "other"
        if first_char not in ISCO_MAJOR_GROUPS:
            first_char = "other"

        if first_char not in groups:
            groups[first_char] = []
        groups[first_char].append(r)

    return groups


def get_all_occupations_flat(year: int = 2024, sort_by: str = "median", salary_type: str = "heildarlaun") -> list[dict]:
    """Get all occupations for a year as a flat sorted list."""
    conn = get_connection()
    cursor = conn.cursor()

    order_col = sort_by if sort_by in ("mean", "median", "p75", "p25") else "median"

    cursor.execute(f"""
        SELECT isco_code, occupation_name, year, mean, median, p25, p75, observation_count, salary_type
        FROM hagstofa_occupations
        WHERE year = ? AND {order_col} IS NOT NULL AND salary_type = ?
            AND LENGTH(REPLACE(REPLACE(isco_code, '*', ''), ' ', '')) >= 4
        ORDER BY {order_col} DESC
    """, (year, salary_type))

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def search_occupations(query: str = "", year: int = 2024, limit: int = 20, salary_type: str = "heildarlaun") -> list[dict]:
    """Search occupations by name. Returns matching occupations with salary stats."""
    conn = get_connection()
    cursor = conn.cursor()

    if query:
        cursor.execute("""
            SELECT isco_code, occupation_name, year, mean, median, p25, p75, observation_count
            FROM hagstofa_occupations
            WHERE occupation_name LIKE ? AND year = ? AND salary_type = ?
                AND LENGTH(REPLACE(REPLACE(isco_code, '*', ''), ' ', '')) >= 4
            ORDER BY mean DESC
            LIMIT ?
        """, (f"%{query}%", year, salary_type, limit))
    else:
        cursor.execute("""
            SELECT isco_code, occupation_name, year, mean, median, p25, p75, observation_count
            FROM hagstofa_occupations
            WHERE year = ? AND salary_type = ?
                AND LENGTH(REPLACE(REPLACE(isco_code, '*', ''), ' ', '')) >= 4
            ORDER BY mean DESC
            LIMIT ?
        """, (year, salary_type, limit))

    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_occupation_detail(isco_code: str, salary_type: str = "heildarlaun") -> list[dict]:
    """Get all years of data for a specific occupation."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT isco_code, occupation_name, year, mean, median, p25, p75, observation_count
        FROM hagstofa_occupations
        WHERE isco_code = ? AND salary_type = ?
        ORDER BY year DESC
    """, (isco_code, salary_type))

    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_occupation_categories() -> list[dict]:
    """Get distinct ISCO major groups (first digit) with counts."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            SUBSTR(isco_code, 1, 1) as major_group,
            COUNT(DISTINCT isco_code) as occupation_count,
            MIN(occupation_name) as example_name
        FROM hagstofa_occupations
        WHERE year = (SELECT MAX(year) FROM hagstofa_occupations)
        GROUP BY SUBSTR(isco_code, 1, 1)
        ORDER BY major_group
    """)

    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_occupation_years() -> list[int]:
    """Get available years for occupation data."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT year FROM hagstofa_occupations ORDER BY year DESC")
    years = [row["year"] for row in cursor.fetchall()]
    conn.close()
    return years


def save_hagstofa_occupation(
    isco_code: str, occupation_name: str, year: int,
    mean: int = None, median: int = None,
    p25: int = None, p75: int = None,
    observation_count: int = None,
    salary_type: str = "heildarlaun"
) -> int:
    """Save or update a Hagstofa occupation record."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO hagstofa_occupations
            (isco_code, occupation_name, year, mean, median, p25, p75,
             observation_count, salary_type, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (isco_code, year, salary_type) DO UPDATE SET
            occupation_name = excluded.occupation_name,
            mean = excluded.mean,
            median = excluded.median,
            p25 = excluded.p25,
            p75 = excluded.p75,
            observation_count = excluded.observation_count,
            fetched_at = excluded.fetched_at
    """, (isco_code, occupation_name, year, mean, median, p25, p75,
          observation_count, salary_type, datetime.now()))

    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return record_id


def save_job_listing(listing: JobListing) -> int:
    """Insert or update job listing (UPSERT on source + source_id).
    On conflict, updates basic info but preserves extracted fields and existing company_id."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO job_listings
            (source, source_id, title, employer_name, company_id, location,
             location_lat, location_lon, employment_type, description_raw,
             source_url, posted_date, deadline, work_hours, remote_policy,
             salary_text, salary_lower, salary_upper, benefits, union_name,
             languages, education_required, experience_years,
             estimated_salary, salary_source, salary_confidence, salary_details,
             extracted_at, employer_logo, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (source, source_id) DO UPDATE SET
            title = excluded.title,
            employer_name = excluded.employer_name,
            company_id = COALESCE(excluded.company_id, job_listings.company_id),
            location = excluded.location,
            location_lat = excluded.location_lat,
            location_lon = excluded.location_lon,
            employment_type = excluded.employment_type,
            description_raw = excluded.description_raw,
            source_url = excluded.source_url,
            posted_date = excluded.posted_date,
            deadline = excluded.deadline,
            work_hours = excluded.work_hours,
            remote_policy = excluded.remote_policy,
            salary_text = excluded.salary_text,
            salary_lower = excluded.salary_lower,
            salary_upper = excluded.salary_upper,
            benefits = excluded.benefits,
            union_name = excluded.union_name,
            languages = excluded.languages,
            education_required = excluded.education_required,
            experience_years = excluded.experience_years,
            employer_logo = COALESCE(excluded.employer_logo, job_listings.employer_logo),
            is_active = excluded.is_active,
            updated_at = datetime('now')
    """, (listing.source, listing.source_id, listing.title, listing.employer_name,
          listing.company_id, listing.location, listing.location_lat, listing.location_lon,
          listing.employment_type, listing.description_raw, listing.source_url,
          listing.posted_date, listing.deadline, listing.work_hours, listing.remote_policy,
          listing.salary_text, listing.salary_lower, listing.salary_upper,
          listing.benefits, listing.union_name, listing.languages,
          listing.education_required, listing.experience_years,
          listing.estimated_salary, listing.salary_source, listing.salary_confidence,
          listing.salary_details, listing.extracted_at, listing.employer_logo,
          listing.is_active))

    job_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return job_id


def get_active_jobs(
    salary_min: Optional[int] = None,
    salary_max: Optional[int] = None,
    location: Optional[str] = None,
    employment_type: Optional[str] = None,
    remote_policy: Optional[str] = None,
    source: Optional[str] = None,
    company_id: Optional[int] = None,
    q: Optional[str] = None,
    sort: str = "salary",
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Get active job listings with optional filters and text search."""
    conn = get_connection()
    cursor = conn.cursor()

    where_clauses = ["jl.is_active = 1"]
    params = []

    if q:
        where_clauses.append("(jl.title LIKE ? OR jl.employer_name LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])

    if salary_min is not None:
        where_clauses.append("jl.estimated_salary >= ?")
        params.append(salary_min)
    if salary_max is not None:
        where_clauses.append("jl.estimated_salary <= ?")
        params.append(salary_max)
    if location:
        where_clauses.append("jl.location LIKE ?")
        params.append(f"%{location}%")
    if employment_type:
        where_clauses.append("jl.employment_type = ?")
        params.append(employment_type)
    if remote_policy:
        where_clauses.append("jl.remote_policy = ?")
        params.append(remote_policy)
    if source:
        where_clauses.append("jl.source = ?")
        params.append(source)
    if company_id is not None:
        where_clauses.append("jl.company_id = ?")
        params.append(company_id)

    where_sql = " AND ".join(where_clauses)
    params.extend([limit, offset])

    # Sort options
    sort_clauses = {
        "salary": "jl.estimated_salary IS NULL, jl.estimated_salary DESC",
        "salary_asc": "jl.estimated_salary IS NULL, jl.estimated_salary ASC",
        "date": "jl.posted_date IS NULL, jl.posted_date DESC",
        "employer": "jl.employer_name ASC",
        "deadline": "jl.deadline IS NULL, jl.deadline ASC",
    }
    order_by = sort_clauses.get(sort, sort_clauses["salary"])

    cursor.execute(f"""
        SELECT jl.*,
            c.name as company_name, c.isat_code, c.sector as company_sector,
            ar.avg_salary as company_avg_salary, ar.year as company_report_year,
            ar.starfsmenn as company_employees
        FROM job_listings jl
        LEFT JOIN companies c ON jl.company_id = c.id
        LEFT JOIN annual_reports ar ON c.id = ar.company_id
            AND ar.year = (SELECT MAX(ar2.year) FROM annual_reports ar2 WHERE ar2.company_id = c.id)
        WHERE {where_sql}
        ORDER BY {order_by}, jl.posted_date DESC
        LIMIT ? OFFSET ?
    """, params)

    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_company_jobs(company_id: int) -> list[dict]:
    """Get active job listings for a specific company."""
    return get_active_jobs(company_id=company_id, limit=100)


def get_job_by_id(job_id: int) -> Optional[dict]:
    """Get a single job listing with company cross-reference data."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT jl.*,
            c.name as company_name, c.isat_code, c.sector as company_sector,
            c.kennitala as company_kennitala,
            ar.avg_salary as company_avg_salary, ar.year as company_report_year,
            ar.starfsmenn as company_employees, ar.tekjur as company_revenue
        FROM job_listings jl
        LEFT JOIN companies c ON jl.company_id = c.id
        LEFT JOIN annual_reports ar ON c.id = ar.company_id
            AND ar.year = (SELECT MAX(ar2.year) FROM annual_reports ar2 WHERE ar2.company_id = c.id)
        WHERE jl.id = ?
    """, (job_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_related_jobs(employer_name: str, exclude_id: int, limit: int = 5) -> list[dict]:
    """Get other active jobs from the same employer."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, estimated_salary, salary_source, remote_policy,
               employment_type, deadline, employer_logo
        FROM job_listings
        WHERE employer_name = ? AND id != ? AND is_active = 1
        ORDER BY estimated_salary DESC NULLS LAST
        LIMIT ?
    """, (employer_name, exclude_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_job_filter_options() -> dict:
    """Get distinct values for job filter dropdowns."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT employment_type FROM job_listings
        WHERE is_active = 1 AND employment_type IS NOT NULL
        ORDER BY employment_type
    """)
    employment_types = [r["employment_type"] for r in cursor.fetchall()]

    cursor.execute("""
        SELECT location, COUNT(*) as cnt FROM job_listings
        WHERE is_active = 1 AND location IS NOT NULL AND location != ''
        GROUP BY location
        ORDER BY cnt DESC
        LIMIT 20
    """)
    locations = [{"name": r["location"], "count": r["cnt"]} for r in cursor.fetchall()]

    cursor.execute("""
        SELECT DISTINCT source FROM job_listings
        WHERE is_active = 1
        ORDER BY source
    """)
    sources = [r["source"] for r in cursor.fetchall()]

    conn.close()
    return {
        "employment_types": employment_types,
        "locations": locations,
        "sources": sources,
    }


def get_job_count(
    q: Optional[str] = None,
    salary_min: Optional[int] = None,
    salary_max: Optional[int] = None,
    location: Optional[str] = None,
    employment_type: Optional[str] = None,
    source: Optional[str] = None,
) -> int:
    """Get total count of jobs matching filters (for pagination)."""
    conn = get_connection()
    cursor = conn.cursor()

    where_clauses = ["is_active = 1"]
    params = []

    if q:
        where_clauses.append("(title LIKE ? OR employer_name LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])
    if salary_min is not None:
        where_clauses.append("estimated_salary >= ?")
        params.append(salary_min)
    if salary_max is not None:
        where_clauses.append("estimated_salary <= ?")
        params.append(salary_max)
    if location:
        where_clauses.append("location LIKE ?")
        params.append(f"%{location}%")
    if employment_type:
        where_clauses.append("employment_type = ?")
        params.append(employment_type)
    if source:
        where_clauses.append("source = ?")
        params.append(source)

    where_sql = " AND ".join(where_clauses)
    cursor.execute(f"SELECT COUNT(*) as cnt FROM job_listings WHERE {where_sql}", params)
    count = cursor.fetchone()["cnt"]
    conn.close()
    return count


def get_unextracted_jobs(limit: int = 100) -> list[dict]:
    """Get active jobs that haven't been through extraction yet."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM job_listings
        WHERE extracted_at IS NULL AND is_active = 1
        ORDER BY created_at ASC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unmatched_jobs() -> list[dict]:
    """Get active jobs not yet matched to a company."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM job_listings
        WHERE company_id IS NULL AND is_active = 1
        ORDER BY created_at ASC
    """)

    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_jobs_needing_salary_estimate() -> list[dict]:
    """Get active jobs without an estimated salary."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM job_listings
        WHERE estimated_salary IS NULL AND is_active = 1
        ORDER BY created_at ASC
    """)

    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def deactivate_stale_jobs(source: str, active_source_ids: list[str]) -> int:
    """Deactivate jobs that are stale. Three rules:
    (a) source matches but source_id not in active_source_ids list
    (b) deadline has passed
    (c) posted_date is more than 90 days ago
    Returns total number of deactivated jobs."""
    conn = get_connection()
    cursor = conn.cursor()
    total = 0

    # (a) Not in active source IDs list — but keep jobs with future deadlines
    if active_source_ids:
        placeholders = ",".join("?" * len(active_source_ids))
        cursor.execute(f"""
            UPDATE job_listings SET is_active = 0, updated_at = datetime('now')
            WHERE source = ? AND source_id NOT IN ({placeholders})
            AND is_active = 1
            AND (deadline IS NULL OR deadline < date('now'))
        """, [source] + active_source_ids)
    else:
        cursor.execute("""
            UPDATE job_listings SET is_active = 0, updated_at = datetime('now')
            WHERE source = ? AND is_active = 1
            AND (deadline IS NULL OR deadline < date('now'))
        """, (source,))
    total += cursor.rowcount

    # (b) Past deadline
    cursor.execute("""
        UPDATE job_listings SET is_active = 0, updated_at = datetime('now')
        WHERE deadline < date('now') AND deadline IS NOT NULL AND is_active = 1
    """)
    total += cursor.rowcount

    # (c) Posted more than 90 days ago
    cursor.execute("""
        UPDATE job_listings SET is_active = 0, updated_at = datetime('now')
        WHERE posted_date < date('now', '-90 days') AND posted_date IS NOT NULL AND is_active = 1
    """)
    total += cursor.rowcount

    conn.commit()
    conn.close()
    return total


def get_job_stats() -> dict:
    """Get summary statistics for job listings."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as cnt FROM job_listings WHERE is_active = 1")
    active_jobs = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(*) as cnt FROM job_listings WHERE is_active = 1 AND company_id IS NOT NULL")
    matched_jobs = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(*) as cnt FROM job_listings WHERE is_active = 1 AND extracted_at IS NOT NULL")
    extracted_jobs = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(*) as cnt FROM job_listings WHERE is_active = 1 AND estimated_salary IS NOT NULL")
    jobs_with_salary = cursor.fetchone()["cnt"]

    cursor.execute("SELECT DISTINCT source FROM job_listings WHERE is_active = 1 ORDER BY source")
    job_sources = [row["source"] for row in cursor.fetchall()]

    conn.close()

    return {
        "active_jobs": active_jobs,
        "matched_jobs": matched_jobs,
        "extracted_jobs": extracted_jobs,
        "jobs_with_salary": jobs_with_salary,
        "job_sources": job_sources,
    }


def get_all_unions() -> list[dict]:
    """Get all unions ordered by member count."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM unions ORDER BY members DESC NULLS LAST")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_union_by_id(union_id: int) -> Optional[dict]:
    """Get a single union by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM unions WHERE id = ?", (union_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def save_union(data: dict) -> int:
    """Insert or update union (UPSERT on name)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO unions (name, name_en, federation, website, sector, members,
            fee_pct, sick_fund_pct, holiday_fund_pct, education_fund_pct,
            rehab_fund_pct, employer_pension_pct, employee_pension_pct,
            sick_pay_pct, sick_pay_days, holiday_homes, education_grants,
            death_benefit, description, benefits_summary, wage_agreement_period,
            min_wage, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT (name) DO UPDATE SET
            name_en = excluded.name_en,
            federation = excluded.federation,
            website = excluded.website,
            sector = excluded.sector,
            members = excluded.members,
            fee_pct = excluded.fee_pct,
            sick_fund_pct = excluded.sick_fund_pct,
            holiday_fund_pct = excluded.holiday_fund_pct,
            education_fund_pct = excluded.education_fund_pct,
            rehab_fund_pct = excluded.rehab_fund_pct,
            employer_pension_pct = excluded.employer_pension_pct,
            employee_pension_pct = excluded.employee_pension_pct,
            sick_pay_pct = excluded.sick_pay_pct,
            sick_pay_days = excluded.sick_pay_days,
            holiday_homes = excluded.holiday_homes,
            education_grants = excluded.education_grants,
            death_benefit = excluded.death_benefit,
            description = excluded.description,
            benefits_summary = excluded.benefits_summary,
            wage_agreement_period = excluded.wage_agreement_period,
            min_wage = excluded.min_wage,
            updated_at = datetime('now')
    """, (data["name"], data.get("name_en"), data.get("federation"),
          data.get("website"), data.get("sector"), data.get("members"),
          data.get("fee_pct"), data.get("sick_fund_pct"),
          data.get("holiday_fund_pct"), data.get("education_fund_pct"),
          data.get("rehab_fund_pct"), data.get("employer_pension_pct"),
          data.get("employee_pension_pct"), data.get("sick_pay_pct"),
          data.get("sick_pay_days"), data.get("holiday_homes"),
          data.get("education_grants"), data.get("death_benefit"),
          data.get("description"), data.get("benefits_summary"),
          data.get("wage_agreement_period"), data.get("min_wage")))
    uid = cursor.lastrowid
    conn.commit()
    conn.close()
    return uid


# Initialize database on import
init_db()
