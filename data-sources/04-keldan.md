# Keldan (Financial Portal)

## Overview
- **Provider:** Keldan ehf. (owned by Kóði)
- **Type:** Web portal + subscription service
- **Cost:** PAID (freemium model)
- **Website:** https://keldan.is/
- **Parent Company:** https://www.kodi.is/

## Business Model
- Free tier: Basic market data, hourly updates
- Premium subscription: Full access to registries and reports
- Enterprise: Custom agreements for large users

## Available Data

### Company Information
| Data | Free | Premium |
|------|------|---------|
| Basic company info | Yes | Yes |
| Financial statements (multiple years) | Limited | Yes |
| Annual reports (ársreikningar) | No | Yes |
| Company comparisons | Limited | Yes |
| Monitoring/alerts | No | Yes |

### Market Data
| Data | Available |
|------|-----------|
| Currency exchange rates | Yes |
| Stock prices (OMX) | Yes |
| Bond prices | Yes |
| Mutual funds | Yes |
| Business news | Yes |

### Public Registries Access
- Company registry (RSK)
- Real estate registry
- Vehicle registry
- Official gazette (Lögbirtingablaðið)
- National ID registry

## API Access
**NO PUBLIC API**

From their terms:
> "Óheimilt er að nota upplýsingamiðlun Keldunnar til að safna í gagnagrunn"
> (It is prohibited to use Keldan's information service to collect into a database)

### Gagnatorg API (Related)
Kóði offers a separate API product called Gagnatorg:
- Market data streams
- Requires paid agreement
- Contact: help@kodi.is or +354 562 2800

## Data Format
- Web interface only (React-rendered)
- No bulk export
- Manual copy/download of individual reports

## Pricing
Not publicly listed - contact for quote.

## URLs Found During Research
| URL Pattern | Content |
|-------------|---------|
| `/Fyrirtaeki/Yfirlit/{kt}` | Company overview |
| `/Fyrirtaeki/Arsreikningar/{kt}` | Annual reports |
| `/Company/Compare/{kt}` | Company comparison |
| `/Company/Profile/{kt}` | Company profile |

## What They Have (But Can't Access)
Keldan displays parsed annual report data including:
- Revenue
- Expenses
- Employee information
- Multi-year financials
- Key ratios

**Problem:** All behind subscription + TOS prohibits scraping

## Use Cases for This Project
Limited due to access restrictions:
1. Manual spot-checks to verify other data sources
2. Reference for what fields exist in annual reports
3. Potential paid partnership if project grows

## NOT Viable For
- Bulk data collection
- Automated data pipeline
- Free PoC development

## Alternatives
- Creditinfo API (similar data, has API)
- Direct Skatturinn PDF extraction
- Hagstofa for industry averages

## Contact
- Email: help@keldan.is
- Phone: +354 562 2800 (Kóði)
- Hours: Weekdays 9-16

## Notes
- Good product but wrong fit for this project
- Could revisit if monetization allows paid data access
- Their data comes from same sources we're investigating (Skatturinn, etc.)
