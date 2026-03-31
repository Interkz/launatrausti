# Samanburdur Page Redesign

## Problem

The /samanburdur page is launatrausti's best feature (269 occupations, percentile ranking, 10 years of data) but the frontend doesn't do the data justice. The percentile result is buried in a small box, the page has three competing entry points, inline styles prevent reuse across pages, and the 2024 data feels stale without trend projections.

## Design Decisions

Validated through visual mockups with the user:

- **White background, color only at focal points** — no decorative elements, no charts that need legends
- **Input first** — salary input is the primary entry point, leaderboard is secondary
- **Result = big number + mini leaderboard** — left side shows salary/percentile text, right side shows you slotted between real occupations
- **Flat ranked list** — no ISCO grouping, just all 269 sorted by median with search
- **Occupation detail** — three numbers (P25/Median/P75) in a row, trend table with % next to salary
- **2025 estimates** — computed from recent YoY trend, labeled as "áætlun"
- **No box plots, no bar charts, no sample sizes** — just numbers

## Page Structure

### State 1: Landing (no salary entered)

```
┌─────────────────────────────────────┐
│  Hvað ertu að þéna?                │
│  [____850.000____] kr  [Bera saman] │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  [Search occupation...] [Leita]     │
├─────────────────────────────────────┤
│  1  Læknar              1.420.000   │
│  2  Flugstjórar         1.205.000   │
│  3  Verkfræðingar       1.024.000   │
│  ...269 occupations sorted by median│
└─────────────────────────────────────┘
```

### State 2: After salary entered

```
┌─────────────────────────────────────┐
│  [____850.000____] kr  [Bera saman] │
└─────────────────────────────────────┘

┌──────────────────┬──────────────────┐
│ Launin þín       │ ...              │
│ 850.000 kr/mán   │ Hugb.forritarar  │
│                  │   952.000        │
│ Hærri en 72%     │ → Þú  850.000   │
│ starfsstétta     │ Bókarar          │
│                  │   798.000        │
│ 269 stéttir 2024 │ ...              │
└──────────────────┴──────────────────┘

(then leaderboard below)
```

Mobile stacks: number on top, mini leaderboard below.

### State 3: Occupation detail (click any occupation)

```
┌─────────────────────────────────────┐
│ ← Til baka                         │
│                                     │
│ Miðgildi launa                      │
│ 952.000 kr/mán  +12.7% vs landsm.  │
│ 2025 áætlun · Hagstofa Íslands     │
├────────────┬───────────┬────────────┤
│ Lægri 25%  │ Miðgildi  │ Efri 25%  │
│ 780.000    │ 952.000   │ 1.180.000 │
├────────────┴───────────┴────────────┤
│ Launaþróun                          │
│ 2025  952.000  +5.2%  (áætlun)     │
│ 2024  905.000  +4.8%               │
│ 2023  863.000  +6.1%               │
│ 2022  813.000  +3.9%               │
│ 2021  782.000                       │
└─────────────────────────────────────┘
```

## Files to Modify

### `src/templates/base.html`
- Add reusable CSS classes for components (hero-input, percentile-result, data-table, filter-controls, etc.)
- Translate nav to Icelandic: Rankings→Fyrirtæki, Industry Benchmarks→Atvinnugreinar, Salaries→Launakannanir
- Mobile responsive rules: stack two-column result, don't hide data

### `src/templates/samanburdur.html`
- Full rewrite replacing inline styles with CSS classes
- Salary input: switch to `type="text" inputmode="numeric"` with hidden input for raw value
- Result section: two-column layout (big number + mini leaderboard)
- Leaderboard: flat ranked list with search, no ISCO grouping
- Occupation detail: three-number row + trend table
- ~25 lines vanilla JS for salary thousand-separator formatting

### `src/main.py` (lines 288-369)
- Compute 2025 estimates: YoY growth from last 2-3 years applied forward
- Build flat sorted list (instead of grouped) for the leaderboard
- Compute nearby occupations for the result mini-leaderboard (2-3 above, 2-3 below)
- Pass `total_occupations` count to template

## 2025 Estimate Logic

```python
# For each occupation with 2+ years of data:
# Use average YoY growth from last 3 available years
# Apply to 2024 value to project 2025
# Mark as estimated in template with "(áætlun)"
```

Conservative: cap growth at ±15% to avoid outlier projections.

## What This Does NOT Include

- Experience/age-based breakdowns (data not available publicly)
- JavaScript charting libraries
- Separate CSS files (stays in base.html style block)
- Changes to other pages (those come after this pattern is validated)
