# Launatrausti - Development Plan

## Current State (Jan 2025)

**Completed:**
- [x] FastAPI web app with company rankings
- [x] SQLite database schema
- [x] Skatturinn API integration (company metadata)
- [x] Hagstofa integration (industry wage benchmarks)
- [x] PDF extraction pipeline (untested with real data)
- [x] Sample data with ISAT codes
- [x] Benchmark comparison on company pages
- [x] `/benchmarks` page showing all industries
- [x] **UI Redesign** - Swiss + Severance (Lumon) aesthetic (2026-01-09)

**Blockers:**
- No bulk list of companies by industry (need Já Gagnatorg)
- No real financial data (need Creditinfo or manual PDF extraction)

---

## Phase 1: Get Real Company Data (BLOCKED ON USER)

### 1.1 Já Gagnatorg - Bulk Company Lists
**Status:** Awaiting user to send email

**Contact:** gagnatorg@ja.is
**Goal:** Get 30-day free trial, download ISAT company mappings

**Once access granted:**
```bash
# Create import script
python scripts/import_ja_companies.py --isat 62  # Tech companies
```

**Files to create:**
- `scripts/import_ja_companies.py` - Parse CSV, import to database

### 1.2 Creditinfo - Financial Data API
**Status:** Awaiting user to send email

**Contact:** https://developer.creditinfo.is/
**Goal:** Get API access to structured ársreikningagögn

**Once access granted:**
- Create `src/creditinfo_api.py`
- Add bulk import script

### 1.3 Alternative: Manual PDF Extraction
**Status:** Ready, needs real PDFs

**Steps:**
1. Download PDFs from https://www.skatturinn.is/fyrirtaekjaskra/leit
2. Save to `pdfs/` folder
3. Run: `python scripts/extract_pdf.py pdfs/file.pdf --kennitala XXXXXXXXXX`
4. Requires `ANTHROPIC_API_KEY`

---

## Phase 2: Data Pipeline

### 2.1 Já Gagnatorg Import Script
```python
# scripts/import_ja_companies.py
# - Download CSV from /v1/dump/businesses-isat
# - Filter by ISAT prefix (e.g., "62" for tech)
# - Import kennitölur + names to database
# - Fetch additional metadata from Skatturinn API
```

### 2.2 Creditinfo Import Script
```python
# scripts/import_creditinfo.py
# - Fetch annual reports for companies in database
# - Extract: launakostnadur, starfsmenn, tekjur
# - Save to annual_reports table
```

### 2.3 Scheduled Updates
- Daily/weekly cron job to fetch new data
- Track last update timestamp
- Incremental updates only

---

## Phase 3: UI Improvements

### 3.1 Search & Filtering
- [ ] Company name search
- [ ] Filter by industry (ISAT)
- [ ] Filter by salary range
- [ ] Filter by company size (employee count)

### 3.2 Data Visualization
- [ ] Salary trend charts (per company)
- [ ] Industry comparison charts
- [ ] Salary distribution histograms

### 3.3 Mobile Responsive
- [ ] Responsive tables
- [ ] Mobile navigation
- [ ] Touch-friendly filters

---

## Phase 4: Advanced Features

### 4.1 Company Comparison
- Side-by-side company comparison
- Multiple years comparison

### 4.2 Alerts & Notifications
- Email alerts when new data available
- Watchlist for specific companies

### 4.3 Data Export
- CSV download
- API for third-party integrations

---

## Technical Debt

### Code Quality
- [ ] Add unit tests for Hagstofa client
- [ ] Add integration tests for API endpoints
- [ ] Type hints throughout codebase

### Performance
- [ ] Add Redis caching for Hagstofa data
- [ ] Database indexes for common queries
- [ ] Pagination for large result sets

### Security
- [ ] Rate limiting on API endpoints
- [ ] Input validation/sanitization
- [ ] CORS configuration for production

---

## Contact Emails (Ready to Send)

### Já Gagnatorg
**To:** gagnatorg@ja.is
**Subject:** API Access - Bulk ISAT Company Data

### Creditinfo
**To:** https://developer.creditinfo.is/
**Subject:** API Access - Ársreikningagögn

### Skatturinn
**To:** skatturinn@skatturinn.is
**Subject:** Aðgangur að ársreikningagögnum

### Keldan
**To:** https://keldan.is/ (contact form)
**Subject:** API aðgangur - Ársreikningagögn

See CLAUDE.md session notes for full email templates.

---

## Quick Reference

**Run the app:**
```bash
uvicorn src.main:app --port 8080 --reload
```

**Key URLs:**
- http://localhost:8080/ - Rankings
- http://localhost:8080/benchmarks - Industry benchmarks
- http://localhost:8080/docs - API docs

**Key files:**
- `src/main.py` - FastAPI routes
- `src/hagstofa.py` - Industry benchmarks
- `src/database.py` - Data models
- `scripts/seed_sample.py` - Test data
