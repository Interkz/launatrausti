# Launatrausti - Icelandic Salary Transparency Platform

## Project Vision

Create an Icelandic version of [levels.fyi](https://levels.fyi) using **only public data sources** - no user submissions. The goal is to help Icelanders evaluate employers and pressure companies to improve compensation by making wage data transparent.

## Core Concept

Calculate estimated average salaries per company using:
```
Average Salary = Launakostnadur (wage costs) / Medalfjoldi starfsmanna (employee count)
```

This data comes from mandatory annual reports (arsreikningar) that Icelandic companies must file publicly. Supplemented by Hagstofa industry benchmarks and VR union salary surveys.

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Web framework** | FastAPI 0.109 + Jinja2 templates |
| **Database** | SQLite (file: `launatrausti.db`, auto-created on import) |
| **PDF extraction** | pdfplumber (text extraction) + Anthropic Claude API (structured parsing) |
| **External APIs** | Skatturinn (company metadata), Hagstofa (industry wages), apis.is (company lookup) |
| **Web scraping** | Playwright (Skatturinn PDFs), requests + BeautifulSoup (Rikisreikningur PDFs) |
| **Testing** | pytest + pytest-asyncio + httpx |
| **Deployment** | Vercel (Python serverless via `api/index.py`) |
| **UI** | Swiss + Severance (Lumon) aesthetic: Playfair Display, IBM Plex Mono, forest-green-black palette |

## Key Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run web server (development)
uvicorn src.main:app --port 8080 --reload

# Seed sample data (fake data for testing)
python scripts/seed_sample.py

# Run the full data pipeline (all stages)
python scripts/run_pipeline.py
python scripts/run_pipeline.py --dry-run        # preview without side effects
python scripts/run_pipeline.py --stage 7         # just print stats

# Fetch companies from Skatturinn API
python scripts/fetch_companies.py --sample
python scripts/fetch_companies.py 4602070880 4710080280

# Scrape annual report PDFs from Skatturinn
python scripts/scrape_arsreikningar.py --kennitolur 4710080280 --years 2023 2022
python scripts/scrape_arsreikningar.py --from-db   # all companies in DB

# Scrape government institution PDFs from Rikisreikningur
python scripts/scrape_rikisreikningur.py
python scripts/scrape_rikisreikningur.py --list-only

# Download and parse VR salary surveys (needs ANTHROPIC_API_KEY)
python scripts/parse_vr_surveys.py --all
python scripts/parse_vr_surveys.py --all --dry-run

# Process a single annual report PDF (needs ANTHROPIC_API_KEY)
python scripts/extract_pdf.py pdfs/some_report.pdf --kennitala 1234567890

# Run tests
pytest
```

## File Structure

```
launatrausti/
├── CLAUDE.md                 # This file
├── plan.md                   # Roadmap and next steps
├── README.md                 # Quick start guide
├── requirements.txt          # Python dependencies
├── vercel.json               # Vercel deployment config
├── launatrausti.db          # SQLite database (auto-created)
├── api.txt                   # Skatturinn API keys (DO NOT COMMIT)
├── idea.txt                  # Original concept notes
├── skatturinn.txt            # API subscription info
├── company-registry-legalentities-v2.json  # Skatturinn OpenAPI spec
│
├── api/
│   └── index.py             # Vercel serverless entry point
│
├── src/
│   ├── __init__.py
│   ├── main.py              # FastAPI app: all routes (HTML + JSON API)
│   ├── database.py          # SQLite schema, models, queries (init_db on import)
│   ├── hagstofa.py          # Hagstofa API client (industry wage benchmarks)
│   ├── extractor.py         # PDF extraction: pdfplumber + Claude API (v1 + v2 + batch)
│   ├── skatturinn_api.py    # Skatturinn API client (company metadata)
│   ├── apis_is.py           # apis.is client (free company lookup, currently down)
│   └── templates/
│       ├── base.html        # Base template (Swiss/Severance design)
│       ├── index.html       # Company rankings page
│       ├── company.html     # Company detail with benchmarks
│       ├── financials.html  # Company financials detail
│       ├── benchmarks.html  # Industry wage benchmarks
│       ├── salaries.html    # VR salary survey data
│       └── launaleynd.html  # Salary secrecy gap analysis
│
├── scripts/
│   ├── __init__.py
│   ├── run_pipeline.py          # Full 7-stage data pipeline orchestrator
│   ├── seed_sample.py           # Seed fake test data
│   ├── cleanup_sample_data.py   # Flag/delete sample data
│   ├── fetch_companies.py       # Fetch from Skatturinn API
│   ├── import_skatturinn.py     # Bulk import via Skatturinn API
│   ├── import_apis_is.py        # Bulk import via apis.is
│   ├── extract_pdf.py           # CLI: process annual report PDF
│   ├── scrape_arsreikningar.py  # Playwright scraper: Skatturinn annual report PDFs
│   ├── scrape_rikisreikningur.py # Scraper: government institution PDFs
│   └── parse_vr_surveys.py      # Download + parse VR salary survey PDFs
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # Fixtures: test_db, sample_company, sample_reports, sample_vr_surveys
│   ├── test_api.py          # API endpoint tests
│   ├── test_database.py     # Database layer tests
│   └── test_extractor.py    # PDF extractor tests
│
├── pdfs/                    # Annual report PDFs (downloaded by scrapers)
│   ├── vr/                  # VR salary survey PDFs
│   └── rikis/               # Government institution PDFs
│
├── data-sources/            # Research documentation
│   ├── README.md
│   ├── RESEARCH-RESULTS.md
│   ├── 01-skatturinn-api.md
│   ├── 02-hagstofa-api.md
│   ├── 03-creditinfo-api.md
│   ├── 04-keldan.md
│   ├── 05-union-wage-tables.md
│   └── 06-skatturinn-arsreikningar-pdfs.md
│
└── SESSION_SUMMARY.md       # Session notes archive
```

## Web Endpoints

### HTML Pages
| Endpoint | Description |
|----------|-------------|
| `GET /` | Company rankings (filterable by year, sector) |
| `GET /company/{id}` | Company detail with benchmark comparison |
| `GET /company/{id}/financials` | Company financials detail (trends, CAGR) |
| `GET /benchmarks?year=2023` | Industry wage benchmarks from Hagstofa |
| `GET /salaries` | VR salary survey data (filterable by category, date) |
| `GET /launaleynd` | Salary secrecy gap analysis (company vs VR avg) |
| `GET /docs` | Swagger API docs (auto-generated) |

### JSON API
| Endpoint | Description |
|----------|-------------|
| `GET /api/companies?year=2023&limit=100` | Company rankings |
| `GET /api/company/{id}` | Company detail + reports |
| `GET /api/company/{id}/financials` | Company financials + trends |
| `GET /api/company/{id}/salary-comparison` | Company vs VR survey comparison |
| `GET /api/benchmarks?year=2023` | Industry benchmarks from Hagstofa |
| `GET /api/salaries?category=X&survey_date=Y` | VR salary survey data |
| `GET /api/stats` | Platform statistics (counts, year range) |
| `GET /health` | Health check |

## Database Schema

### companies
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| kennitala | TEXT UNIQUE | Company national ID |
| name | TEXT | Company name |
| isat_code | TEXT | Industry classification (e.g., "62.01") |
| address | TEXT | Company address |
| legal_form | TEXT | Legal form (ehf, hf, etc.) |
| sector | TEXT | Sector label (e.g., "public") |
| employee_count_latest | INTEGER | Latest known employee count |
| updated_at | DATETIME | Last update timestamp |

### annual_reports
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| company_id | INTEGER | FK to companies |
| year | INTEGER | Report year |
| launakostnadur | INTEGER | Total wage costs (ISK) |
| starfsmenn | REAL | Average employee count |
| tekjur | INTEGER | Revenue (optional) |
| avg_salary | INTEGER | Calculated: launakostnadur / starfsmenn |
| hagnadur | INTEGER | Net profit/loss |
| rekstrarkostnadur | INTEGER | Operating expenses |
| eiginfjarhlufall | REAL | Equity ratio |
| laun_hlutfall_tekna | REAL | Wages as fraction of revenue |
| source_pdf | TEXT | PDF filename |
| source_type | TEXT | 'pdf', default |
| confidence | REAL | Extraction confidence (0-1) |
| is_sample | BOOLEAN | True for seeded test data |
| extracted_at | DATETIME | When extracted |

### vr_salary_surveys
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| survey_date | TEXT | Survey period (e.g., "2025-09") |
| starfsheiti | TEXT | Job title (Icelandic) |
| starfsstett | TEXT | Job category |
| medaltal | INTEGER | Mean monthly salary (ISK) |
| midgildi | INTEGER | Median salary |
| p25 | INTEGER | 25th percentile |
| p75 | INTEGER | 75th percentile |
| fjoldi_svara | INTEGER | Number of respondents |

### scrape_log
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| source | TEXT | Source identifier (e.g., "skatturinn_arsreikningar") |
| identifier | TEXT | Item identifier (kennitala or file_id) |
| year | INTEGER | Year |
| status | TEXT | 'pending', 'downloaded', 'extracted', 'failed' |
| pdf_path | TEXT | Path to downloaded PDF |
| error_message | TEXT | Error details if failed |

### data_flags
Tracks data quality issues (sample_data, low_confidence, outlier, stale).

## Data Pipeline

The `scripts/run_pipeline.py` orchestrates 7 stages:

1. **Cleanup** - Flag/delete sample data
2. **Download VR PDFs** - Fetch VR salary survey PDFs
3. **Parse VR surveys** - Extract salary data via Claude API
4. **Scrape Skatturinn** - Download annual report PDFs (Playwright)
5. **Scrape Rikisreikningur** - Download government institution PDFs
6. **Extract PDFs** - Batch extract financial data from all PDFs (Claude API)
7. **Stats** - Print platform statistics

## API Keys & Credentials

### Skatturinn API
- **Keys in:** `api.txt` (line: `primary key: <key>`) or `SKATTURINN_API_KEY` env var
- **Limits:** 60 calls/min, 5000 calls/month
- **Provides:** Company metadata (name, ISAT code, status, address)

### Hagstofa API (no key needed)
- **Endpoint:** `https://px.hagstofa.is/pxis/api/v1/is/`
- **Table:** VIN02003 (wages by industry)
- **Data:** 2014-2024, industry averages by ISAT category

### Anthropic API (for PDF extraction)
- Set `ANTHROPIC_API_KEY` environment variable
- Used by `src/extractor.py` and `scripts/parse_vr_surveys.py`

## ISAT Code Mapping

`src/hagstofa.py` maps 2-digit ISAT prefixes to Hagstofa industry letter codes:
- **58-63** -> J (Information & Communication / Tech)
- **64-66** -> K (Finance & Insurance)
- **41-43** -> F (Construction)
- **49-53** -> H (Transport & Storage)
- See `ISAT_TO_HAGSTOFA` dict for full mapping

## Icelandic Terminology

| English | Icelandic |
|---------|-----------|
| Annual report | Arsreikningur |
| Wages/salary | Laun |
| Wage costs | Launakostnadur |
| Employees | Starfsmenn |
| Average employees | Medalfjoldi starfsmanna |
| Company | Fyrirtaeki |
| National ID | Kennitala |
| Tax Authority | Skatturinn / RSK |
| Statistics Iceland | Hagstofa Islands |
| Industry classification | ISAT |
| Profit | Hagnadur |
| Operating expenses | Rekstrarkostnadur |
| Equity ratio | Eiginfjarhlufall |
| Salary survey | Launarannsokn |

## Conventions

- Database auto-initializes on `import src.database` (calls `init_db()`)
- Schema migrations use `ALTER TABLE ADD COLUMN` with `_column_exists()` guard
- All scrapers use `scrape_log` table for idempotency (skip already-processed items)
- Sample data is flagged with `is_sample=1` and excluded from rankings by default
- Vercel deployment copies DB to `/tmp` (read-only filesystem workaround)
- Tests use `tmp_path` fixture with `patch.object(db, "DB_PATH", ...)` for isolation
