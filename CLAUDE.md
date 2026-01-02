# Launatrausti - Icelandic Salary Transparency Platform

## Project Vision

Create an Icelandic version of [levels.fyi](https://levels.fyi) using **only public data sources** - no user submissions. The goal is to help Icelanders evaluate employers and pressure companies to improve compensation by making wage data transparent.

## Core Concept

Calculate estimated average salaries per company using:
```
Average Salary = Launakostnaður (wage costs) ÷ Meðalfjöldi starfsmanna (employee count)
```

This data comes from mandatory annual reports (ársreikningar) that Icelandic companies must file publicly.

## Current Status: MVP COMPLETE

**Phase:** MVP built and running

**What's Working:**
- FastAPI web app with company rankings
- SQLite database with companies and annual reports
- Skatturinn API integration (fetches company metadata)
- PDF extraction pipeline (ready, needs real PDFs)
- Sample data seeded for testing

**Run the app:**
```bash
cd launatrausti
pip install -r requirements.txt
python scripts/seed_sample.py  # Add test data
uvicorn src.main:app --port 8080
# Open http://localhost:8080
```

## File Structure

```
launatrausti/
├── CLAUDE.md                 # This file
├── README.md                 # Quick start guide
├── requirements.txt          # Python dependencies
├── launatrausti.db          # SQLite database (auto-created)
├── api.txt                   # Skatturinn API keys (DO NOT COMMIT)
├── idea.txt                  # Original concept notes
├── skatturinn.txt            # API subscription info
├── company-registry-legalentities-v2.json  # Skatturinn OpenAPI spec
│
├── src/
│   ├── __init__.py
│   ├── main.py              # FastAPI web app
│   ├── database.py          # SQLite models and queries
│   ├── extractor.py         # PDF extraction with Claude API
│   ├── skatturinn_api.py    # Skatturinn API client
│   └── templates/
│       ├── base.html        # Base template
│       ├── index.html       # Rankings page
│       └── company.html     # Company detail page
│
├── scripts/
│   ├── extract_pdf.py       # CLI: Process annual report PDF
│   ├── fetch_companies.py   # CLI: Fetch from Skatturinn API
│   └── seed_sample.py       # CLI: Add sample test data
│
├── pdfs/                    # Put annual report PDFs here
│
└── data-sources/            # Research documentation
    ├── README.md
    ├── 01-skatturinn-api.md
    ├── 02-hagstofa-api.md
    ├── 03-creditinfo-api.md
    ├── 04-keldan.md
    ├── 05-union-wage-tables.md
    └── 06-skatturinn-arsreikningar-pdfs.md
```

## API Keys & Credentials

### Skatturinn API (ACTIVE)
- **Keys in:** `api.txt` (primary key line)
- **Portal:** https://api.skatturinn.is/
- **Limits:** 60 calls/min, 5000 calls/month
- **Provides:** Company metadata (name, ISAT code, status, address)
- **Does NOT provide:** Financial data (wage costs, employees, revenue)

### Anthropic API (for PDF extraction)
- Set `ANTHROPIC_API_KEY` environment variable
- Used by `src/extractor.py` to parse annual report PDFs

## Key Commands

```bash
# Fetch companies from Skatturinn API
python scripts/fetch_companies.py --sample
python scripts/fetch_companies.py 4602070880 4710080280

# Process an annual report PDF (needs ANTHROPIC_API_KEY)
python scripts/extract_pdf.py pdfs/some_report.pdf --kennitala 1234567890

# Seed sample data (fake data for testing)
python scripts/seed_sample.py

# Run web server
uvicorn src.main:app --port 8080 --reload
```

## Database Schema

### companies
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| kennitala | TEXT | Company national ID (unique) |
| name | TEXT | Company name |
| isat_code | TEXT | Industry classification |

### annual_reports
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| company_id | INTEGER | FK to companies |
| year | INTEGER | Report year |
| launakostnadur | INTEGER | Total wage costs (ISK) |
| starfsmenn | REAL | Average employee count |
| tekjur | INTEGER | Revenue (optional) |
| avg_salary | INTEGER | Calculated field |
| source_pdf | TEXT | PDF filename |
| extracted_at | DATETIME | When extracted |

## Web Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Rankings page (HTML) |
| `GET /company/{id}` | Company detail (HTML) |
| `GET /api/companies?year=2023` | JSON API |
| `GET /api/company/{id}` | Company JSON |
| `GET /docs` | Swagger API docs |

## Verified Company Kennitölur

```python
# These are confirmed working with Skatturinn API
"6204830369"  # JBT Marel ehf
"6407070540"  # Marel Iceland ehf
"4602070880"  # Síminn hf
"4710080280"  # Landsbankinn hf
"5810080150"  # Arion banki hf
"4910080160"  # Íslandsbanki hf
```

## Data Sources Summary

| Source | Has API | Company-Specific | Has Wage Data | Bulk ISAT List | Cost |
|--------|---------|------------------|---------------|----------------|------|
| Já Gagnatorg | ✅ | ✅ | ❌ | ✅ **YES** | 30-day free trial |
| Skatturinn API | ✅ | ✅ Metadata only | ❌ | ❌ | Free |
| Hagstofa | ✅ | ❌ Industry avg | ✅ | ❌ | Free |
| Creditinfo | ✅ | ✅ Full financials | ✅ | ❓ | Paid |
| Skatturinn PDFs | ❌ Manual | ✅ | ✅ | ❌ | Free |
| apis.is | ✅ | ✅ Search only | ❌ | ❌ | Free |

### Já Gagnatorg (KEY for company discovery)
- **Portal:** https://gagnatorg.ja.is/
- **Docs:** https://gagnatorg.ja.is/docs/skra/v1/
- **Contact:** gagnatorg@ja.is
- **Cost:** 30-day free trial, then 2,100-14,900 kr/month
- **Key endpoints:**
  - `/v1/dump/businesses` - Complete business register (CSV)
  - `/v1/dump/businesses-isat` - Business-to-ISAT mappings (CSV)
  - `/v1/dump/isat` - All ISAT classifications
- **Why it matters:** Only known source for bulk listing companies by ISAT code

## Next Steps (Priority Order)

### 1. Get Tech Company List via Já Gagnatorg
**Problem:** Skatturinn API cannot list/filter companies by ISAT code
**Solution:** Já Gagnatorg has bulk CSV dumps with ISAT mappings

1. Sign up for 30-day free trial at https://gagnatorg.ja.is/
2. Download `/v1/dump/businesses-isat` CSV
3. Filter for ISAT codes starting with "62" (tech/IT)
4. Import kennitölur into our database

### 2. Get Financial Data
Once we have kennitölur, get wage data via:

**Option A: PDF Extraction (Free but manual)**
1. Download annual reports from https://www.skatturinn.is/fyrirtaekjaskra/leit
2. Save to `pdfs/` folder
3. Run: `python scripts/extract_pdf.py pdfs/file.pdf`
4. Requires `ANTHROPIC_API_KEY` for Claude parsing

**Option B: Creditinfo API (Paid but automated)**
- Has structured annual account data with launakostnaður + starfsmenn
- Contact: https://developer.creditinfo.is/

### 3. Add Hagstofa Integration
- Industry benchmark wages are available free via API
- Python library: `pip install hagstofan`
- Would allow "Company X vs Industry Average" comparisons

### 4. Improve UI
- Add search/filtering
- Add charts for salary trends
- Mobile responsive design

## Icelandic Terminology

| English | Icelandic |
|---------|-----------|
| Annual report | Ársreikningur |
| Wages/salary | Laun |
| Wage costs | Launakostnaður |
| Employees | Starfsmenn |
| Average employees | Meðalfjöldi starfsmanna |
| Company | Fyrirtæki |
| National ID | Kennitala |
| Tax Authority | Skatturinn / RSK |
| Statistics Iceland | Hagstofa Íslands |
| Private limited company | Einkahlutafélag (ehf.) |
| Public limited company | Hlutafélag (hf.) |
| Industry classification | ISAT |

## Useful Links

- **Já Gagnatorg** (bulk company data): https://gagnatorg.ja.is/
- **Já Gagnatorg API Docs**: https://gagnatorg.ja.is/docs/skra/v1/
- Skatturinn API Portal: https://api.skatturinn.is/
- Skatturinn Company Search: https://www.skatturinn.is/fyrirtaekjaskra/leit
- apis.is (free Icelandic APIs): https://docs.apis.is/
- Hagstofa Wage Data: https://px.hagstofa.is/pxis/pxweb/is/Samfelag/Samfelag__launogtekjur__1_laun__1_laun/
- Hagstofa Python Library: https://github.com/datador/hagstofan
- Creditinfo Developer Portal: https://developer.creditinfo.is/
- Keldan (reference, no API): https://keldan.is/

## Session Notes

**2025-01-02 Session:**
- Researched how to get bulk company lists by ISAT code
- **Key discovery:** Já Gagnatorg API has `/dump/businesses-isat` endpoint
  - 30-day free trial available
  - Only known source for bulk ISAT-filtered company lists
- Skatturinn API confirmed: NO search/filter capability, single lookup only
- apis.is: Free but search-only, can't list all companies
- **New strategy:**
  1. Já Gagnatorg for tech company kennitölur (ISAT 62)
  2. Creditinfo OR manual PDF extraction for financial data
- Draft emails prepared for Já and Creditinfo inquiries

**2024-12-31 Session:**
- Built complete MVP from scratch
- Researched all Icelandic data sources (documented in `/data-sources/`)
- Integrated Skatturinn API with working authentication
- Created PDF extraction pipeline (untested with real PDFs)
- Web app running on port 8080 (port 8000 was in use)
- Database has sample data + 6 real companies from API
- Main blocker: Need real annual report PDFs or Creditinfo access for actual wage data
