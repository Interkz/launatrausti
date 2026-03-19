-- Initial schema: companies, annual_reports, vr_salary_surveys, scrape_log, data_flags

CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kennitala TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    isat_code TEXT,
    address TEXT,
    legal_form TEXT,
    sector TEXT,
    employee_count_latest INTEGER,
    updated_at DATETIME
);

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
    hagnadur INTEGER,
    rekstrarkostnadur INTEGER,
    eiginfjarhlufall REAL,
    laun_hlutfall_tekna REAL,
    source_type TEXT DEFAULT 'pdf',
    confidence REAL DEFAULT 1.0,
    is_sample BOOLEAN DEFAULT 0,
    FOREIGN KEY (company_id) REFERENCES companies (id),
    UNIQUE (company_id, year)
);

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
);

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
);

CREATE TABLE IF NOT EXISTS data_flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    record_id INTEGER NOT NULL,
    flag_type TEXT NOT NULL CHECK(flag_type IN ('sample_data', 'low_confidence', 'outlier', 'stale')),
    message TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_annual_reports_year ON annual_reports(year);
CREATE INDEX IF NOT EXISTS idx_annual_reports_avg_salary ON annual_reports(avg_salary DESC);
CREATE INDEX IF NOT EXISTS idx_companies_isat ON companies(isat_code);
CREATE INDEX IF NOT EXISTS idx_companies_sector ON companies(sector);
CREATE INDEX IF NOT EXISTS idx_vr_surveys_date ON vr_salary_surveys(survey_date);
CREATE INDEX IF NOT EXISTS idx_vr_surveys_stett ON vr_salary_surveys(starfsstett);
CREATE INDEX IF NOT EXISTS idx_scrape_log_status ON scrape_log(status);
