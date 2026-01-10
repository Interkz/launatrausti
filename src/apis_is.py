"""
apis.is - Icelandic Open Data API client for company lookups.

Free API with no authentication required.
Documentation: https://docs.apis.is/
"""

import requests
import urllib3
from typing import Optional
from dataclasses import dataclass

# Suppress SSL warnings - apis.is has expired cert but is a trusted public data source
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "http://apis.is/company"


@dataclass
class CompanyInfo:
    """Company information from apis.is."""
    name: str
    kennitala: str  # Social security number (sn)
    address: str
    active: bool


def search_company(
    name: Optional[str] = None,
    kennitala: Optional[str] = None,
    address: Optional[str] = None,
    vsk: Optional[str] = None,
) -> list[CompanyInfo]:
    """
    Search for Icelandic companies via apis.is.

    At least one parameter is required.

    Args:
        name: Company name to search for
        kennitala: Company's kennitala (socialnumber)
        address: Company's address
        vsk: Company's VAT number

    Returns:
        List of matching companies
    """
    params = {}
    if name:
        params["name"] = name
    if kennitala:
        params["socialnumber"] = kennitala
    if address:
        params["address"] = address
    if vsk:
        params["vsknr"] = vsk

    if not params:
        raise ValueError("At least one search parameter is required")

    try:
        # Note: apis.is has SSL cert issues, so we disable verification
        # This is acceptable for a public, read-only data source
        resp = requests.get(BASE_URL, params=params, timeout=15, verify=False)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as e:
        print(f"apis.is error: {e}")
        return []
    except ValueError as e:
        print(f"apis.is JSON error: {e}")
        return []

    results = data.get("results", [])

    companies = []
    for r in results:
        companies.append(CompanyInfo(
            name=r.get("name", ""),
            kennitala=r.get("sn", ""),
            address=r.get("address", ""),
            active=r.get("active") == 1,
        ))

    return companies


def get_company_by_kennitala(kennitala: str) -> Optional[CompanyInfo]:
    """
    Look up a specific company by kennitala.

    Args:
        kennitala: Company's kennitala (10 digits)

    Returns:
        CompanyInfo if found, None otherwise
    """
    results = search_company(kennitala=kennitala)
    return results[0] if results else None


def search_companies_by_name(name: str) -> list[CompanyInfo]:
    """
    Search for companies by name.

    Args:
        name: Full or partial company name

    Returns:
        List of matching companies
    """
    return search_company(name=name)


# Well-known Icelandic companies to seed the database with
# These are large employers that would be interesting for salary data
SEED_COMPANIES = [
    # Banks & Finance
    "Landsbankinn",
    "Íslandsbanki",
    "Arion banki",
    "Kvika banki",
    "Lykill fjármögnun",

    # Tech
    "Marel",
    "CCP",
    "Advania",
    "Sensa",
    "Controlant",
    "Azazo",
    "DataMarket",
    "Vettvangur",
    "Tempo",
    "Kolibri",
    "Aleph",
    "Taktikal",
    "Plain Vanilla",
    "Gangverk",

    # Telecom
    "Síminn",
    "Nova",
    "Vodafone",
    "Sýn",

    # Retail
    "Hagar",
    "Bónus",
    "Hagkaup",
    "Krónan",
    "Costco",
    "IKEA",
    "Elko",

    # Airlines & Transport
    "Icelandair",
    "Play",
    "Eimskip",
    "Samskip",

    # Energy
    "Landsvirkjun",
    "Orkuveita Reykjavíkur",
    "HS Orka",
    "Orkusalan",

    # Media
    "RÚV",
    "Stöð 2",
    "Morgunblaðið",
    "Fréttablaðið",
    "Vísir",

    # Healthcare & Pharma
    "Actavis",
    "Össur",
    "Kerecis",
    "Decode",

    # Construction
    "Íslenska gámafélagið",
    "Ístak",
    "Verkís",

    # Tourism
    "Bláa Lónið",
    "Reykjavík Excursions",
    "Gray Line",
    "Flybus",

    # Food & Beverage
    "Mjólkursamsalan",
    "Ölgerðin",
    "Vífilfell",
    "Sláturfélag Suðurlands",

    # Insurance
    "Sjóvá",
    "Vörður",
    "TM",
    "Vátryggingafélag Íslands",

    # Real Estate
    "Reitir",
    "Reginn",
    "Eik fasteignafélag",
]
