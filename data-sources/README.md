# Data Sources Overview

## Quick Reference

| Source | API | Company-Specific | Wage Data | Cost | Effort |
|--------|-----|------------------|-----------|------|--------|
| [Skatturinn API](01-skatturinn-api.md) | Yes | Yes (metadata only) | No | Free | Low |
| [Hagstofa](02-hagstofa-api.md) | Yes | No (industry avg) | Yes | Free | Low |
| [Creditinfo](03-creditinfo-api.md) | Yes | Yes | Yes | Paid | Low |
| [Keldan](04-keldan.md) | No | Yes | Yes | Paid | N/A |
| [Union Tables](05-union-wage-tables.md) | No | No (minimums) | Yes | Free | Medium |
| [Skatturinn PDFs](06-skatturinn-arsreikningar-pdfs.md) | No | Yes | Yes | Free | High |

## For Company-Specific Wage Estimates

### Free Path
```
Skatturinn API (company list + ISAT codes)
         ↓
Skatturinn PDFs (download annual reports)
         ↓
Extract: launakostnaður ÷ starfsmenn = avg salary
         ↓
Enrich with Hagstofa industry benchmarks
```

### Paid Path
```
Creditinfo API
    ↓
Structured annual account data
    ↓
Direct access to wage costs + employee counts
```

## Data Combination Strategy

### Layer 1: Company Foundation
**Source:** Skatturinn API
- All companies with kennitölur
- ISAT industry codes
- Company status (active/bankrupt)
- Board members

### Layer 2: Industry Benchmarks
**Source:** Hagstofa API
- Average wages by ISAT code
- Wage trends over time
- Occupation-level pay data

### Layer 3: Company-Specific (Choose One)

**Option A - Free/Effort:**
- Skatturinn PDFs → Extract launakostnaður + starfsmenn

**Option B - Paid/Easy:**
- Creditinfo API → Direct structured data

### Layer 4: Supplementary
**Source:** Union wage tables
- Minimum wage floors by job title
- Role-specific pay bands

## Recommended PoC Approach

### Phase 1: Foundation (Easy)
1. Set up Skatturinn API integration
2. Get list of target companies (top 100 or one industry)
3. Pull Hagstofa industry averages

### Phase 2: Company Data (Choose)
- **If budget:** Try Creditinfo API
- **If no budget:** Manual PDF download + extraction for top companies

### Phase 3: Enrichment
1. Add union minimum wages for context
2. Calculate estimated ranges per company
3. Show industry comparisons

## Key Metrics to Display

| Metric | Source(s) |
|--------|-----------|
| Estimated avg salary at Company X | PDFs or Creditinfo |
| Industry average salary | Hagstofa |
| Minimum wage for role Y | Union tables |
| Salary trend over years | Hagstofa + historical PDFs |
| Company vs industry comparison | Calculated |

## Files in This Directory

1. `01-skatturinn-api.md` - Free company registry API
2. `02-hagstofa-api.md` - Free statistics API
3. `03-creditinfo-api.md` - Paid annual accounts API
4. `04-keldan.md` - Paid portal (no API)
5. `05-union-wage-tables.md` - Free PDFs (minimums)
6. `06-skatturinn-arsreikningar-pdfs.md` - Free PDFs (actual data)
