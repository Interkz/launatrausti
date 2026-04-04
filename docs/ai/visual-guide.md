# Visual Guide — launatrausti.is

Persistent reference for any model to understand the site's visual state without screenshots.
**Last updated:** 2026-04-04

## Design System

### Color Palette
| Variable | Hex | Usage |
|----------|-----|-------|
| `--lumon-white` | `#f7f7f5` | Body background |
| `--lumon-paper` | `#f0f0ec` | Input backgrounds, table stripes |
| `--lumon-black` | `#0a0f0d` | Body text |
| `--lumon-green` | `#1a3d2e` | Primary brand — headings, CTAs, nav active, salary positive |
| `--lumon-green-light` | `#2a5c47` | Button hover |
| `--lumon-green-muted` | `#3d6b58` | Subdued labels, job source badges |
| `--lumon-border` | `rgba(29,75,57,.14)` | Card borders, dividers |
| `--lumon-grid` | `#c8c8c4` | Heavier dividers, disabled states |
| `--lumon-text-secondary` | `#5a5a56` | Metadata, labels, secondary text |
| `--lumon-accent` | `#8b4513` | Warnings, negative values, accent badges |
| `--salary-high` | `#1a6b3c` | Above-average salary |
| `--salary-low` | `#b8463e` | Below-average salary |
| `--gold` | `#c4841d` | Input focus, union salary card highlight |

### Typography
| Variable | Font | Usage |
|----------|------|-------|
| `--font-display` | Playfair Display | Hero title, page h1s, company names, occupation names, big numbers |
| `--font-sans` | IBM Plex Sans | Body text, nav links, descriptions, labels |
| `--font-mono` | IBM Plex Mono | Salary figures, data values, technical metadata, CAGR/percentages |

Font sizes: 3.5rem (hero) → 2.5rem (page h1) → 1.5rem (section h2) → 1rem (body) → 0.875rem (data) → 0.75rem (labels) → 0.6875rem (metadata)

### Component Inventory
- **Cards** (`.card`): White bg, subtle border (`--lumon-border`), 2px radius, hover shadow. Used for data sections.
- **Stat cards** (`.stats > .stat-card`): Grid of KPI boxes with mono labels and large display values.
- **Benchmark grid** (`.benchmark-grid`): Side-by-side comparison items with company-val vs benchmark-val and colored diff percentage.
- **Year filter** (`.year-filter`): Bordered tab-style switcher for year selection.
- **Ranking rows** (`.ranking-row`): Grid rows (rank | name | salary | meta) with hover highlight.
- **Occupation rows** (`.occupation-row`): Clickable rows linking to samanburdur detail.
- **Job rows** (`.job-row`): Job listing links with title, employer, salary, source attribution.
- **Badges** (`.badge`): Small outlined label chips for sector, employment type.
- **Position bar** (`.position-bar`): CSS-only percentile visualization with fill + marker.
- **Trend arrows** (`.trend-arrow.up/.down`): Green up / red down percentage indicators.

### Layout
- Max width: 1400px (`.container`)
- Padding: 3rem desktop, 1rem mobile
- Mobile breakpoint: 768px
- No grid texture overlay (removed 2026-04-04)
- No card double-borders (removed 2026-04-04)

## Page-by-Page

### `/` — Homepage ("Hvað viltu þéna?")
**Layout:** Hero → search results (if salary entered) → top 20 rankings below fold
- **Hero**: Centered Playfair "Hvað viltu þéna?" + stats subtitle + salary input with green "Leita" button
- **Search results** (when salary entered): Position bar → nearby occupations → "Næsta stig" tier → matching jobs → matching companies
- **Rankings**: "Opinber fyrirtæki" heading with year filter. Top 20 companies as `.ranking-row` grid rows (rank, name, salary kr/mán, employees+year). "Sjá öll X fyrirtæki →" link below.
- **Notice**: "Einkageirinn kemur fljótlega" in green text below heading

### `/samanburdur` — Occupation Comparison
**Layout:** Best-looking page. Salary input → search → ranked leaderboard
- **Leaderboard**: Flat rows with rank number, ISCO group color dot, occupation name, mini salary bar, salary figure
- **Detail view** (when occupation selected): Big salary number with percentile context, p10/p25/median/p75/p90 stat row, year-by-year trend table, 2025 estimate
- **Filters**: heildarlaun/grunnlaun toggle, hæst/lægst sort, year selector, occupation group legend
- 164 occupations, Hagstofa data, 2014-2024

### `/salaries` — Launakannanir (Salary Surveys)
**Layout:** Date filter tabs → category sidebar → survey table
- **Sources**: VR (239 rows, 3 dates) + SSF financial sector (56 rows, "2025-SSF")
- **Table columns**: Starfsheiti, Meðaltal, Miðgildi, 25%, 75%, Svarendur, Dreifing (bar)
- SSF rows show green "SSF" badge next to job title
- Category filter includes "Fjármálageirinn" for SSF data

### `/company/{id}` — Company Detail
**Layout:** Hero → big salary number → comparison → facts grid → VR comparison → ársreikningar → launaþróun → laus störf
- **Hero**: Company name, kennitala, sector badge (Opinbert/Einkageirinn), industry name
- **Big number**: Centered 3rem Playfair salary kr/mán with year attribution
- **Samanburður card**: Company vs industry avg and vs national avg with percentage diffs
- **Facts grid** (2x2): Starfsmenn, Launakostnaður, Hagnaður/Tap, Laun sem % af tekjum
- **VR launakönnun**: Only shown if diff_pct is within ±100% (hides unreasonable comparisons)
- **Ársreikningar table**: All Icelandic headers (Ár, Meðallaun/mán, Meðallaun/ár, Starfsmenn, Launakostnaður, Tekjur)
- **Launaþróun**: Text trend summary with CAGR
- **Laus störf**: Job rows at bottom if company has open positions
- **ALL labels in Icelandic** — no English anywhere

### `/benchmarks` — Atvinnugreinar (Industry Benchmarks)
**Layout:** Year filter → industry table with wage data
- Hagstofa live API data
- Fully translated to Icelandic

### `/jobs` — Störf (Job Listings)
**Layout:** Stats row → filters sidebar → sort toggles → job cards
- Sources: Alfred.is, Starfatorg
- Badge colors now use palette (green-muted, accent) — no off-palette blue/purple
- Employer initial avatar, salary with source badge, location, type badges

### `/stettarfelog` — Stéttarfélög (Union Comparison)
**Layout:** Optional salary input → overview table → cost breakdown table → union detail cards
- 10 unions with fee calculator
- Gold-highlighted salary card if user entered salary
- Fully Icelandic

## Data Totals (as of 2026-04-04)
- 466 companies (205 with real annual reports, all public sector)
- 295 salary survey rows (239 VR + 56 SSF)
- 5,408 Hagstofa occupation records (5,210 with p10/p90 deciles)
- 126 VFÍ dimensional salary records
- 1,169 active job listings
- 164 specific occupations in samanburdur
