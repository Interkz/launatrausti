"""
Skatturinn API Client

Fetches company information from the Icelandic Tax Authority's Company Registry API.

API Limits (Developer tier):
- 60 calls/minute
- 5000 calls/month
"""

import os
import time
from dataclasses import dataclass
from typing import Optional
import requests


API_BASE_URL = "https://api.skattur.cloud/legalentities/v2"

# Rate limiting
CALLS_PER_MINUTE = 60
_last_call_time = 0
_calls_this_minute = 0


@dataclass
class CompanyInfo:
    kennitala: str
    name: str
    status: Optional[str]
    legal_form: Optional[str]  # ehf, hf, etc.
    isat_code: Optional[str]  # Industry classification
    isat_name: Optional[str]
    address: Optional[str]
    postcode: Optional[str]
    city: Optional[str]
    registered: Optional[str]
    share_capital: Optional[float]


def get_api_key() -> str:
    """Get API key from environment or config."""
    key = os.environ.get("SKATTURINN_API_KEY")
    if not key:
        # Try reading from api.txt in project root
        api_file = os.path.join(os.path.dirname(__file__), "..", "api.txt")
        if os.path.exists(api_file):
            with open(api_file, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("primary key:"):
                        key = line.split(":", 1)[1].strip()
                        break
    if not key:
        raise ValueError(
            "Skatturinn API key not found. Set SKATTURINN_API_KEY environment variable "
            "or add api.txt with 'primary key: <key>'"
        )
    return key


def _rate_limit():
    """Simple rate limiting to stay under 60 calls/minute."""
    global _last_call_time, _calls_this_minute

    current_time = time.time()

    # Reset counter if a minute has passed
    if current_time - _last_call_time > 60:
        _calls_this_minute = 0
        _last_call_time = current_time

    # If we've hit the limit, wait
    if _calls_this_minute >= CALLS_PER_MINUTE:
        sleep_time = 60 - (current_time - _last_call_time)
        if sleep_time > 0:
            print(f"Rate limit reached, waiting {sleep_time:.1f}s...")
            time.sleep(sleep_time)
            _calls_this_minute = 0
            _last_call_time = time.time()

    _calls_this_minute += 1


def fetch_company(kennitala: str, api_key: Optional[str] = None) -> Optional[CompanyInfo]:
    """
    Fetch company information by kennitala.

    Args:
        kennitala: 10-digit company national ID
        api_key: Optional API key (will use env/config if not provided)

    Returns:
        CompanyInfo object or None if not found
    """
    api_key = api_key or get_api_key()

    # Clean kennitala (remove dashes)
    kennitala = kennitala.replace("-", "").strip()

    if len(kennitala) != 10:
        raise ValueError(f"Invalid kennitala: {kennitala} (must be 10 digits)")

    _rate_limit()

    headers = {
        "Ocp-Apim-Subscription-Key": api_key,
        "Accept": "application/json"
    }

    url = f"{API_BASE_URL}/{kennitala}"

    try:
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code == 404:
            return None

        response.raise_for_status()
        data = response.json()

        # Extract ISAT code (primary activity)
        isat_code = None
        isat_name = None
        if data.get("activityCode"):
            # type can be a string "Primary" or an object {"name": "Aðalstarfsemi"}
            def is_primary(a):
                t = a.get("type")
                if isinstance(t, str):
                    return t.lower() == "primary"
                elif isinstance(t, dict):
                    return t.get("name") in ("Aðalstarfsemi", "Primary")
                return False

            primary = next(
                (a for a in data["activityCode"] if is_primary(a)),
                data["activityCode"][0] if data["activityCode"] else None
            )
            if primary:
                isat_code = primary.get("id")
                isat_name = primary.get("name")

        # Extract address
        address = None
        postcode = None
        city = None
        if data.get("address"):
            def is_legal_address(a):
                t = a.get("type")
                if isinstance(t, str):
                    return t.lower() in ("legal", "lögheimili")
                elif isinstance(t, dict):
                    return t.get("name") in ("Lögheimili", "Legal")
                return False

            legal_addr = next(
                (a for a in data["address"] if is_legal_address(a)),
                data["address"][0] if data["address"] else None
            )
            if legal_addr:
                address = legal_addr.get("addressName")
                postcode = legal_addr.get("postcode")
                city = legal_addr.get("city")

        # Extract share capital
        share_capital = None
        if data.get("articlesOfAssociation"):
            share_capital = data["articlesOfAssociation"].get("shareCapital")

        return CompanyInfo(
            kennitala=data.get("nationalId", kennitala),
            name=data.get("name", "Unknown"),
            status=data.get("status"),
            legal_form=data.get("legalForm", {}).get("name") if data.get("legalForm") else None,
            isat_code=isat_code,
            isat_name=isat_name,
            address=address,
            postcode=postcode,
            city=city,
            registered=data.get("registered"),
            share_capital=share_capital
        )

    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        raise


def fetch_companies_batch(kennitolur: list[str], api_key: Optional[str] = None) -> list[CompanyInfo]:
    """
    Fetch multiple companies by kennitala.

    Args:
        kennitolur: List of kennitölur to fetch
        api_key: Optional API key

    Returns:
        List of CompanyInfo objects (skips not found)
    """
    api_key = api_key or get_api_key()
    results = []

    for i, kt in enumerate(kennitolur):
        print(f"Fetching {i+1}/{len(kennitolur)}: {kt}...")
        try:
            company = fetch_company(kt, api_key)
            if company:
                results.append(company)
                print(f"  → {company.name}")
            else:
                print(f"  → Not found")
        except Exception as e:
            print(f"  → Error: {e}")

    return results


# Well-known Icelandic company kennitölur for testing
# Verified kennitölur from Keldan/Skatturinn
SAMPLE_KENNITOLUR = [
    "6204830369",  # JBT Marel ehf (formerly Marel hf)
    "6407070540",  # Marel Iceland ehf
    "4602070880",  # Síminn hf
    "4710080280",  # Landsbankinn hf
    "5810080150",  # Arion banki hf
    "4910080160",  # Íslandsbanki hf
]


if __name__ == "__main__":
    # Quick test
    print("Testing Skatturinn API...")
    try:
        company = fetch_company("5501692829")  # Marel
        if company:
            print(f"\nSuccess! Found: {company.name}")
            print(f"  Legal form: {company.legal_form}")
            print(f"  ISAT: {company.isat_code} - {company.isat_name}")
            print(f"  Address: {company.address}, {company.postcode} {company.city}")
        else:
            print("Company not found")
    except Exception as e:
        print(f"Error: {e}")
