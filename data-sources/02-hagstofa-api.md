# Hagstofa (Statistics Iceland) API

## Overview
- **Provider:** Hagstofa Íslands (Statistics Iceland)
- **Type:** PX-Web REST API
- **Cost:** FREE
- **Base URL:** `https://px.hagstofa.is/pxis/api/v1/is/`
- **Docs:** https://statice.is/publications/open-data-access/
- **License:** CC BY 4.0 (fully open, attribution required)

## Rate Limits
| Limit | Value |
|-------|-------|
| Calls/second | 30 |
| Max values/request | 10,000 |

## Authentication
None required - fully public API.

## Python Library
```bash
pip install hagstofan
```

```python
from hagstofan import Hagstofan
hagstofan = Hagstofan()

# Search for datasets
hagstofan.search_datasets('laun')

# Get data
df = hagstofan.get_data(table='VIN02001')
```

## Key Wage/Salary Tables

### VIN02001 - Wages by Occupation & Gender (2014-2024)
- **URL:** https://px.hagstofa.is/pxis/pxweb/is/Samfelag/Samfelag__launogtekjur__1_laun__1_laun/VIN02001.px
- **Fields:** Occupation, Gender, Year, Monthly wages (thousands ISK)
- **Granularity:** Occupation category level

### VIN02003 - Wages by Industry, Occupation & Gender (2014-2024)
- **URL:** https://px.hagstofa.is/pxis/pxweb/is/Samfelag/Samfelag__launogtekjur__1_laun__1_laun/VIN02003.px
- **Fields:** Industry (ISAT), Occupation class, Gender, Year, Wages, Hours
- **Granularity:** Industry + occupation level

### LAU04007 - Wage Index by Industry & Month (2015+)
- **URL:** https://px.hagstofa.is/pxis/pxweb/is/Samfelag/Samfelag__launogtekjur__2_lvt__1_manadartolur/LAU04007.px
- **Fields:** Industry, Month, Wage index
- **Use:** Track wage growth over time by sector

### LAU04000 - Monthly Wage Index (1989+)
- **URL:** https://px.hagstofa.is/pxis/pxweb/is/Samfelag/Samfelag__launogtekjur__2_lvt__1_manadartolur/LAU04000.px
- **Fields:** Month, Overall wage index
- **Use:** Historical wage inflation tracking

## Available Data Categories

### Wages (Laun)
| Data | Available |
|------|-----------|
| Average wages by occupation | Yes |
| Average wages by industry | Yes |
| Wages by gender | Yes |
| Wage indices over time | Yes |
| **Company-specific wages** | **NO** |

### Employment
| Data | Available |
|------|-----------|
| Employment by industry | Yes |
| Employment by occupation | Yes |
| Unemployment rates | Yes |
| **Company employee counts** | **NO** |

## Data Dimensions Available
- **By Industry:** ISAT classification codes
- **By Occupation:** ISCO occupation codes
- **By Gender:** Male/Female/Total
- **By Time:** Monthly, Quarterly, Annual
- **By Region:** Some tables have regional breakdown

## NOT Available
- Company-specific data (any field)
- Individual salary data
- Company names or kennitölur

## Use Cases for This Project
1. Get industry-average wages to benchmark companies
2. Show wage trends over time by sector
3. Compare occupation pay across industries
4. Correlate with company ISAT codes from Skatturinn API

## Example: Fetch Wage Data
```python
from hagstofan import Hagstofan

h = Hagstofan()

# Get wages by occupation
df = h.get_data(table='VIN02001')

# Filter for software developers, 2024
software_wages = df[
    (df['Starfsstétt'] == 'Sérfræðingar í upplýsingatækni') &
    (df['Ár'] == 2024)
]
```

## API Response Format
PX-Web returns data in JSON-stat format, which the `hagstofan` library converts to pandas DataFrames.

## Notes
- Data is aggregated/anonymized - never individual or company level
- Survey-based methodology (sample surveys of employers)
- Updates vary by table - some monthly, some annual
- Can combine ISAT codes with Skatturinn API to estimate company wages by industry average
