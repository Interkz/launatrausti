# Spec 1: Intelligent Job Listings

> "Every Icelandic job listing, enriched with salary intelligence that exists nowhere else."

## Context

Launatrausti has 163 real entities with financial data, 269 VR occupation salary surveys, and Hagstofa industry benchmarks. But job seekers have no reason to visit daily — the data is static reference material.

Icelandic job boards (Alfred.is, Island.is Starfatorg) list ~1,400 active jobs but publish almost zero salary data. The `jobCompensations` field in Alfred's API is always empty. Employers reference "salary per collective agreement" without numbers.

**The opportunity:** Combine live job listings with launatrausti's salary intelligence. Show estimated salaries on jobs where none exist. Let people filter by "700k+ jobs" using data derived from company financials, industry averages, and union surveys. Nobody else in Iceland does this.

**Secondary value:** Job listings contain employer names — scraping them daily is a free company discovery engine that feeds the financial data pipeline.

## Data Sources (verified live, 2026-03-29)

### Alfred.is — Public REST API
- **Endpoint:** `GET https://userapi.alfred.is/api/v2/jobs?page={n}&size=50`
- **Auth:** None
- **Jobs:** ~1,036 active
- **Pagination:** page + size params, 50/page max
- **Fields:** id, title, brand.name, brand.slug, location (lat/lon), employmentType, jobType, description, applicationDeadline, createdAt, tags[], jobCompensations[] (always empty)
- **No kennitala.** Employer identified by brand.name only.
- **Rate limit:** Unknown; use 1s delay between requests.

### Island.is Starfatorg — Public GraphQL
- **Endpoint:** `POST https://island.is/api/graphql`
- **Auth:** None
- **Jobs:** ~358 government vacancies
- **Query:** `icelandicGovernmentInstitutionVacancies` returns all vacancies in one call
- **Detail query:** `icelandicGovernmentInstitutionVacancyById(id)` returns salaryTerms, jobPercentage, qualificationRequirements, tasksAndResponsibilities
- **Fields:** id, title, institutionName, location, fieldOfWork, applicationDeadlineFrom/To, intro, salaryTerms (rich text)
- **Salary:** `salaryTerms` is rich text, usually "Laun samkvaemi kjarasamningi" — NLP extraction needed

### Tvinna.is — RSS Feed (deferred to Phase 2)
- 22 tech-focused jobs, minimal structure, poor effort/value ratio
- Trivial to add later once Alfred + Starfatorg are working

## Architecture

### New Files
| File | Purpose |
|------|---------|
| `src/job_extractor.py` | Claude API: job description text → structured fields JSON |
| `src/company_matcher.py` | Match employer names to companies table + Skatturinn API discovery |
| `src/salary_engine.py` | Compute estimated salary from company financials, VR surveys, Hagstofa |
| `scripts/scrape_jobs.py` | Job scraper (Alfred + Starfatorg) |
| `scripts/extract_jobs.py` | AI extraction of structured fields from job descriptions |
| `scripts/match_companies.py` | Match job employers to companies + discover new via Skatturinn |
| `src/templates/jobs.html` | Job search/filter page |
| `.github/workflows/data-pipeline.yml` | Daily autonomous pipeline |

### Modified Files
| File | Changes |
|------|---------|
| `src/database.py` | Add `job_listings` table, `JobListing` dataclass, query functions |
| `src/main.py` | Add `/jobs` + `/api/jobs` routes, job section on company pages |
| `src/templates/company.html` | Add "Laus storf" (open positions) section |
| `scripts/run_pipeline.py` | Add stages 8-11 (scrape, extract, match, estimate salaries) |
| `requirements.txt` | Add `feedparser` (if Tvinna added later) |

### Database Schema

```sql
CREATE TABLE IF NOT EXISTS job_listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,              -- 'alfred', 'starfatorg', 'tvinna'
    source_id TEXT,                    -- external ID from source
    title TEXT NOT NULL,
    employer_name TEXT NOT NULL,
    company_id INTEGER,               -- FK to companies, null until matched
    location TEXT,
    location_lat REAL,
    location_lon REAL,
    employment_type TEXT,              -- 'full-time', 'part-time', 'contract', 'temporary'
    description_raw TEXT,              -- full description HTML/text
    source_url TEXT,
    posted_date TEXT,                  -- ISO date
    deadline TEXT,                     -- ISO date
    -- AI-extracted structured fields (populated by job_extractor)
    work_hours TEXT,                   -- "8:00-16:00", "flexible", "shift"
    remote_policy TEXT,                -- 'remote', 'hybrid', 'onsite', null
    salary_text TEXT,                  -- raw salary mention if found in text
    salary_lower INTEGER,             -- extracted salary range lower (ISK/month)
    salary_upper INTEGER,             -- extracted salary range upper (ISK/month)
    benefits TEXT,                     -- JSON array: ["lunch", "gym", "pension_extra", ...]
    union_name TEXT,                   -- mentioned union name
    languages TEXT,                    -- JSON array: ["is", "en", ...]
    education_required TEXT,           -- "university", "trade", "none", etc.
    experience_years TEXT,             -- "0-2", "3-5", "5+", etc.
    -- Pre-computed salary estimate (updated by pipeline stage 11)
    estimated_salary INTEGER,         -- best salary estimate (ISK/month)
    salary_source TEXT,               -- 'job_listing', 'company_avg', 'vr_survey', 'hagstofa'
    salary_confidence REAL,           -- 0.0-1.0
    salary_details TEXT,              -- human-readable: "company avg, 2023" etc.
    -- Metadata
    extracted_at TEXT,                 -- when AI extraction was last run
    is_active BOOLEAN DEFAULT 1,      -- false when past deadline or removed from source
    created_at DATETIME DEFAULT (datetime('now')),
    updated_at DATETIME DEFAULT (datetime('now')),
    UNIQUE(source, source_id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_company ON job_listings(company_id);
CREATE INDEX IF NOT EXISTS idx_jobs_active ON job_listings(is_active);
CREATE INDEX IF NOT EXISTS idx_jobs_source ON job_listings(source);
CREATE INDEX IF NOT EXISTS idx_jobs_deadline ON job_listings(deadline);
CREATE INDEX IF NOT EXISTS idx_jobs_salary ON job_listings(estimated_salary);
```

### JobListing Dataclass

```python
@dataclass
class JobListing:
    id: Optional[int]
    source: str
    source_id: Optional[str]
    title: str
    employer_name: str
    company_id: Optional[int]
    location: Optional[str]
    employment_type: Optional[str]
    description_raw: Optional[str]
    source_url: Optional[str]
    posted_date: Optional[str]
    deadline: Optional[str]
    work_hours: Optional[str]
    remote_policy: Optional[str]
    salary_text: Optional[str]
    salary_lower: Optional[int]
    salary_upper: Optional[int]
    benefits: Optional[str]       # JSON array
    union_name: Optional[str]
    languages: Optional[str]      # JSON array
    estimated_salary: Optional[int]
    salary_source: Optional[str]
    salary_confidence: Optional[float]
    salary_details: Optional[str]
    is_active: bool
```

### Database Query Functions

```python
def save_job_listing(listing: JobListing) -> int:
    """Upsert job listing. Returns id."""

def get_active_jobs(
    salary_min=None, salary_max=None, location=None,
    employment_type=None, remote_policy=None, benefits=None,
    source=None, limit=50, offset=0
) -> list[dict]:
    """Filter active jobs with pagination."""

def get_company_jobs(company_id: int) -> list[dict]:
    """Active jobs for a specific company."""

def get_unextracted_jobs(limit=100) -> list[dict]:
    """Jobs needing AI field extraction."""

def get_unmatched_jobs() -> list[dict]:
    """Jobs with no company_id match."""

def get_jobs_needing_salary_estimate() -> list[dict]:
    """Jobs where estimated_salary is NULL."""

def deactivate_stale_jobs(source: str, active_source_ids: list[str]):
    """Mark jobs inactive if removed from source or >90 days old."""

def get_job_stats() -> dict:
    """Counts by source, matched %, extracted %, salary coverage."""
```

## Salary Intelligence Engine

The core differentiator. For each job listing, compute an **estimated salary** from multiple sources, prioritized by specificity:

### Priority Order
1. **Job listing itself** — If AI extraction found actual salary numbers in the text (rare, <5% of listings)
2. **Company financials** — `avg_salary` from matched company's latest `annual_reports` entry
3. **VR kjarakannanir** — Occupation-specific salary from `vr_salary_surveys`, matched by job title similarity
4. **Hagstofa industry average** — Industry-wide average by company's ISAT code via `hagstofa.py`

### Display Format
- Primary: "Est. 780,000 kr/mo" (prominently displayed, mono font)
- Source tag: "(company avg, 2023)" or "(IT industry avg)" or "(VR: verkefnastjori)"
- Confidence indicator: solid badge for company-specific, lighter for industry avg

### Implementation
`src/salary_engine.py` with function `estimate_job_salary(job_listing, company=None)`:
- Takes a job listing dict + optional matched company dict
- Returns `{estimate: int, source: str, confidence: float, details: str}`
- **Pre-computed and stored** on `job_listings` table (columns: `estimated_salary`, `salary_source`, `salary_confidence`, `salary_details`)
- Recalculated by pipeline stage 11 nightly — not at render time (1,400 jobs x multiple DB lookups per job = too slow for page load)
- Matches existing pattern where `avg_salary` is pre-computed on `annual_reports`

### VR Title Matching Algorithm
For matching job titles to VR survey occupations (`starfsheiti`):
1. Normalize both strings: lowercase, strip accents, remove punctuation
2. Tokenize into words, remove stop words (og, i, a, vid, fyrir, etc.)
3. Find VR title with highest token overlap (Jaccard similarity)
4. Threshold: require >= 0.4 Jaccard similarity to use as match
5. No Claude API — this is a pure string comparison, zero cost
6. Example: "Senior Software Developer" → tokens ["senior", "software", "developer"] → matches VR "Hugbunadarverkfraedingur" poorly → falls through to Hagstofa industry avg instead
7. Works better for Icelandic titles: "Verkefnastjori" → direct match to VR "Verkefnastjori"

## Job Scraper: `scripts/scrape_jobs.py`

Unified scraper following existing conventions (scrape_log idempotency, rate limiting, CLI args).

### Alfred Scraper
```python
def scrape_alfred(dry_run=False) -> list[dict]:
    """Paginate through Alfred API, return raw job dicts."""
    # GET userapi.alfred.is/api/v2/jobs?page={n}&size=50
    # Continue until page returns fewer than size results
    # Map to internal schema, upsert to job_listings
```

### Starfatorg Scraper
```python
def scrape_starfatorg(dry_run=False) -> list[dict]:
    """Query Island.is GraphQL for government vacancies."""
    # POST island.is/api/graphql with vacancy list query
    # For each vacancy, fetch detail for salaryTerms
    # Map to internal schema, upsert to job_listings
```

### Deactivation
After scraping each source:
1. Mark jobs as inactive if past deadline
2. Mark jobs as inactive if not seen in source for 2 consecutive scrapes
3. Max age: deactivate any job >90 days from `posted_date` regardless of deadline

## Job Field Extractor: `src/job_extractor.py`

Same pattern as `src/extractor.py` — module-level prompt constant + parse function.

### Extraction Prompt
Takes raw job description text, returns JSON:
```json
{
    "work_hours": "8:00-16:00",
    "remote_policy": "hybrid",
    "salary_text": "Laun 750.000 - 900.000 kr",
    "salary_lower": 750000,
    "salary_upper": 900000,
    "benefits": ["lunch", "gym", "flexible_hours", "pension_extra"],
    "union_name": "VR",
    "languages": ["is", "en"],
    "education_required": "university",
    "experience_years": "3-5"
}
```

Fields are nullable — if not mentioned in the job description, return null.

### Batch Processing
Process unextracted jobs: `WHERE extracted_at IS NULL AND is_active = 1`.
Rate limit Claude API calls. Batch mode follows extractor.py v2 pattern.

## Company Matcher: `src/company_matcher.py`

### Matching Strategy
1. **Exact match:** `employer_name` → `companies.name` (case-insensitive)
2. **Normalized match:** Strip legal suffixes (ehf, hf, sf, ses, ohf), normalize whitespace/accents, retry
3. **Skatturinn API lookup:** Search by name fragments → get kennitala → add to companies table
4. **Manual review queue:** Unmatched employers logged for manual resolution

### New Company Pipeline
When a new company is discovered via Skatturinn API:
1. Insert into `companies` table with metadata
2. Add to `scrape_log` as pending for PDF scraping
3. Next pipeline run picks it up for annual report extraction

## Pipeline Integration

Extend `scripts/run_pipeline.py` with 4 new stages (one script per stage, matching existing convention):

| Stage | Name | Script |
|-------|------|--------|
| 8 | Scrape Jobs | `scripts/scrape_jobs.py` — Alfred + Starfatorg |
| 9 | Extract Job Fields | `scripts/extract_jobs.py` — Claude API on unextracted jobs |
| 10 | Match Companies | `scripts/match_companies.py` — employer → company matching + Skatturinn discovery |
| 11 | Estimate Salaries | `scripts/estimate_salaries.py` — pre-compute estimated_salary for all jobs |

## GitHub Actions: `.github/workflows/data-pipeline.yml`

```yaml
name: Data Pipeline
on:
  schedule:
    - cron: '0 6 * * *'  # Daily at 06:00 UTC
  workflow_dispatch: {}    # Manual trigger

jobs:
  pipeline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          playwright install chromium --with-deps
      - name: Run pipeline
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          SKATTURINN_API_KEY: ${{ secrets.SKATTURINN_API_KEY }}
        run: python scripts/run_pipeline.py
      - name: Commit DB changes
        run: |
          git config user.name "Launatrausti Bot"
          git config user.email "bot@launatrausti.is"
          git add launatrausti.db
          git diff --cached --quiet || git commit -m "data: daily pipeline update $(date +%Y-%m-%d)"
          git push
```

## UI: `/jobs` — Job Search Page

### Layout
Left sidebar with filters + main content area with job cards (follows existing `.content-with-sidebar` pattern).

### Filters (sidebar)
- **Salary range:** Min/max inputs (uses estimated salary)
- **Location:** Dropdown (Reykjavik, Akureyri, etc.)
- **Employment type:** Checkboxes (full-time, part-time, contract)
- **Remote:** Checkboxes (remote, hybrid, onsite)
- **Benefits:** Toggle chips (lunch, gym, pension, flexible hours)
- **Source:** Checkboxes (Alfred, Starfatorg, Tvinna)

### Job Cards
Each card displays:
- Job title (Playfair Display font)
- Employer name + financial health badge (if matched)
- **Estimated salary** (IBM Plex Mono, prominent, green)
- Salary source tag: "(company avg)" / "(industry avg)" / "(VR survey)"
- Location
- Employment type + remote badge
- Key benefits as small badges
- Deadline
- "View" link to source job listing

### Endpoints
- `GET /jobs` — HTML page with filters
- `GET /api/jobs?salary_min=700000&location=Reykjavik&remote=hybrid&limit=50&offset=0` — JSON API with pagination

## UI: Company Page Enhancement

Add "Laus storf" (Open Positions) section to `/company/{id}` between existing sections. Shows active job listings for the matched company with extracted fields.

## Testing Strategy

### Unit Tests (`tests/test_jobs.py`)
- Job scraper response parsing (mock HTTP responses)
- AI extraction prompt/parse (mock Claude API)
- Company matching logic (exact, fuzzy, normalized)
- Salary estimation engine (all 4 priority levels)
- Database CRUD for job_listings

### Integration Tests
- API endpoints: `/api/jobs`, `/api/jobs?salary_min=X`
- Template rendering: `/jobs` page loads without errors
- Pipeline stages 8-10 with mock data

## Cost Estimate

- **Claude API (job extraction):** ~1,400 jobs x $0.002/job = ~$2.80 initial, then ~$0.20/day for new listings
- **Skatturinn API (company discovery):** New companies from job matching, within 5,000/month limit
- **Monthly run cost:** ~$6-10/month (Claude API for new job extractions)

## Definition of Done

1. Alfred + Starfatorg scrapers fetch and store real data
2. AI extraction produces structured fields for >90% of jobs
3. Company matcher links employers to companies where matches exist
4. Salary engine computes estimates for all matched jobs
5. `/jobs` page renders with filters, pagination, and estimated salaries
6. Company pages show matched job listings
7. Pipeline stages 8-11 run end-to-end via `run_pipeline.py`
8. GitHub Actions workflow committed and ready to activate
9. All tests pass (`pytest`)
10. App starts without errors: `uvicorn src.main:app --port 8080`
11. Stale job deactivation works (past deadline + 90-day max age)
