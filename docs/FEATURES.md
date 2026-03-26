# Launatrausti — Feature Roadmap

> Strategy: Pick ONE feature, perfect it, use it as the quality standard for the rest. No parallel development.

## Current State (March 2026)

7 pages live: Rankings, Company Detail, Financials, Benchmarks, Samanburdur (best — 269 occupations, salary input, percentile), VR Salaries, Launaleynd. 163 real entities. Severance/Lumon aesthetic.

---

## Next Features

### 1. Stettarfelagasamanburdur (Union Comparison) — RECOMMENDED FIRST

Compare Icelandic unions side-by-side. Who gives you the most for your dues?

**What to show:**
- Dues amount (% of salary)
- Services: legal aid, grants, loans, vacation homes, strike fund
- Member count, financial health (from union arsreikningar)
- Sector coverage

**UX vision:**
- Side-by-side picker: "Compare VR vs. Efling vs. SI"
- Each union gets a detail page (like company detail pages)
- Visual comparison cards, not just tables
- Filters: by sector, by benefit type, by dues

**Data sources:** Kjarasamningar (public PDFs), union arsreikningar (public), union websites

**Why first:**
- New standalone page — sets the pattern for "how a new Launatrausti page should feel"
- New data pipeline — PDF scraper pattern becomes template for future features
- Comparison UX — side-by-side pattern feeds into Job Comparison later
- B2B leverage — unions are the target customers. "VR, you're #2 in grants but #5 in legal aid"
- Public data, no privacy concerns

---

### 2. Hlunnindi / Benefits Finder

Which companies offer stock purchase programs (hlutabrefakaup), extra pension, car allowance, gym, etc.?

**Data sources:** Kjarasamningar PDFs, job postings (Alfred, Tvinna)

**Fits as:** Extension of company profiles — add benefits table, show on company detail page + new filterable benefits page

**Value:** Nobody aggregates this in Iceland. "Which companies offer hlutabrefakaup?" has no good answer today.

---

### 3. Launasedill Reader (Payslip Scanner)

Upload your launasedill (payslip PDF/photo), extract salary breakdown, see how you compare.

**Components:**
- OCR + structured extraction (grunnlaun, yfirvinna, lifeyrir, stettarfelagsgjold)
- Compare against company averages and occupation benchmarks
- "Collect" payslips over time — personal salary history

**Considerations:**
- Payslip formats vary by payroll system (DK, Origo, Sameyki)
- Privacy: consider client-side-only processing to avoid GDPR issues
- Very sticky if it works — users return monthly

---

### 4. Starfasamanburdur (Job Comparison)

The dream endgame: pick two jobs/companies, see side-by-side — wages, working hours, overtime, benefits, union, pension, vacation.

**Depends on:** Benefits data (#2) + Union data (#1) existing first. Low effort once data is there — it's a comparison UI on structured data.

**This is the "Google Flights for jobs" feature.** Data completeness is the bottleneck, not engineering.

---

### 5. Ferilskra.is — CV Hub / Talent Marketplace (PARKED)

Public CV profiles. Workers listed like football players. Companies browse and poach without workers having to apply.

**Status:** Separate product, not a Launatrausti feature. Marketplace dynamics (needs both sides). Revisit after Launatrausti has union traction.

Could share brand: "Launatrausti ranks companies. Ferilskra ranks workers."

---

## Ship Order

```
Union Comparison → Benefits → Job Comparison → Payslip Reader
         ↓              ↓            ↓
   sets patterns    adds data    combines all
```

Ferilskra.is = separate venture, park it.
