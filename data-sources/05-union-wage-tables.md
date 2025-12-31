# Union Wage Tables (Kjarasamningar)

## Overview
- **Type:** Negotiated wage agreements
- **Cost:** FREE (public documents)
- **Format:** PDF documents
- **Update Cycle:** Every 3-4 years (current: 2024-2028)

## What Are Kjarasamningar?
Collective bargaining agreements between unions and employers that set **minimum wages** by job category. These are legal minimums - actual pay is often higher.

## Major Union Federations

### ASÍ (Alþýðusamband Íslands)
- **Website:** https://www.asi.is/
- **Coverage:** Blue-collar workers, general labor
- **Member unions:** Efling, VR, Samiðn, etc.

### BHM (Bandalag háskólamanna)
- **Website:** https://www.bhm.is/vinnurettur/samningar
- **Coverage:** University-educated professionals
- **Member unions:** Engineers, nurses, teachers, etc.

### BSRB (Bandalag starfsmanna ríkis og bæja)
- **Website:** https://www.bsrb.is/
- **Coverage:** Public sector employees

## Key Union Sources

### VR stéttarfélag
- **URL:** https://www.vr.is/kjaramal/kjarasamningar/
- **Coverage:** Retail, office workers, service sector
- **Employer counterpart:** SA (Samtök atvinnulífsins)

### Efling
- **Coverage:** General workers, cleaning, food service
- **Current agreement:** 2024-2028 with SA

### SA (Samtök atvinnulífsins) - Employer Side
- **URL:** https://www.sa.is/vinnumarkadsvefur/kjarasamningar/kjarasamningar-2024-2028/
- **Has:** Kaupgjaldsskrá (wage tables) for all SA agreements
- **Coverage:** Private sector employers

### Reykjavík City
- **URL:** https://reykjavik.is/en/wage-agreements-and-salary-scales
- **Coverage:** Municipal employees
- **Agreements with:** 18 different unions

## Available Data

### Launatöflur (Wage Tables)
| Field | Available |
|-------|-----------|
| Job categories/titles | Yes |
| Minimum monthly wage | Yes |
| Wage steps by experience | Yes |
| Overtime rates | Yes |
| Shift differentials | Yes |
| Holiday pay | Yes |

### What You Can Extract
- Minimum wage by job title
- Wage progression by years of experience
- Differences between union categories
- Year-over-year wage increases

## Data Format
**PDF documents** - requires extraction/parsing

Typical structure:
```
Starfsheiti (Job Title) | Grunnlaun (Base) | Ár 1 | Ár 2 | Ár 3...
------------------------|--------------------|------|------|-------
Afgreiðslumaður         | 425,000 kr        | +5%  | +3%  | +2%
Verslunarstjóri         | 520,000 kr        | +5%  | +3%  | +2%
```

## Limitations

### Only Minimums
These are **floor** wages, not actual wages paid:
- Many companies pay above minimum
- Bonuses not included
- Benefits not captured
- Stock options not included

### Coverage Gaps
- Not all workers are union members
- Some industries have weak union presence
- Executive pay not covered
- Foreign workers sometimes paid differently

### Not Company-Specific
- Same minimums apply across all companies in sector
- Can't differentiate good vs bad employers
- No company performance linkage

## Use Cases for This Project

### Viable Uses
1. Establish wage floors by occupation
2. Show minimum legal pay for job titles
3. Track negotiated wage increases over time
4. Supplement Hagstofa averages with role granularity

### How to Combine with Other Data
```
Estimated actual wage = Union minimum × Industry multiplier (from Hagstofa)
```

Or:
```
Company wage estimate = Hagstofa industry avg × (Company revenue / Industry avg revenue)
```

## PDF Sources to Extract

### Priority Documents
1. **SA Kaupgjaldsskrá** - comprehensive private sector tables
2. **VR kjarasamningur** - office/retail detailed tables
3. **BHM samningar** - professional/specialist rates

### Current Agreements (2024-2028)
| Union | Employer | Signed |
|-------|----------|--------|
| VR | SA | March 2024 |
| Efling | SA | 2024 |
| Samiðn | SA | 2024 |
| BHM | SA | 2024 |
| Sameyki | Reykjavík | June 2024 |

## Technical Approach

### PDF Extraction Options
1. **Manual transcription** - accurate but slow
2. **PDF parsing (PyPDF2, pdfplumber)** - if tables are text-based
3. **OCR (Tesseract)** - if scanned images
4. **LLM extraction** - use Claude to parse tables

### Suggested Schema
```json
{
  "union": "VR",
  "employer": "SA",
  "valid_from": "2024-02-01",
  "valid_to": "2028-01-31",
  "categories": [
    {
      "title": "Afgreiðslumaður",
      "base_wage": 425000,
      "currency": "ISK",
      "period": "monthly",
      "steps": [
        {"years": 0, "wage": 425000},
        {"years": 1, "wage": 446250},
        {"years": 3, "wage": 459638}
      ]
    }
  ]
}
```

## Notes
- Good supplementary data source
- Requires PDF processing effort
- Most valuable for role-specific minimum benchmarks
- Should clearly label as "minimum" not "average" in final product
