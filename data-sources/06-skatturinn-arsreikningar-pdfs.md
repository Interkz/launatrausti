# Skatturinn Ársreikningar (Annual Report PDFs)

## Overview
- **Provider:** Ríkisskattstjóri (Icelandic Tax Authority)
- **Type:** PDF documents
- **Cost:** FREE (electronic access)
- **Portal:** https://www.skatturinn.is/fyrirtaekjaskra/arsreikningaskra/
- **Search:** https://www.skatturinn.is/fyrirtaekjaskra/leit

## Legal Requirement
Companies required to submit annual accounts:
- Public limited companies (hf.)
- Private limited companies (ehf.)
- Limited partnerships (ses.)
- Cooperatives
- Self-owned institutions in business

## How to Access

### Manual Process
1. Go to company search: https://www.skatturinn.is/fyrirtaekjaskra/leit
2. Search by company name or kennitala
3. Click "Gögn úr ársreikningaskrá" (Data from annual accounts registry)
4. Add desired years to shopping cart
5. Download PDFs (free)

### No Bulk API
- Individual lookups only
- No programmatic bulk download
- Rate limiting unknown but likely exists

## Available Data (Inside PDFs)

### Income Statement (Rekstrarreikningur)
| Field (Icelandic) | Field (English) | Useful? |
|-------------------|-----------------|---------|
| Rekstrartekjur | Operating revenue | Yes |
| Rekstrargjöld | Operating expenses | Yes |
| **Launakostnaður** | **Wage costs** | **YES - KEY** |
| Afskriftir | Depreciation | Maybe |
| Fjármunatekjur | Financial income | Maybe |
| Fjármagnsgjöld | Financial expenses | Maybe |
| Hagnaður/Tap | Profit/Loss | Yes |

### Balance Sheet (Efnahagsreikningur)
| Field | Useful? |
|-------|---------|
| Eignir (Assets) | Context |
| Skuldir (Liabilities) | Context |
| Eigið fé (Equity) | Context |

### Notes (Skýringar)
| Field | Useful? |
|-------|---------|
| **Meðalfjöldi starfsmanna** | **YES - KEY** |
| Breakdown of expenses | Maybe |
| Related party transactions | Maybe |

## Key Fields for This Project

### Primary Target
```
Estimated Average Salary = Launakostnaður / Meðalfjöldi starfsmanna
```

### Where to Find Them
- **Launakostnaður:** Usually in income statement or expense breakdown
- **Starfsmenn:** Usually in notes section, sometimes income statement

## PDF Structure Variations

### Keyed-In (Innslegnir)
- Structured, text-based
- Easier to parse
- Standard format
- Available from ~2007+

### Scanned (Skannaðir)
- Image-based
- Requires OCR
- Variable quality
- Older reports

## Technical Extraction Approach

### For Text-Based PDFs
```python
import pdfplumber

with pdfplumber.open('arsreikningur.pdf') as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        tables = page.extract_tables()
        # Parse for launakostnaður, starfsmenn
```

### For Scanned PDFs
```python
import pytesseract
from pdf2image import convert_from_path

images = convert_from_path('arsreikningur.pdf')
for img in images:
    text = pytesseract.image_to_string(img, lang='isl')
    # Parse Icelandic text
```

### LLM-Assisted Extraction
```python
# Use Claude to extract structured data from PDF text
prompt = """
Extract from this Icelandic annual report:
1. Launakostnaður (wage costs) - number in ISK
2. Meðalfjöldi starfsmanna (average employees) - number
3. Rekstrartekjur (revenue) - number in ISK
4. Year of report

Return as JSON.
"""
```

## Challenges

### Volume
- ~30,000+ active companies
- Multiple years per company
- Manual download not scalable

### Parsing Variability
- Different accountants use different formats
- Field names vary slightly
- Table structures inconsistent
- Some reports in English

### Data Quality
- Some reports missing employee counts
- Consolidated vs standalone confusion
- Part-time employee handling varies

## Realistic Scope for PoC

### Targeted Approach
1. **Top 100 employers** - manually download, high impact
2. **One industry** - e.g., all tech companies (ISAT 62)
3. **One year** - start with 2023, expand later

### Estimation
| Scope | Companies | PDFs | Effort |
|-------|-----------|------|--------|
| Top 100 | 100 | 100-300 | 1-2 days |
| Tech sector | ~500 | 500-1500 | 1 week |
| All active | 30,000+ | 90,000+ | Not feasible manually |

## Workflow for PoC

### Phase 1: Manual Collection
1. Get list of target kennitölur (from Skatturinn API)
2. Manually download PDFs for top companies
3. Store in organized folder structure

### Phase 2: Extraction Pipeline
```
PDF → Text extraction → LLM parsing → Structured JSON → Database
```

### Phase 3: Validation
- Spot check extracted values against source
- Flag outliers for manual review
- Build confidence scores

## Output Schema
```json
{
  "kennitala": "5501692829",
  "company_name": "Marel hf.",
  "year": 2023,
  "source": "arsreikningur",
  "extracted_at": "2024-01-15",
  "data": {
    "launakostnadur": 45000000000,
    "starfsmenn": 7500,
    "tekjur": 180000000000,
    "hagnadur": 12000000000
  },
  "calculated": {
    "avg_salary_annual": 6000000,
    "avg_salary_monthly": 500000
  },
  "confidence": 0.95,
  "notes": "Consolidated group figures"
}
```

## Notes
- This is the authoritative source for company-specific wage data
- Free but requires significant extraction effort
- Best combined with Skatturinn API for company metadata
- Consider Creditinfo API if budget allows (they've already parsed this)
