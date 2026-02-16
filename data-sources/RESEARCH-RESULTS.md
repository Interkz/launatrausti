# Data Source Research Results

**Date:** 2026-02-16
**Goal:** Find the fastest path to real salary data for Launatrausti

---

## Executive Summary

There is **no single API** that gives us company-level salary data in Iceland. The path to real data requires combining multiple sources:

1. **Ja Gagnatorg** (email required) gives us a complete company list with ISAT codes
2. **Skatturinn arsreikningaskra** (scrapeable) gives us free annual report PDFs with launakostnadur + employee counts
3. **Hagstofa** (already integrated, free) gives us industry-average benchmarks
4. **VR launarannsokn** (free PDFs) gives us salary-by-job-title data
5. **Creditinfo** (paid) gives us structured annual accounts via API -- the premium path
6. **Rikisreikningur** (free, scrapeable) gives us public sector institution annual accounts

The **fastest path to real data** is:

```
Step 1: Scrape Skatturinn for top-100 company PDFs     [no waiting, build scraper]
Step 2: Extract launakostnadur + starfsmenn with Claude [existing extractor.py]
Step 3: Parse VR launarannsokn PDFs for job-title data  [free, immediate]
Step 4: Email Ja Gagnatorg for ISAT bulk dump           [30-day trial]
Step 5: Email Creditinfo for API pricing                [may be expensive]
```

---

## Source-by-Source Analysis

### 1. Skatturinn API (Company Registry)

| Attribute | Value |
|-----------|-------|
| **Status** | ALREADY INTEGRATED |
| **Signup** | Self-service at https://api.skatturinn.is/ |
| **Cost** | Free (Developer tier: 60 calls/min, 5,000/month) |
| **Data** | Company metadata: name, kennitala, ISAT code, address, status, board members |
| **What's missing** | No financials, no employee counts, no wages |
| **Automation** | Already built in `src/skatturinn_api.py` |
| **Priority** | HIGH - foundation layer, already done |

**Limitation:** No bulk list endpoint -- you need to know the kennitala to query. This is why we need Ja Gagnatorg for the company list.

---

### 2. Hagstofa (Statistics Iceland) API

| Attribute | Value |
|-----------|-------|
| **Status** | ALREADY INTEGRATED |
| **Signup** | None required -- fully public |
| **Cost** | Free, CC BY 4.0 |
| **Data** | Industry-average wages by occupation, gender, time. Wage index. Employment stats. |
| **What's missing** | No company-specific data whatsoever |
| **Automation** | Already built in `src/hagstofa.py` |
| **Priority** | HIGH - benchmark layer, already done |

**Key tables already identified:**
- VIN02001: Wages by Occupation & Gender (2014-2024)
- VIN02003: Wages by Industry, Occupation & Gender
- LAU04007: Wage Index by Industry & Month
- LAU04000: Monthly Wage Index (1989+)

**Additional finding:** The wage index rose 8.7% year-over-year in Q3 2025. Latest monthly data through December 2024 shows 6.4% annual increase. All accessible via existing PX-Web API -- no additional endpoints needed beyond what is already integrated.

---

### 3. Ja Gagnatorg API

| Attribute | Value |
|-----------|-------|
| **Status** | EMAIL REQUIRED |
| **Signup** | Email gagnatorg@ja.is for 30-day trial |
| **Cost** | Monthly 2,350 kr + 14-21 kr/lookup (Registry Access). Full access: 15,600 kr/month. |
| **Data** | Company registry, ISAT codes, kennitolur, addresses, business types |
| **Automation** | REST API with full documentation at gagnatorg.ja.is/docs/skra/v1/ |
| **Priority** | CRITICAL - this is how we get the complete company list |

**Key discovery: Bulk dump endpoints exist!**

The API offers CSV dump endpoints (gzip-compressed):
- `businesses` -- all registered businesses
- `businesses-isat` -- mapping of kennitala to ISAT codes
- `isat` -- all ISAT classification codes
- `business-types` -- all business entity types
- `businesses-vsk-numbers` -- VAT number mappings

This means we can download a **complete list of all Icelandic companies with their ISAT codes** in one API call. This is the missing piece that unlocks everything else.

**Individual lookup endpoints:**
- `GET /v1/businesses/(kennitala)` -- single business lookup
- `GET /v1/businesses` -- search with filtering
- `GET /v1/isat/(code)` -- ISAT classification lookup

**Action required:** Send email requesting 30-day trial. Draft below.

---

### 4. Creditinfo API

| Attribute | Value |
|-----------|-------|
| **Status** | EMAIL REQUIRED, LIKELY PAID |
| **Signup** | Developer portal at https://developer.creditinfo.is/ (JavaScript app, could not verify self-service) |
| **Cost** | Unknown -- "Sja verdskra" (view price list) but prices not public. Individual keyed-in accounts: 1,990 kr each. Scanned originals: free for subscribers. |
| **Data** | 600,000+ annual accounts since 1995. Revenue, expenses, EBITDA, profit/loss, assets, liabilities. Possibly launakostnadur and employee counts (not confirmed on website). |
| **Automation** | Web service (vefthjonusta) API available for subscribers. Developer docs at developer.creditinfo.is. |
| **Priority** | HIGH VALUE but possibly expensive |

**Key insight:** Creditinfo has already parsed the same PDFs we would be scraping from Skatturinn. If their API includes launakostnadur and meðalfjoldi starfsmanna fields, this would save enormous PDF extraction effort.

**Risk:** Pricing may be prohibitive for a side project. Per-account pricing (1,990 kr x thousands of companies) would be very expensive. Need to ask about bulk/subscription pricing and whether startup/research rates exist.

**Also offers:**
- 5-year financial comparisons exportable to Excel
- Credit ratings
- Payment history
- Ownership structure
- KYC API (separate product)

**Action required:** Email/contact for API pricing and to confirm wage-related fields exist. Draft below.

---

### 5. Keldan

| Attribute | Value |
|-----------|-------|
| **Status** | SKIP |
| **Signup** | Subscription required |
| **Cost** | Not public -- contact for quote |
| **Data** | Same annual account data as Creditinfo (they source from same places) |
| **Automation** | NO PUBLIC API. Terms explicitly prohibit scraping: "Oheimilt er ad nota upplysingamidlun Keldunnar til ad safna i gagnagrunn" |
| **Priority** | LOW -- not viable for this project |

**Decision:** Skip entirely. Same data available through Creditinfo (with API) or direct Skatturinn PDFs (free). Their TOS prohibits the exact use case we need.

---

### 6. Union Wage Tables (Kjarasamningar)

| Attribute | Value |
|-----------|-------|
| **Status** | FREE, IMMEDIATE ACCESS |
| **Signup** | None -- public documents |
| **Cost** | Free |
| **Data** | Minimum wages by job category, wage progression by experience, overtime rates |
| **Automation** | PDF parsing required |
| **Priority** | MEDIUM -- good supplementary data, but only minimums |

**Key limitation:** These are negotiated **minimum** wages, not actual wages paid. Many companies pay significantly above minimums.

**Most useful sources:**
- SA Kaupgjaldsskra (private sector wage tables): https://www.sa.is/vinnumarkadsvefur/kjarasamningar/
- VR kjarasamningur (office/retail): https://www.vr.is/kjaramal/kjarasamningar/
- BHM samningar (professionals): https://www.bhm.is/vinnurettur/samningar

**Current agreements (2024-2028):** All major unions signed new agreements in 2024 with ~3.25-3.5% annual increases.

**Decision:** Parse these as supplementary "wage floor" data. Label clearly as minimums in the UI.

---

### 7. VR Launarannsokn (Salary Survey)

| Attribute | Value |
|-----------|-------|
| **Status** | FREE, IMMEDIATE ACCESS |
| **Signup** | None -- PDFs are public |
| **Cost** | Free |
| **Data** | Actual salaries by job title. Median, mean, 25th/75th percentiles. Based on member survey. |
| **Automation** | PDF parsing required. Published as PDFs at regular intervals. |
| **Priority** | HIGH -- actual salary data by job title, not just minimums |

**Available PDFs found:**
- September 2025: https://www.vr.is/media/2f3e21zj/launarannsokn_september_2025.pdf
- September 2024: https://www.vr.is/media/n4ed1zfs/launatafla_vefur.pdf
- February 2024: https://www.vr.is/media/ogvfb001/launarannsokn_tafla_februar2024.pdf
- February 2023: https://www.vr.is/media/y10ihrjt/tafla_launarannsokn.pdf
- February 2021: https://www.vr.is/media/fvrjaulf/laun_eftir_starfsheiti_februar_2021.pdf

**Data includes:** Salary by starfsstett (job category), with midgildi (median), medaltal (mean), 25% and 75% percentiles. Only published when 10+ respondents behind each figure.

**VR Launaspa (Wage Forecast):** VR also has a machine learning salary calculator at https://www.vr.is/kannanir/launaspa-vr-launarannsokn/ but it requires member login (Minar sidur). Not accessible for scraping.

**Limitation:** Only covers VR members (retail, office, service workers). Does not cover tech workers, engineers, healthcare, etc.

**Action:** Download all available PDFs and parse with Claude. This gives us immediate real salary data.

---

### 8. Skatturinn Arsreikningaskra (Annual Report PDFs)

| Attribute | Value |
|-----------|-------|
| **Status** | FREE, SCRAPEABLE |
| **Signup** | None -- free electronic access |
| **Cost** | Free |
| **Data** | Full annual reports: launakostnadur, starfsmenn, tekjur, hagnadur. THE authoritative source. |
| **Automation** | No API, but the web interface can be scraped with Selenium |
| **Priority** | CRITICAL -- this is our primary source for company-specific wage data |

**How it works:**
1. Search at https://www.skatturinn.is/fyrirtaekjaskra/leit
2. Enter kennitala
3. Click "Gogn ur arsreikningaskra"
4. Add years to shopping cart
5. Download PDFs (free)

**No bulk API exists.** Confirmed through multiple searches. Skatturinn offers web services for VAT and withholding tax, but NOT for arsreikningaskra.

**Scraping approach:**
- Use Selenium/Playwright to automate the manual process
- Input kennitala, navigate to arsreikningaskra section, download PDFs
- Rate-limit to avoid being blocked
- Start with top 100 companies, expand to ISAT sectors

**Key URL patterns discovered:**
- Company search: `https://www.skatturinn.is/fyrirtaekjaskra/leit/kennitala/{kt}`
- Annual accounts are linked from there

**Extraction pipeline (already built):**
```
PDF -> pdfplumber (text extraction) -> Claude API (structured extraction) -> JSON -> SQLite
```

The `src/extractor.py` is already built and ready. Just needs real PDFs.

---

### 9. Rikisreikningur (Government Annual Accounts)

| Attribute | Value |
|-----------|-------|
| **Status** | FREE, SCRAPEABLE |
| **Signup** | None -- fully public |
| **Cost** | Free |
| **Data** | Annual accounts for ALL public institutions and municipalities. Includes laun (wages), launatengd gjold (payroll taxes), benefits. |
| **Automation** | PDF files with predictable URL patterns |
| **Priority** | HIGH for public sector data |

**Key finding: Predictable URL pattern for downloads**

Files are at: `https://arsreikningar.rikisreikningur.is/Stofnun/GetFile/{id}`

Where `{id}` is a sequential numeric ID. The site lists all institutions by ministry with links to their PDFs.

**Coverage:**
- All government ministries (10+)
- Hundreds of subordinate agencies and institutions
- Years: 2022-2024 visible
- Includes wage data (laun), salary-related costs, board/executive compensation

**Additional resources discovered:**
- `https://rikisreikningur.is/utgefin-gogn` -- published government financial data (JavaScript app)
- `https://island.is/opnir-reikningar-rikisins` -- Open Accounts portal showing paid invoices (updated monthly)

**Scraping approach:**
- Enumerate all institution IDs from the listing page
- Download PDFs via GetFile/{id}
- Parse with same Claude extraction pipeline as private sector reports

---

### 10. Stjornarradid Forstodumanna Laun (Executive Pay)

| Attribute | Value |
|-----------|-------|
| **Status** | FREE, IMMEDIATE |
| **Signup** | None |
| **Cost** | Free |
| **Data** | Named salaries for heads of all government institutions |
| **Automation** | Downloadable PDF |
| **Priority** | MEDIUM -- good for transparency angle, small dataset |

**URL:** https://www.stjornarradid.is/verkefni/mannaudsmal-rikisins/laun-forstodumanna/

Includes:
- Complete list of forstodumenn (institution heads) with total compensation
- Updated June 2025, sourced from State Treasury
- Evaluated using unified job evaluation system
- Also has "Forstodumannalisti" with all names

**Action:** Download the PDF and parse it. Small, high-value dataset.

---

### 11. Alex Harri's Icelandic Developer Survey

| Attribute | Value |
|-----------|-------|
| **Status** | FREE, PUBLIC |
| **Signup** | None |
| **Cost** | Free |
| **Data** | Developer salaries by age, industry, technology. Salary brackets. Benefits. |
| **Automation** | Web scraping or manual extraction |
| **Priority** | LOW-MEDIUM -- niche (tech only) but high quality for that niche |

**URL:** https://alexharri.com/blog/icelandic-developer-survey-2024

Published July 2024. Covers monthly salary in ISK brackets, split by age, industry (public vs banking vs other), and benefits. Not raw data -- aggregate results from survey.

**Limitation:** Salary brackets, not exact numbers. Only developers. No company-level data.

**Decision:** Nice to reference but not a primary data source. Could link to it from the tech industry page.

---

### 12. BHM (University Graduates Union)

| Attribute | Value |
|-----------|-------|
| **Status** | PARTIAL ACCESS |
| **Signup** | Some data public, wage calculator likely member-only |
| **Cost** | Free (public data) |
| **Data** | Salary information for university-educated professionals. Collective agreements. |
| **Priority** | MEDIUM -- covers professionals not in VR |

**Key finding:** BHM publishes salary data showing that public sector BHM members received a 1.24% increase in September 2025. Collective agreements available at https://www.bhm.is/vinnurettur/samningar.

**Action:** Check their website for any published launarannsokn PDFs similar to VR's.

---

## Action Plan

### Phase 1: Immediate Actions (No Waiting Required)

#### 1A. Download and parse VR launarannsokn PDFs
**Effort:** 2-4 hours
**Value:** Immediate real salary data by job title

```
Download these PDFs:
- https://www.vr.is/media/2f3e21zj/launarannsokn_september_2025.pdf
- https://www.vr.is/media/n4ed1zfs/launatafla_vefur.pdf
- https://www.vr.is/media/ogvfb001/launarannsokn_tafla_februar2024.pdf
- https://www.vr.is/media/y10ihrjt/tafla_launarannsokn.pdf

Parse with Claude -> structured JSON -> database
```

#### 1B. Build Skatturinn arsreikningaskra scraper
**Effort:** 1-2 days
**Value:** THE core dataset -- company-level wage data

Build a Playwright/Selenium script that:
1. Takes a kennitala as input
2. Navigates to `https://www.skatturinn.is/fyrirtaekjaskra/leit/kennitala/{kt}`
3. Clicks "Gogn ur arsreikningaskra"
4. Adds most recent year to cart
5. Downloads PDF
6. Runs through extractor.py

Start with the 6 companies already in the database (Landsbankinn, Arion, Islandsbanki, Siminn, Marel).

#### 1C. Download Rikisreikningur public sector PDFs
**Effort:** 4-8 hours
**Value:** Complete public sector wage data

1. Scrape the institution listing from `https://arsreikningar.rikisreikningur.is/stofnun`
2. Download all PDFs via `GetFile/{id}` pattern
3. Run through same extraction pipeline

#### 1D. Download Stjornarradid executive pay PDF
**Effort:** 30 minutes
**Value:** Named executive salaries for all government institutions

Download from https://www.stjornarradid.is/verkefni/mannaudsmal-rikisins/laun-forstodumanna/

---

### Phase 2: Emails to Send

#### Email 1: Ja Gagnatorg -- Request 30-day trial

**To:** gagnatorg@ja.is
**Subject:** Beidni um prufu-adgang -- Gagnatorg API

```
Sael/soell,

Eg er ad vinna ad opnu verkefni sem heitir Launatrausti -- vefur sem birtir
launaupplysingar fyrirtaekja a Islandi, byggt a opinberum gognum (arsreikningar,
Hagstofa o.fl.).

Eg hef ahuga a ad fa 30 daga prufuadgang ad Gagnatorg API, serstaklega:

1. Businesses dump -- listi yfir oll skrad fyrirtaeki med kennitolum
2. Businesses-ISAT dump -- tengingar fyrirtaekja vid ISAT atvinnugreinaflokka
3. ISAT flokkun -- uppfletting a atvinnugreinakoda

Tilgangurinn er ad byggja upp gagnasafn fyrirtaekja flokkad eftir atvinnugreinum,
sem sidan er tengt vid opinber fjarhagsgogn (arsreikninga).

Verkefnid er ekki i fjarhagslegu avinningsmarkmidum a thessu stigi -- that er
nytaverkefni til ad auka gagnsaei a islenskum vinnumarkadi.

Er haegt ad fa prufuadgang?

Bestu kvedju,
[Nafn]
[Netfang]
[Simi]
```

#### Email 2: Creditinfo -- Request API pricing and field confirmation

**To:** info@creditinfo.is (or through developer.creditinfo.is contact)
**Subject:** API adgangur -- arsreikningagogn og launaupplysingar

```
Sael/soell,

Eg er ad throdast opid verkefni sem heitir Launatrausti -- upplysingSidur um
laun a islenskum vinnumarkadi, byggt a opinberum gognum.

Eg hef ahuga a ad nota Creditinfo API til ad na i uppbygd arsreikningagogn.
Mer er serlega thad mikilvagt ad geta nalgast eftirfarandi reiti:

1. Launakostnadur (wage costs)
2. Medalfjoldi starfsmanna (average employee count)
3. Rekstrartekjur (revenue)
4. Ar arsreiknings

Spurningar:
a) Eru thessi reiti (serstaklega launakostnadur og starfsmannafjoldi)
   aofengolguleg gegnum API-id?
b) Hvad kostar adgangur? Er til askriftarleifur sem henta lidum verkefnum
   eda nyskopanarfyrirtaekjum?
c) Er haegt ad na i gogn i magni (t.d. oll fyrirtaeki med akvedinn ISAT koda)?
d) Er mogulegt ad fa prufu-adgang til ad kanna API-id?

Verkefnid er ekker-avinningsdrifid a thessu stigi og midar ad opnum
launaupplysingum a islenskum vinnumarkadi.

Bestu kvedju,
[Nafn]
[Netfang]
[Simi]
```

#### Email 3: Skatturinn -- Ask about bulk/API access to arsreikningar

**To:** fyrirtaekjaskra@skatturinn.is
**Subject:** Beidni um upplysingar -- magnadgang ad arsreikningaskra

```
Sael/soell,

Eg vinn ad opnu verkefni sem safnar saman opinberum fjarhagsgognum
islenskra fyrirtaekja til ad auka gagnsaei a vinnumarkadi.

Eg nyta mer tha nu thegar Fyrirtaekjaskra API-id (developer adgangur) til
ad soekja grunngogn um fyrirtaeki.

Mer er forvitni a ad vita:
1. Er til vefthjonusta eda API til ad soekja arsreikninga a rafraenu formi,
   likt og til er fyrir fyrirtaekjaskra?
2. Er haegt ad soekja arsreikninga i magni (t.d. eftir ISAT flokki eda arsbili)?
3. Ef engin slik thjonusta er til, eru einhver fyriraetlan ad bjoda slikt?

Eg skil ad arsreikningar eru opinn gogn og adgengilegir okeypis a vefnum.
Eg spyr einungis hvort til se leifur til ad na i thau gogn a sjaalfvirkan hatt
frekar en ad soekja einn og einn.

Bestu kvedju,
[Nafn]
[Netfang]
[Simi]
```

---

### Phase 3: Scrapers to Build

#### Scraper 1: Skatturinn Arsreikningar PDF Downloader

**Priority:** CRITICAL
**Tech:** Python + Playwright (handles JavaScript-rendered pages)
**Input:** List of kennitolur
**Output:** PDF files in organized directory

```python
# Pseudocode for scripts/scrape_arsreikningar.py
# 1. For each kennitala:
#    a. Navigate to skatturinn.is/fyrirtaekjaskra/leit/kennitala/{kt}
#    b. Find and click "Gogn ur arsreikningaskra" link
#    c. Select most recent year(s)
#    d. Add to cart and download
#    e. Save as pdfs/{kennitala}_{year}.pdf
# 2. Rate limit: max 1 request per 5 seconds
# 3. Start with SAMPLE_KENNITOLUR from skatturinn_api.py
```

#### Scraper 2: Rikisreikningur Institution PDFs

**Priority:** HIGH
**Tech:** Python + requests (simple HTTP downloads)
**Input:** Institution listing page
**Output:** PDF files for all institutions

```python
# Pseudocode for scripts/scrape_rikisreikningur.py
# 1. Fetch https://arsreikningar.rikisreikningur.is/stofnun
# 2. Parse HTML to extract all institution names and GetFile IDs
# 3. For each institution:
#    a. Download PDF from /Stofnun/GetFile/{id}
#    b. Save as pdfs/rikis/{institution_name}_{year}.pdf
# 4. Run through extractor.py
```

#### Scraper 3: VR Launarannsokn PDF Parser

**Priority:** HIGH
**Tech:** Python + pdfplumber + Claude API
**Input:** Downloaded VR PDFs
**Output:** Structured JSON with salary by job title

```python
# Pseudocode for scripts/parse_vr_launarannsokn.py
# 1. Open PDF with pdfplumber
# 2. Extract tables
# 3. Parse columns: Starfsheiti, Midgildi, Medaltal, 25%, 75%
# 4. Output structured JSON per job category
# 5. Import to database
```

---

### Phase 4: Sources to Skip

| Source | Reason |
|--------|--------|
| **Keldan** | No API, TOS prohibits scraping, same data available elsewhere |
| **Alex Harri survey** | Too niche (developers only), aggregate brackets not raw data |
| **Opnir reikningar rikisins** | Invoice data, not salary data. Shows what government paid to vendors, not employee salaries. |
| **apis.is** | Service is down (502 Bad Gateway). Previously aggregated Ja.is + other data but no longer operational. |

---

## Cost Summary

| Source | Cost | Notes |
|--------|------|-------|
| Skatturinn API | Free | Already integrated |
| Hagstofa API | Free | Already integrated |
| Skatturinn PDFs | Free | Scraping + Claude API costs for extraction |
| VR launarannsokn | Free | PDF parsing |
| Rikisreikningur | Free | PDF scraping + extraction |
| Ja Gagnatorg | ~2,350 kr/mo + per-lookup, or 30-day free trial | Need trial first |
| Creditinfo | Unknown (likely expensive) | Must email for pricing |
| Claude API costs | ~$0.01-0.05 per PDF extraction | For extractor.py runs |

**Total estimated cost for PoC: Near zero** (if we use Gagnatorg trial + free Skatturinn PDFs + Claude API for extraction)

---

## Priority Matrix

```
                    HIGH VALUE
                       |
  Ja Gagnatorg --------+-------- Skatturinn PDFs (scraper)
  (company list)       |         (wage data per company)
                       |
  VR Launarannsokn ----+-------- Rikisreikningur
  (salary by job)      |         (public sector wages)
                       |
  Creditinfo ----------+-------- Hagstofa (done)
  (structured data)    |         (industry benchmarks)
                       |
                    LOW VALUE
                       |
  BHM/Union tables ----+-------- Keldan (skip)
  (minimums only)      |
                       |
  LOW EFFORT --------- + -------- HIGH EFFORT
```

---

## Recommended Execution Order

1. **Today:** Download VR launarannsokn PDFs (4 files, free, immediate)
2. **Today:** Download Stjornarradid executive pay PDF (1 file, free)
3. **Today:** Send email to Ja Gagnatorg requesting trial
4. **Today:** Send email to Creditinfo requesting pricing
5. **Today:** Send email to Skatturinn asking about bulk API
6. **This week:** Build Skatturinn PDF scraper (Playwright)
7. **This week:** Build Rikisreikningur PDF scraper (requests)
8. **This week:** Parse VR PDFs into structured data
9. **When trial arrives:** Import Ja Gagnatorg company dump
10. **When pricing arrives:** Evaluate Creditinfo vs scraping ROI
