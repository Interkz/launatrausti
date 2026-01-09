"""
Hagstofa (Statistics Iceland) API client for industry wage benchmarks.

Uses the PX-Web API to fetch average wages by industry from table VIN02003.
Data is cached in-memory to avoid excessive API calls.
"""

import requests
from typing import Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

# Hagstofa PX-Web API
BASE_URL = "https://px.hagstofa.is/pxis/api/v1/is"
WAGE_TABLE = "Samfelag/launogtekjur/1_laun/1_laun/VIN02003.px"

# Cache duration (1 day - data updates infrequently)
CACHE_DURATION = timedelta(hours=24)


@dataclass
class IndustryWage:
    """Industry wage benchmark data."""
    industry_code: str  # Hagstofa code (e.g., "J", "K")
    industry_name: str  # Full name in Icelandic
    year: int
    monthly_wage: int  # Average monthly wage in ISK
    annual_wage: int  # monthly * 12


# ISAT code to Hagstofa industry code mapping
# ISAT uses detailed codes (e.g., 62.01), Hagstofa uses letter codes (e.g., J)
ISAT_TO_HAGSTOFA = {
    # C - Manufacturing (10-33)
    **{str(i): "C" for i in range(10, 34)},
    # D - Electricity, gas (35)
    "35": "D",
    # E - Water, waste (36-39)
    **{str(i): "E" for i in range(36, 40)},
    # F - Construction (41-43)
    **{str(i): "F" for i in range(41, 44)},
    # G - Wholesale/retail (45-47)
    **{str(i): "G" for i in range(45, 48)},
    # H - Transport, storage (49-53)
    **{str(i): "H" for i in range(49, 54)},
    # I - Accommodation, food (55-56)
    **{str(i): "I" for i in range(55, 57)},
    # J - Information, communication (58-63) - TECH/IT
    **{str(i): "J" for i in range(58, 64)},
    # K - Finance, insurance (64-66)
    **{str(i): "K" for i in range(64, 67)},
    # L - Real estate (68)
    "68": "L",
    # M - Professional, scientific (69-75)
    **{str(i): "M" for i in range(69, 76)},
    # N - Administrative (77-82)
    **{str(i): "N" for i in range(77, 83)},
    # O - Public administration (84)
    "84": "O",
    # P - Education (85)
    "85": "P",
    # Q - Health, social (86-88)
    **{str(i): "Q" for i in range(86, 89)},
    # R - Arts, entertainment (90-93)
    **{str(i): "R" for i in range(90, 94)},
    # S - Other services (94-96)
    **{str(i): "S" for i in range(94, 97)},
}

# Human-readable industry names (Icelandic)
INDUSTRY_NAMES = {
    "0": "Allar atvinnugreinar",
    "C": "Framleiðsla",
    "D": "Rafmagns-, gas- og hitaveitur",
    "E": "Vatnsveita, fráveitа, meðhöndlun úrgangs",
    "F": "Byggingarstarfsemi",
    "G": "Heild- og smásöluverslun",
    "H": "Flutningar og geymsla",
    "I": "Gististaðir og veitingar",
    "J": "Upplýsingar og fjarskipti",  # Tech/IT
    "K": "Fjármála- og vátryggingastarfsemi",  # Finance
    "L": "Fasteignaviðskipti",
    "M": "Sérfræði-, vísinda- og tækniþjónusta",
    "N": "Stjórnsýsla og stoðþjónusta",
    "O": "Opinber stjórnsýsla",
    "P": "Fræðslustarfsemi",
    "Q": "Heilbrigðis- og félagsþjónusta",
    "R": "Listir, afþreying og tómstundir",
    "S": "Önnur þjónusta",
}

# English industry names for UI
INDUSTRY_NAMES_EN = {
    "0": "All industries",
    "C": "Manufacturing",
    "D": "Electricity, gas, utilities",
    "E": "Water, waste management",
    "F": "Construction",
    "G": "Wholesale & retail trade",
    "H": "Transport & storage",
    "I": "Accommodation & food service",
    "J": "Information & communication",  # Tech/IT
    "K": "Finance & insurance",
    "L": "Real estate",
    "M": "Professional & scientific services",
    "N": "Administrative services",
    "O": "Public administration",
    "P": "Education",
    "Q": "Health & social work",
    "R": "Arts & entertainment",
    "S": "Other services",
}


class HagstofaCache:
    """Simple in-memory cache for Hagstofa data."""

    def __init__(self):
        self._data: dict[str, dict[int, IndustryWage]] = {}  # code -> year -> wage
        self._last_fetch: Optional[datetime] = None

    def is_valid(self) -> bool:
        if self._last_fetch is None:
            return False
        return datetime.now() - self._last_fetch < CACHE_DURATION

    def get(self, industry_code: str, year: int) -> Optional[IndustryWage]:
        if not self.is_valid():
            return None
        return self._data.get(industry_code, {}).get(year)

    def set(self, wage: IndustryWage):
        if wage.industry_code not in self._data:
            self._data[wage.industry_code] = {}
        self._data[wage.industry_code][wage.year] = wage

    def mark_fetched(self):
        self._last_fetch = datetime.now()

    def get_all_industries(self, year: int) -> list[IndustryWage]:
        """Get all industries for a given year."""
        result = []
        for code_data in self._data.values():
            if year in code_data:
                result.append(code_data[year])
        return sorted(result, key=lambda w: w.annual_wage, reverse=True)


# Global cache instance
_cache = HagstofaCache()


def fetch_industry_wages(years: Optional[list[int]] = None) -> dict[str, dict[int, IndustryWage]]:
    """
    Fetch average wages by industry from Hagstofa.

    Args:
        years: List of years to fetch. Defaults to last 3 years.

    Returns:
        Dict mapping industry_code -> year -> IndustryWage
    """
    if years is None:
        current_year = datetime.now().year
        years = [current_year, current_year - 1, current_year - 2]

    url = f"{BASE_URL}/{WAGE_TABLE}"

    # Build query for all industries, all genders, all occupations
    # Using "Heildarlaun - fullvinnandi" (total wages, full-time) and average
    query = {
        "query": [
            {"code": "Ár", "selection": {"filter": "item", "values": [str(y) for y in years]}},
            {"code": "Atvinnugrein", "selection": {"filter": "all", "values": ["*"]}},
            {"code": "Starfsstétt", "selection": {"filter": "item", "values": ["0"]}},  # All occupations
            {"code": "Kyn", "selection": {"filter": "item", "values": ["0"]}},  # All genders
            {"code": "Laun og vinnutími", "selection": {"filter": "item", "values": ["7"]}},  # Total wages full-time
            {"code": "Eining", "selection": {"filter": "item", "values": ["0"]}},  # Average
        ],
        "response": {"format": "json-stat2"}
    }

    try:
        resp = requests.post(url, json=query, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Hagstofa API error: {e}")
        return {}

    # Parse JSON-stat2 format
    year_dim = data["dimension"]["Ár"]["category"]
    industry_dim = data["dimension"]["Atvinnugrein"]["category"]
    values = data["value"]

    year_codes = list(year_dim["index"].keys())
    industry_codes = list(industry_dim["index"].keys())
    industry_labels = industry_dim["label"]

    result: dict[str, dict[int, IndustryWage]] = {}

    # Values are in row-major order: year x industry
    for j, year_code in enumerate(year_codes):
        year = int(year_code)
        for i, ind_code in enumerate(industry_codes):
            val_idx = j * len(industry_codes) + i
            if val_idx >= len(values) or values[val_idx] is None:
                continue

            monthly_wage = int(values[val_idx] * 1000)  # Convert from thousands
            annual_wage = monthly_wage * 12

            wage = IndustryWage(
                industry_code=ind_code,
                industry_name=industry_labels.get(ind_code, ind_code),
                year=year,
                monthly_wage=monthly_wage,
                annual_wage=annual_wage,
            )

            if ind_code not in result:
                result[ind_code] = {}
            result[ind_code][year] = wage

            # Update cache
            _cache.set(wage)

    _cache.mark_fetched()
    return result


def get_industry_benchmark(isat_code: Optional[str], year: int) -> Optional[IndustryWage]:
    """
    Get industry wage benchmark for a company based on ISAT code.

    Args:
        isat_code: Company's ISAT classification code (e.g., "62.01" or "6201")
        year: Year to get benchmark for

    Returns:
        IndustryWage if found, None otherwise
    """
    if not isat_code:
        return None

    # Extract first 2 digits of ISAT code
    isat_clean = isat_code.replace(".", "").replace(" ", "")
    if len(isat_clean) >= 2:
        isat_prefix = isat_clean[:2]
    else:
        return None

    # Map to Hagstofa industry code
    hagstofa_code = ISAT_TO_HAGSTOFA.get(isat_prefix)
    if not hagstofa_code:
        return None

    # Check cache first
    cached = _cache.get(hagstofa_code, year)
    if cached:
        return cached

    # Fetch fresh data
    fetch_industry_wages([year, year - 1, year - 2])
    return _cache.get(hagstofa_code, year)


def get_national_average(year: int) -> Optional[IndustryWage]:
    """Get national average wage for a given year."""
    cached = _cache.get("0", year)
    if cached:
        return cached

    fetch_industry_wages([year, year - 1, year - 2])
    return _cache.get("0", year)


def get_all_benchmarks(year: int) -> list[IndustryWage]:
    """Get all industry benchmarks for a given year, sorted by wage."""
    if not _cache.is_valid():
        fetch_industry_wages([year, year - 1, year - 2])

    return _cache.get_all_industries(year)


def isat_to_industry_name(isat_code: Optional[str], english: bool = False) -> Optional[str]:
    """Convert ISAT code to human-readable industry name."""
    if not isat_code:
        return None

    isat_clean = isat_code.replace(".", "").replace(" ", "")
    if len(isat_clean) >= 2:
        isat_prefix = isat_clean[:2]
    else:
        return None

    hagstofa_code = ISAT_TO_HAGSTOFA.get(isat_prefix)
    if not hagstofa_code:
        return None

    names = INDUSTRY_NAMES_EN if english else INDUSTRY_NAMES
    return names.get(hagstofa_code)
