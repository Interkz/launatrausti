# Launatrausti

Icelandic salary transparency platform. Calculates estimated average salaries per company from publicly filed annual reports (arsreikningar) and compares them against national industry benchmarks from Hagstofa (Statistics Iceland).

**Core formula:**

```
Average Salary = Launakostnadur (wage costs) / Medalfjoldi starfsmanna (employee count)
```

Data comes from mandatory annual reports that Icelandic companies file with Skatturinn (the tax authority).

## Features

- **Company salary rankings** — ranked list of companies by estimated average salary, filterable by year and sector
- **Industry benchmarks** — average wages by ISAT industry code from Hagstofa (Statistics Iceland)
- **Company detail pages** — annual report history with benchmark comparison against industry and national averages
- **Salary survey data** — VR union salary survey integration with job title breakdowns
- **Salary gap analysis** — "Launaleynd" page comparing company averages to survey expectations
- **Financial trends** — multi-year salary and revenue CAGR calculations
- **PDF extraction pipeline** — extract financial data from annual report PDFs using pdfplumber + Claude API
- **Skatturinn API integration** — fetch company metadata (name, ISAT code, legal form, address)
- **JSON API** — all data available via REST endpoints alongside the HTML views

## Tech Stack

- **Python 3.10+**
- **FastAPI** — web framework and API
- **SQLite** — database (auto-created on first run)
- **Jinja2** — HTML templates
- **pdfplumber** — PDF text extraction
- **Anthropic Claude API** — intelligent PDF parsing for financial data
- **Hagstofa PX-Web API** — industry wage benchmarks
- **Skatturinn API** — company registry metadata

## Setup

```bash
git clone https://github.com/your-username/launatrausti.git
cd launatrausti

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Seed with sample data for testing
python scripts/seed_sample.py

# Run the server
uvicorn src.main:app --port 8080 --reload
```

Open http://localhost:8080.

## API Endpoints

### HTML Pages

| Endpoint | Description |
|----------|-------------|
| `GET /` | Company rankings page (filterable by `?year=` and `?sector=`) |
| `GET /company/{id}` | Company detail with benchmark comparison |
| `GET /company/{id}/financials` | Company financial trends |
| `GET /benchmarks?year=2023` | Industry wage benchmarks |
| `GET /salaries` | VR salary survey data (filterable by `?category=` and `?survey_date=`) |
| `GET /launaleynd` | Salary secrecy gap analysis |

### JSON API

All JSON endpoints are also documented at `/docs` (Swagger UI).

#### `GET /api/companies`

List companies ranked by average salary.

```bash
# All companies (latest year per company)
curl http://localhost:8080/api/companies

# Filter by year, limit results
curl "http://localhost:8080/api/companies?year=2023&limit=10"
```

Response:

```json
{
  "companies": [
    {
      "id": 1,
      "kennitala": "4710080280",
      "name": "Landsbankinn hf.",
      "isat_code": "64.19",
      "year": 2023,
      "launakostnadur": 28000000000,
      "starfsmenn": 1100.0,
      "avg_salary": 25454545,
      "tekjur": 65000000000
    }
  ],
  "year": 2023
}
```

#### `GET /api/company/{id}`

Get company details with all annual reports.

```bash
curl http://localhost:8080/api/company/1
```

Response:

```json
{
  "company": {
    "id": 1,
    "kennitala": "4710080280",
    "name": "Landsbankinn hf.",
    "isat_code": "64.19",
    "sector": "Finance"
  },
  "reports": [
    {
      "year": 2023,
      "launakostnadur": 28000000000,
      "starfsmenn": 1100.0,
      "avg_salary": 25454545,
      "tekjur": 65000000000,
      "source_pdf": "landsbankinn_2023.pdf"
    }
  ]
}
```

#### `GET /api/company/{id}/financials`

Company financial data with multi-year trends (CAGR).

```bash
curl http://localhost:8080/api/company/1/financials
```

#### `GET /api/company/{id}/salary-comparison`

Compare company average salary against VR survey data.

```bash
curl http://localhost:8080/api/company/1/salary-comparison
```

Response:

```json
{
  "company_avg_salary": 25454545,
  "report_year": 2023,
  "vr_survey_date": "2024-01",
  "vr_avg": 850000,
  "diff_pct": 2894.7
}
```

#### `GET /api/benchmarks`

Industry wage benchmarks from Hagstofa.

```bash
curl "http://localhost:8080/api/benchmarks?year=2023"
```

Response:

```json
{
  "year": 2023,
  "national_average": {
    "monthly": 935000,
    "annual": 11220000
  },
  "industries": [
    {
      "code": "K",
      "name": "Fjarmaala- og vatryggingastarfsemi",
      "name_en": "Finance & insurance",
      "monthly_wage": 1235000,
      "annual_wage": 14820000
    }
  ],
  "source": "Hagstofa Islands (Statistics Iceland)"
}
```

#### `GET /api/salaries`

VR salary survey data.

```bash
# All surveys
curl http://localhost:8080/api/salaries

# Filter by category
curl "http://localhost:8080/api/salaries?category=Hugbunadadarfraedi"
```

#### `GET /api/stats`

Platform statistics (total companies, reports, coverage).

```bash
curl http://localhost:8080/api/stats
```

#### `GET /health`

Health check.

```bash
curl http://localhost:8080/health
# {"status": "ok"}
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | For PDF extraction | Anthropic API key for Claude-powered PDF parsing |
| `SKATTURINN_API_KEY` | For company fetch | Skatturinn API key (alternatively, put `primary key: <key>` in `api.txt`) |
| `VERCEL` | Auto-set on Vercel | When set, copies database to `/tmp` for read-only deployment |

## Scripts

```bash
# Seed sample data for testing
python scripts/seed_sample.py

# Fetch company metadata from Skatturinn API
python scripts/fetch_companies.py --sample
python scripts/fetch_companies.py 4602070880 4710080280

# Extract financial data from a single PDF
python scripts/extract_pdf.py pdfs/report.pdf --kennitala 1234567890

# Import companies from Skatturinn API into database
python scripts/import_skatturinn.py

# Scrape annual reports from Skatturinn
python scripts/scrape_arsreikningar.py

# Parse VR salary survey PDFs
python scripts/parse_vr_surveys.py

# Run the full data pipeline
python scripts/run_pipeline.py

# Clean up sample/test data
python scripts/cleanup_sample_data.py
```

## Project Structure

```
launatrausti/
├── src/
│   ├── main.py              # FastAPI app — routes and API endpoints
│   ├── database.py          # SQLite schema, models, queries
│   ├── hagstofa.py          # Hagstofa API client (industry benchmarks)
│   ├── extractor.py         # PDF extraction (pdfplumber + Claude API)
│   ├── skatturinn_api.py    # Skatturinn company registry API client
│   └── templates/           # Jinja2 HTML templates
├── scripts/                 # CLI tools for data ingestion
├── pdfs/                    # Annual report PDFs (not committed)
├── data-sources/            # Research docs on available data sources
├── requirements.txt
└── launatrausti.db          # SQLite database (auto-created)
```

## Database Schema

### companies

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `kennitala` | TEXT | Company national ID (unique, 10 digits) |
| `name` | TEXT | Company name |
| `isat_code` | TEXT | ISAT industry classification (e.g., "62.01") |
| `sector` | TEXT | Sector label |
| `address` | TEXT | Registered address |
| `legal_form` | TEXT | Legal form (ehf, hf, etc.) |

### annual_reports

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `company_id` | INTEGER | FK to companies |
| `year` | INTEGER | Fiscal year |
| `launakostnadur` | INTEGER | Total wage costs (ISK) |
| `starfsmenn` | REAL | Average employee count |
| `tekjur` | INTEGER | Revenue (ISK) |
| `avg_salary` | INTEGER | Calculated: launakostnadur / starfsmenn |
| `hagnadur` | INTEGER | Net profit/loss (ISK) |
| `rekstrarkostnadur` | INTEGER | Operating expenses (ISK) |
| `eiginfjarhlufall` | REAL | Equity ratio (0-1) |
| `laun_hlutfall_tekna` | REAL | Wage costs as fraction of revenue |
| `source_pdf` | TEXT | Source PDF filename |
| `source_type` | TEXT | Source type (pdf, api, etc.) |
| `confidence` | REAL | Extraction confidence (0-1) |
| `is_sample` | BOOLEAN | Whether this is sample/test data |

### vr_salary_surveys

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `survey_date` | TEXT | Survey period |
| `starfsheiti` | TEXT | Job title |
| `starfsstett` | TEXT | Job category |
| `medaltal` | INTEGER | Average salary (ISK/month) |
| `midgildi` | INTEGER | Median salary |
| `p25` | INTEGER | 25th percentile |
| `p75` | INTEGER | 75th percentile |

## Development Notes

- The database is auto-initialized on import of `src.database`. No migrations needed — new columns are added via `ALTER TABLE` with existence checks.
- Hagstofa data is cached in-memory for 24 hours to avoid excessive API calls. No API key needed.
- Skatturinn API is rate-limited to 60 calls/minute (handled automatically by the client).
- PDF extraction has two modes: Claude-powered (accurate, requires API key) and regex-based fallback (basic, no API key needed).
- Sample data is flagged with `is_sample=1` and excluded from the main rankings by default.
- The app runs on Vercel in read-only mode (SQLite copied to `/tmp`). For production with writes, use Turso or similar.

## Limitations

- Average salary includes all employees (CEO to intern) — no breakdown by role
- Part-time workers may skew the average downward
- Benefits and bonuses may or may not be included in launakostnadur depending on the company's reporting
- Annual report data is 6-12 months behind (filed after fiscal year ends)
- Industry benchmarks from Hagstofa are national averages, not company-specific

## License

MIT
