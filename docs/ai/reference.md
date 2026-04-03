# Launatrausti — AI Reference

This file contains technical reference material for the launatrausti codebase.
For behavioral rules and project priorities, see `CLAUDE.md` in the project root.

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
pip install -r requirements.txt
uvicorn src.main:app --port 8080 --reload
python scripts/run_pipeline.py                    # full pipeline
python scripts/run_pipeline.py --stage 7          # just stats
python scripts/fetch_companies.py --sample
python scripts/scrape_arsreikningar.py --from-db
python scripts/scrape_rikisreikningur.py
python scripts/parse_vr_surveys.py --all
python scripts/extract_pdf.py pdfs/some_report.pdf --kennitala 1234567890
python scripts/scrape_jobs.py
pytest
```

## Web Endpoints

### HTML Pages
| Endpoint | Description |
|----------|-------------|
| `GET /` | Salary search hero + company rankings |
| `GET /company/{id}` | Company detail with benchmark, jobs, financials |
| `GET /samanburdur` | Salary comparison (164 occupations, percentile) |
| `GET /benchmarks?year=2024` | Industry wage benchmarks from Hagstofa |
| `GET /salaries` | VR salary survey data (filterable by category, date) |
| `GET /jobs` | Job listings with search, filters, cross-referencing |
| `GET /stettarfelog` | Union comparison (10 unions, personalized fees) |

### JSON API
| Endpoint | Description |
|----------|-------------|
| `GET /api/companies?year=2023&limit=100` | Company rankings |
| `GET /api/company/{id}` | Company detail + reports |
| `GET /api/company/{id}/financials` | Company financials + trends |
| `GET /api/company/{id}/salary-comparison` | Company vs VR survey comparison |
| `GET /api/benchmarks?year=2023` | Industry benchmarks from Hagstofa |
| `GET /api/salaries?category=X&survey_date=Y` | VR salary survey data |
| `GET /api/jobs?q=X&salary_min=N&sort=salary` | Job listings with search |
| `GET /api/unions` | Union comparison data |
| `GET /api/occupations?q=X&year=2024` | Occupation search |
| `GET /api/stats` | Platform statistics |
| `GET /health` | Health check |

## Database Schema

### companies
kennitala (TEXT UNIQUE), name, isat_code, address, legal_form, sector, employee_count_latest, updated_at

### annual_reports
company_id (FK), year, launakostnadur, starfsmenn, tekjur, avg_salary, hagnadur, rekstrarkostnadur, eiginfjarhlufall, laun_hlutfall_tekna, source_pdf, source_type, confidence, is_sample, extracted_at

### vr_salary_surveys
survey_date, starfsheiti, starfsstett, medaltal, midgildi, p25, p75, fjoldi_svara

### job_listings
source, source_id, title, employer_name, company_id (FK), location, salary_text, salary_lower, salary_upper, estimated_salary, salary_source, education_required, posted_date, deadline, source_url, is_active

### hagstofa_occupations
isco_code, occupation_name, year, mean, median, p25, p75, observation_count, salary_type

### unions
name, name_en, federation, sector, members, fee_pct, sick_pay_days, holiday_homes

### scrape_log
source, identifier, year, status, pdf_path, error_message

### data_flags
Tracks quality issues (sample_data, low_confidence, outlier, stale).

## Data Pipeline (11 stages)

1. Cleanup sample data → 2. Download VR PDFs → 3. Parse VR surveys → 4. Scrape Skatturinn → 5. Scrape Ríkisreikningur → 6. Extract PDFs → 7. Stats → 8. Scrape jobs → 9. Extract job fields → 10. Match employers → 11. Estimate salaries

## API Keys

- **Skatturinn:** `api.txt` or `SKATTURINN_API_KEY` env var. 60 calls/min, 5000/month.
- **Hagstofa:** No key needed. `https://px.hagstofa.is/pxis/api/v1/is/`
- **Anthropic:** `ANTHROPIC_API_KEY` env var. Used for PDF extraction + job field extraction.

## ISAT Code Mapping
See `ISAT_TO_HAGSTOFA` dict in `src/hagstofa.py`. Maps 2-digit ISAT prefixes to Hagstofa industry letter codes (58-63→J, 64-66→K, 41-43→F, etc.)

## Icelandic Terminology
Ársreikningur (annual report), Laun (wages), Launakostnaður (wage costs), Starfsmenn (employees), Meðalfjöldi starfsmanna (avg employees), Fyrirtæki (company), Kennitala (national ID), Skatturinn/RSK (tax authority), Hagstofa Íslands (Statistics Iceland), ISAT (industry classification), Hagnaður (profit), Rekstrarkostnaður (operating expenses), Eiginfjárhlutfall (equity ratio), Launarannsókn (salary survey)

## Conventions
- Database auto-initializes on `import src.database`
- Schema migrations use `ALTER TABLE ADD COLUMN` with `_column_exists()` guard
- Scrapers use `scrape_log` table for idempotency
- Sample data flagged `is_sample=1`, excluded from rankings
- Vercel deployment copies DB to `/tmp` (read-only filesystem workaround)
- Tests use `tmp_path` fixture with `patch.object(db, "DB_PATH", ...)`
