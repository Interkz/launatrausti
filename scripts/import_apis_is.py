#!/usr/bin/env python3
"""
Import companies from apis.is (free Icelandic company data).

This script:
1. Searches apis.is for well-known Icelandic companies
2. Adds them to the database with real kennitala and names
3. Optionally generates sample financial data for testing

NOTE: apis.is does NOT provide financial data (wage costs, employees).
      Companies imported this way won't appear in rankings until
      annual report data is added via PDF extraction or other sources.

Usage:
    # Import companies only (no financial data)
    python scripts/import_apis_is.py

    # Import with sample financial data for testing
    python scripts/import_apis_is.py --with-sample-data

    # Search for a specific company
    python scripts/import_apis_is.py --search "Marel"
"""

import sys
import argparse
import random
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.apis_is import search_companies_by_name, get_company_by_kennitala, SEED_COMPANIES
from src.database import get_or_create_company, save_annual_report, init_db


# Sample financial data ranges by industry (for testing only)
# Based on Hagstofa 2023 averages
SAMPLE_DATA_RANGES = {
    "tech": {"salary_range": (900_000, 1_400_000), "employees_range": (20, 500)},
    "finance": {"salary_range": (1_000_000, 1_500_000), "employees_range": (100, 2000)},
    "retail": {"salary_range": (500_000, 800_000), "employees_range": (50, 5000)},
    "energy": {"salary_range": (900_000, 1_300_000), "employees_range": (100, 1000)},
    "telecom": {"salary_range": (800_000, 1_200_000), "employees_range": (200, 1500)},
    "default": {"salary_range": (700_000, 1_100_000), "employees_range": (50, 1000)},
}

# Map company names to industries (rough)
COMPANY_INDUSTRIES = {
    "Marel": "tech", "CCP": "tech", "Advania": "tech", "Sensa": "tech",
    "Controlant": "tech", "Tempo": "tech", "Gangverk": "tech",
    "Landsbankinn": "finance", "Íslandsbanki": "finance", "Arion": "finance",
    "Kvika": "finance", "Sjóvá": "finance", "TM": "finance",
    "Síminn": "telecom", "Nova": "telecom", "Vodafone": "telecom", "Sýn": "telecom",
    "Landsvirkjun": "energy", "Orkuveita": "energy", "HS Orka": "energy",
    "Hagar": "retail", "Bónus": "retail", "Hagkaup": "retail", "Krónan": "retail",
}


def guess_industry(company_name: str) -> str:
    """Guess industry from company name."""
    name_lower = company_name.lower()
    for keyword, industry in COMPANY_INDUSTRIES.items():
        if keyword.lower() in name_lower:
            return industry
    return "default"


def generate_sample_data(company_name: str, year: int = 2023) -> dict:
    """Generate sample financial data for testing."""
    industry = guess_industry(company_name)
    ranges = SAMPLE_DATA_RANGES[industry]

    monthly_salary = random.randint(*ranges["salary_range"])
    employees = random.randint(*ranges["employees_range"])
    annual_salary = monthly_salary * 12
    launakostnadur = annual_salary * employees

    return {
        "year": year,
        "launakostnadur": launakostnadur,
        "starfsmenn": employees,
        "tekjur": launakostnadur * random.uniform(2.5, 4.0),  # Rough revenue estimate
    }


def import_companies(with_sample_data: bool = False, verbose: bool = True):
    """Import well-known companies from apis.is."""
    init_db()

    imported = 0
    skipped = 0
    errors = 0

    for company_name in SEED_COMPANIES:
        if verbose:
            print(f"Searching for: {company_name}...", end=" ")

        try:
            results = search_companies_by_name(company_name)
        except Exception as e:
            if verbose:
                print(f"ERROR: {e}")
            errors += 1
            continue

        if not results:
            if verbose:
                print("not found")
            skipped += 1
            continue

        # Take the first active result, or first result if none active
        company = next((r for r in results if r.active), results[0])

        if verbose:
            print(f"found: {company.name} ({company.kennitala})")

        # Add to database
        company_id = get_or_create_company(
            kennitala=company.kennitala,
            name=company.name,
            isat_code=None  # apis.is doesn't provide ISAT codes
        )

        # Optionally add sample financial data
        if with_sample_data:
            sample = generate_sample_data(company.name)
            save_annual_report(
                company_id=company_id,
                year=sample["year"],
                launakostnadur=sample["launakostnadur"],
                starfsmenn=sample["starfsmenn"],
                tekjur=int(sample["tekjur"]),
                source_pdf="apis.is (sample data)"
            )
            if verbose:
                monthly = sample["launakostnadur"] // sample["starfsmenn"] // 12
                print(f"  → Added sample data: {sample['starfsmenn']} employees, ~{monthly:,} kr/month")

        imported += 1

    print(f"\nDone! Imported: {imported}, Skipped: {skipped}, Errors: {errors}")

    if not with_sample_data:
        print("\nNOTE: Companies were added but have no financial data.")
        print("They won't appear in rankings until annual report data is added.")
        print("Run with --with-sample-data to generate test data.")


def search_single(name: str):
    """Search for a single company and display results."""
    print(f"Searching for: {name}\n")

    results = search_companies_by_name(name)

    if not results:
        print("No results found.")
        return

    for i, company in enumerate(results, 1):
        status = "Active" if company.active else "Inactive"
        print(f"{i}. {company.name}")
        print(f"   Kennitala: {company.kennitala}")
        print(f"   Address: {company.address}")
        print(f"   Status: {status}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Import Icelandic companies from apis.is"
    )
    parser.add_argument(
        "--with-sample-data",
        action="store_true",
        help="Generate sample financial data for testing"
    )
    parser.add_argument(
        "--search",
        type=str,
        help="Search for a specific company"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress verbose output"
    )

    args = parser.parse_args()

    if args.search:
        search_single(args.search)
    else:
        import_companies(
            with_sample_data=args.with_sample_data,
            verbose=not args.quiet
        )


if __name__ == "__main__":
    main()
