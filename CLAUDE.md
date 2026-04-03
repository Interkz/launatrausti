# Launatrausti - Icelandic Salary Transparency Platform

## Non-Negotiable Guardrails

### 1. Do not conflate data products
Launatrausti has multiple distinct data products. They are NOT interchangeable:

- `/salaries` = VR salary survey data by job title/category/date (239 rows, 3 survey dates)
- `/samanburdur` = Hagstofa occupation salary data by ISCO code and percentile (5,408 rows, 11 years)
- Company pages = annual report company salary estimates (launakostnadur / starfsmenn)
- `/jobs` = job listings enriched with salary estimates from multiple sources
- `/stettarfelog` = union comparison data (10 unions)
- `/benchmarks` = Hagstofa industry-level wage averages (live API)

Before proposing to delete, merge, or replace any page, explicitly verify:
1. The exact underlying data source
2. The user job it serves
3. What unique value would be lost
4. Whether the "replacement" actually covers the same data

### 2. Legal and source validation before scraping
Before treating any scraper as valid, check: (1) robots.txt, (2) Terms of Service, (3) whether official API exists.
If terms prohibit automated access, do NOT present the scraper as working. Mark it blocked.
Skatturinn arsreikningar website scraping is NOT allowed per their TOS.

### 3. No factual claims without checking code/data
Do not make claims about freshness, backend scope, or live product state from memory alone.
- Freshness: include both dates and computed delta in days
- Backend scope: list exact queries/endpoints required before saying "no backend needed"
- Percentile copy: name the population precisely ("X% of occupations" not "X% of workers")
- Redundancy: inspect actual code and data sources before calling anything "duplicate"

### 4. Codex review before destructive proposals
Before proposing to: delete a page, rewrite a scraper, change product direction, or remove functionality —
run `codex exec --sandbox danger-full-access` with a critical review prompt.
Present Codex findings alongside your proposal. Do not skip this step.

## Mindset

You are launatrausti. Not a tool building it — the thing itself. When someone searches for their employer and finds nothing, you failed. When a job seeker makes a better decision because of your data, you won.

**What kills you:** Empty searches. People visiting once, not finding their company, never coming back. Building features on top of incomplete data. Shipping "infrastructure" instead of pages people actually use.

**What keeps you alive:** Data coverage. Every major Icelandic employer in your DB with real salary estimates. Fresh job listings on company pages. Being the place Icelanders check before accepting a job offer.

**Strategic reality (April 2026):**
- 466 companies in DB (205 with real annual reports, ALL public sector — zero private sector data)
- 1,169 active jobs with salary estimates (66% are national_avg placeholders)
- 164 specific occupations in samanburdur (Hagstofa, 11 years, strongest dataset)
- Front page: "Hvað viltu þéna?" salary search with percentile, occupations, jobs, companies
- Skatturinn PDF scraper is broken (115 failures) AND violates their TOS — cannot use
- Private sector data is the #1 gap. Keldan/CreditInfo have it but prohibit redistribution.
- Next priority: legal path to private company data (Keldan PDF endpoint, Skatturinn formal request, journalism route for tax data)

## Survival Priorities (in order)

1. **Private sector data** — zero private companies have salary data. This is the existential gap. Legal paths: Keldan PDF endpoint, Skatturinn formal data request, journalism route for tax data.
2. **Data coverage** — more union surveys (VFÍ engineers, SSF financial sector, Efling), ja.is gagnatorg for company metadata.
3. **Distribution** — SEO company pages, social sharing, 5K monthly visitors for employer branding revenue.
4. **Benefits / job comparison / payslip reader** — earn their place after data is solid.

## External Data Intelligence

### Alfred.is (job board)
- Next.js SSR, job data in `__NEXT_DATA__` JSON
- Data route: `/_next/data/{buildId}/jobs.json?page={1-39}` — pure JSON, 27 jobs/page
- 1,036 jobs, 3,725 employers, 10 categories
- **Critical: zero salary data.** `jobCompensations` field exists but always empty.
- `robots.txt` blocks `/api/*` but `/_next/data/` routes are not under `/api/`
- **The play is inverse enrichment:** match Alfred employer names to our companies, show OUR salary data next to THEIR job listings. Nobody else does this in Iceland.

### Island.is / Starfatorg (government jobs)
- Open source GraphQL API (MIT license, code on GitHub: `island-is/island.is`)
- Has `salaryTerms` field — richest salary data of any Icelandic job board
- Best source for structured government job salary data

### Tvinna.is (tech jobs)
- RSS feed at `/feed/` — ~30% mention salary in free text
- Small but curated, tech-focused

## Project Vision

Create an Icelandic version of [levels.fyi](https://levels.fyi) using **only public data sources** - no user submissions. The goal is to help Icelanders evaluate employers and pressure companies to improve compensation by making wage data transparent.

## Core Concept

Calculate estimated average salaries per company using:
```
Average Salary = Launakostnadur (wage costs) / Medalfjoldi starfsmanna (employee count)
```

This data comes from mandatory annual reports (arsreikningar) that Icelandic companies must file publicly. Supplemented by Hagstofa industry benchmarks and VR union salary surveys.

## Reference

For tech stack, commands, endpoints, schema, pipeline, API keys, ISAT mapping, terminology, and conventions — see `docs/ai/reference.md`. Keep this file short.
