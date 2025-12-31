# Skatturinn API (Company Registry)

## Overview
- **Provider:** Ríkisskattstjóri (Icelandic Tax Authority)
- **Type:** REST API
- **Cost:** FREE (Developer tier)
- **Base URL:** `https://api.skattur.cloud/legalentities/v2`
- **Docs:** https://api.skatturinn.is/

## Rate Limits
| Tier | Calls/Minute | Calls/Month |
|------|--------------|-------------|
| Developer (Free) | 60 | 5,000 |

## Authentication
- Header: `Ocp-Apim-Subscription-Key: <your-key>`
- Or query: `?subscription-key=<your-key>`

## Endpoints

### GET `/{nationalId}`
Returns full company details by kennitala.

### GET `/{nationalId}/overview`
Returns PDF overview document.

## Available Data Fields

### Basic Info
| Field | Type | Description |
|-------|------|-------------|
| `nationalId` | string | Kennitala |
| `name` | string | Company name |
| `additionalName` | string | Trade name |
| `purposeOfEntity` | string | Business purpose |
| `status` | string | Active/inactive |
| `registered` | datetime | Registration date |
| `lastUpdated` | datetime | Last modified |

### Financial (Limited)
| Field | Type | Description |
|-------|------|-------------|
| `initialCapital` | number | Initial capital at founding |
| `shareCapital` | number | Current share capital |
| `shareCapitalCurrency` | string | Currency (ISK) |
| `accountingYear` | string | Fiscal year end |

### Classification
| Field | Type | Description |
|-------|------|-------------|
| `activityCode[]` | array | ISAT codes (industry classification) |
| `legalForm` | object | ehf, hf, ses, etc. |

### Status
| Field | Type | Description |
|-------|------|-------------|
| `deregistration.deregistered` | bool | Is deregistered |
| `deregistration.bankrupcy` | bool | Bankruptcy status |
| `deregistration.insolvency` | bool | Insolvency status |

### Relationships (Board/Directors)
| Field | Type | Description |
|-------|------|-------------|
| `relationships[].type` | string | Relationship type |
| `relationships[].position` | string | Position title |
| `relationships[].nationalId` | string | Person's kennitala |
| `relationships[].name` | string | Person's name |
| `relationships[].address` | object | Person's address |

### VAT Info
| Field | Type | Description |
|-------|------|-------------|
| `vat[].vatNumber` | string | VAT number |
| `vat[].registered` | datetime | VAT registration date |
| `vat[].deRegistered` | datetime | VAT deregistration date |
| `vat[].activityCode` | object | VAT activity classification |

### Address
| Field | Type | Description |
|-------|------|-------------|
| `address[].type` | object | Legal/postal |
| `address[].addressName` | string | Street address |
| `address[].postcode` | string | Postal code |
| `address[].city` | string | City |
| `address[].municipality` | string | Municipality name |

## NOT Available
- Employee count
- Wage costs (launakostnaður)
- Revenue / Income
- Expenses / Profit
- Annual report financials

## Use Cases for This Project
1. Get list of all companies with kennitölur
2. Classify companies by industry (ISAT codes)
3. Get company metadata (address, status, legal form)
4. Link board members across companies
5. Filter active vs bankrupt/deregistered companies

## Example Request
```bash
curl -H "Ocp-Apim-Subscription-Key: YOUR_KEY" \
  "https://api.skattur.cloud/legalentities/v2/5501692829"
```

## Notes
- No bulk/list endpoint discovered - need kennitala to query
- May need to combine with another source to get list of all kennitölur
