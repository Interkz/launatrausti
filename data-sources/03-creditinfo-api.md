# Creditinfo API (Annual Accounts)

## Overview
- **Provider:** Creditinfo Lánstraust hf.
- **Type:** REST API (Web Service)
- **Cost:** PAID (subscription required)
- **Developer Portal:** https://developer.creditinfo.is/
- **Handbook:** https://developer.creditinfo.is/skatturinn/skatturinn-handbok
- **Website:** https://www.creditinfo.is/

## Database Size
- 600,000+ annual accounts
- Data since 1995
- Largest business information collection in Iceland

## Pricing (as of research)
| Item | Price |
|------|-------|
| Keyed-in annual account | 1,990 kr |
| Scanned annual account | 0 kr (free) |
| Subscription plans | Contact for quote |

Contact: https://www.creditinfo.is/askriftarleidir

## Available Data

### Annual Accounts (Ársreikningar)
| Field | Available | Notes |
|-------|-----------|-------|
| Revenue (Tekjur) | Yes | |
| Expenses | Yes | |
| EBITDA | Yes | Calculated |
| Profit/Loss | Yes | |
| Assets | Yes | |
| Liabilities | Yes | |
| Debt levels | Yes | |
| **Employee info** | Yes | Can filter by employee count |
| **Individual line items** | Yes | From entered accounts |

### Company Information
| Field | Available |
|-------|-----------|
| Company basics | Yes |
| Credit rating | Yes |
| Payment history | Yes |
| Ownership structure | Yes |
| Board/management | Yes |

## API Access Methods
- Web service (vefþjónusta) for integration
- Excel export for analysis
- Web portal for manual lookups

## Data Sources
Creditinfo aggregates from:
- Skatturinn (Tax Authority)
- Þjóðskrá (National Registry)
- Ökutækjaskrá (Vehicle Registry)
- Court records
- Own credit data collection

## Key Features for This Project

### What Makes This Valuable
1. **Structured annual account data** - not PDFs
2. **Individual line items accessible via API**
3. **Historical data back to 1995**
4. **Employee-related fields available**

### Potential Fields (needs confirmation)
Based on typical annual account structure:
- Launakostnaður (wage costs) - likely available
- Meðalfjöldi starfsmanna (average employees) - mentioned
- Launatengd gjöld (payroll taxes) - likely available

## NOT Confirmed
- Exact API endpoints
- Specific field names for wages/employees
- Bulk download capabilities
- Rate limits

## Use Cases for This Project
1. Get actual wage costs per company
2. Get employee counts per company
3. Calculate average salary: `launakostnaður / starfsmenn`
4. Track company financials year-over-year
5. Compare companies within same industry

## Next Steps to Investigate
1. Sign up for developer account
2. Review API handbook at developer portal
3. Get pricing for bulk/subscription access
4. Confirm wage cost and employee fields exist
5. Test API with sample company

## Contact
- Developer support: Through developer.creditinfo.is
- Sales: https://www.creditinfo.is/
- General: info@creditinfo.is

## Notes
- This is the most promising source for company-specific wage data via API
- Cost may be prohibitive for PoC - need to investigate
- May be worth contacting for startup/research pricing
