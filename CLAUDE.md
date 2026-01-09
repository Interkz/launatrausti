# Launatrausti - Icelandic Salary Transparency Platform

## Project Vision

Create an Icelandic version of [levels.fyi](https://levels.fyi) using **only public data sources** - no user submissions. The goal is to help Icelanders evaluate employers and pressure companies to improve compensation by making wage data transparent.

## Core Concept

Calculate estimated average salaries per company using:
```
Average Salary = Launakostnaður (wage costs) ÷ Meðalfjöldi starfsmanna (employee count)
```

This data comes from mandatory annual reports (ársreikningar) that Icelandic companies must file publicly.

## Current Status: MVP + Hagstofa Integration

**Phase:** MVP with industry benchmarks

**What's Working:**
- FastAPI web app with company rankings
- SQLite database with companies and annual reports
- Skatturinn API integration (fetches company metadata)
- **Hagstofa integration (industry wage benchmarks)** - NEW
- PDF extraction pipeline (ready, needs real PDFs)
- Sample data seeded with ISAT codes

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
├── plan.md                   # Roadmap and next steps
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
│   ├── hagstofa.py          # Hagstofa API client (industry benchmarks)
│   ├── extractor.py         # PDF extraction with Claude API
│   ├── skatturinn_api.py    # Skatturinn API client
│   └── templates/
│       ├── base.html        # Base template
│       ├── index.html       # Rankings page
│       ├── company.html     # Company detail page (with benchmarks)
│       └── benchmarks.html  # Industry benchmarks page
│
├── scripts/
│   ├── extract_pdf.py       # CLI: Process annual report PDF
│   ├── fetch_companies.py   # CLI: Fetch from Skatturinn API
│   └── seed_sample.py       # CLI: Add sample test data (with ISAT codes)
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

## Web Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Rankings page (HTML) |
| `GET /company/{id}` | Company detail with benchmark comparison (HTML) |
| `GET /benchmarks?year=2023` | Industry wage benchmarks page (HTML) |
| `GET /api/companies?year=2023` | JSON API |
| `GET /api/company/{id}` | Company JSON |
| `GET /api/benchmarks?year=2023` | Industry benchmarks JSON |
| `GET /docs` | Swagger API docs |

## API Keys & Credentials

### Skatturinn API (ACTIVE)
- **Keys in:** `api.txt` (primary key line)
- **Portal:** https://api.skatturinn.is/
- **Limits:** 60 calls/min, 5000 calls/month
- **Provides:** Company metadata (name, ISAT code, status, address)
- **Does NOT provide:** Financial data (wage costs, employees, revenue)

### Hagstofa API (ACTIVE - No key needed)
- **Endpoint:** `https://px.hagstofa.is/pxis/api/v1/is/`
- **Table:** VIN02003 (wages by industry)
- **Provides:** Industry average wages by ISAT category
- **Data:** 2014-2024, updated annually

### Anthropic API (for PDF extraction)
- Set `ANTHROPIC_API_KEY` environment variable
- Used by `src/extractor.py` to parse annual report PDFs

## Key Commands

```bash
# Run web server
uvicorn src.main:app --port 8080 --reload

# Seed sample data (fake data for testing)
python scripts/seed_sample.py

# Fetch companies from Skatturinn API
python scripts/fetch_companies.py --sample
python scripts/fetch_companies.py 4602070880 4710080280

# Process an annual report PDF (needs ANTHROPIC_API_KEY)
python scripts/extract_pdf.py pdfs/some_report.pdf --kennitala 1234567890
```

## Database Schema

### companies
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| kennitala | TEXT | Company national ID (unique) |
| name | TEXT | Company name |
| isat_code | TEXT | Industry classification (e.g., "62.01") |

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

## Hagstofa Industry Benchmarks (2023)

| Industry | Code | Monthly Avg | Annual Avg |
|----------|------|-------------|------------|
| Utilities | D | 1,286,000 kr | 15.4M kr |
| Finance & Insurance | K | 1,235,000 kr | 14.8M kr |
| Construction | F | 1,042,000 kr | 12.5M kr |
| Public Admin | O | 1,036,000 kr | 12.4M kr |
| Transport | H | 1,017,000 kr | 12.2M kr |
| **IT/Tech** | **J** | **1,009,000 kr** | **12.1M kr** |
| Health & Social | Q | 987,000 kr | 11.8M kr |
| Manufacturing | C | 946,000 kr | 11.4M kr |
| **National Average** | - | **935,000 kr** | **11.2M kr** |

## ISAT Code Mapping

The Hagstofa module (`src/hagstofa.py`) maps ISAT codes to industry categories:
- **58-63** → J (Information & Communication / Tech)
- **64-66** → K (Finance & Insurance)
- **41-43** → F (Construction)
- **49-53** → H (Transport & Storage)
- See `ISAT_TO_HAGSTOFA` dict in `src/hagstofa.py` for full mapping

## Data Sources Summary

| Source | Has API | Company-Specific | Has Wage Data | Bulk ISAT List | Cost |
|--------|---------|------------------|---------------|----------------|------|
| **Hagstofa** | ✅ | ❌ Industry avg | ✅ **INTEGRATED** | ❌ | Free |
| Já Gagnatorg | ✅ | ✅ | ❌ | ✅ **YES** | 30-day free trial |
| Skatturinn API | ✅ | ✅ Metadata only | ❌ | ❌ | Free |
| Creditinfo | ✅ | ✅ Full financials | ✅ | ❓ | Paid |
| Skatturinn PDFs | ❌ Manual | ✅ | ✅ | ❌ | Free |

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
| Industry classification | ISAT |

## Useful Links

- **Hagstofa Wage Data**: https://px.hagstofa.is/pxis/pxweb/is/Samfelag/Samfelag__launogtekjur__1_laun__1_laun/
- **Já Gagnatorg** (bulk company data): https://gagnatorg.ja.is/
- Skatturinn API Portal: https://api.skatturinn.is/
- Skatturinn Company Search: https://www.skatturinn.is/fyrirtaekjaskra/leit
- Creditinfo Developer Portal: https://developer.creditinfo.is/
- Keldan: https://keldan.is/

## Session Notes

**2026-01-09 Session:**
- **UI Redesign: Swiss + Severance aesthetic**
  - Complete visual overhaul inspired by Lumon Industries (Apple TV's Severance)
  - Typography: Playfair Display (headings), IBM Plex Mono (data), IBM Plex Sans (body)
  - Color palette: forest-green-black (`#1a3d2e`), off-white paper (`#f7f7f5`)
  - Subtle 80px architectural grid overlay
  - Monospaced tabular data with zero-padded indices
  - Double-line borders, uppercase micro-labels
  - Removed traffic-light colors (no red/green for gains/losses)
- Created global `/start` skill at `~/.claude/commands/start.md`
  - Loads CLAUDE.md and plan.md for project context
  - Available across all projects

**2025-01-09 Session:**
- **Hagstofa integration complete**
  - Created `src/hagstofa.py` - API client with caching
  - Added `/benchmarks` page showing all industries
  - Company detail pages now show benchmark comparison
  - Added `/api/benchmarks` JSON endpoint
- Updated sample data with ISAT codes for benchmark matching
- Prepared contact emails for data providers (Já, Creditinfo, Skatturinn, Keldan)
- **Key insight:** Tech (ISAT J) pays ~1M kr/month avg, Finance (K) ~1.2M kr/month

**2025-01-02 Session:**
- Researched bulk company list sources
- **Key discovery:** Já Gagnatorg has `/dump/businesses-isat` endpoint
- Draft emails prepared for data provider inquiries

**2024-12-31 Session:**
- Built complete MVP from scratch
- Researched all Icelandic data sources
- Integrated Skatturinn API
- Created PDF extraction pipeline
