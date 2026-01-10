#!/usr/bin/env python3
"""
Import companies from Skatturinn API (Icelandic Tax Authority).

This script:
1. Fetches company data from Skatturinn API using known kennitölur
2. Adds them to the database with real kennitala, name, and ISAT code
3. Optionally generates sample financial data for testing

NOTE: Skatturinn API provides company metadata but NOT financial data.
      Companies imported this way won't appear in rankings until
      annual report data is added via PDF extraction or Creditinfo.

Requires: SKATTURINN_API_KEY environment variable or api.txt file

Usage:
    # Import known companies
    python scripts/import_skatturinn.py

    # Import with sample financial data for testing
    python scripts/import_skatturinn.py --with-sample-data

    # Fetch a specific company by kennitala
    python scripts/import_skatturinn.py --kennitala 5501692829
"""

import sys
import argparse
import random
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.skatturinn_api import fetch_company, SAMPLE_KENNITOLUR
from src.database import get_or_create_company, save_annual_report, init_db


# Well-known Icelandic companies with verified kennitölur
# Sources: Skatturinn company registry API
KNOWN_COMPANIES = [
    # Banks & Finance (verified)
    ("4710080280", "Landsbankinn hf"),
    ("5810080150", "Arion banki hf"),
    ("4910080160", "Íslandsbanki hf"),

    # Telecom (verified)
    ("4602070880", "Síminn hf"),

    # Note: Many kennitölur need verification via Skatturinn lookup
    # The API doesn't support name search, only kennitala lookup
    # Users should add more verified kennitölur as they find them
]

# Sample financial data ranges by ISAT code prefix
SAMPLE_DATA_RANGES = {
    "62": {"salary_range": (950_000, 1_350_000), "employees_range": (50, 800)},   # IT
    "64": {"salary_range": (1_050_000, 1_450_000), "employees_range": (200, 2000)}, # Finance
    "61": {"salary_range": (850_000, 1_150_000), "employees_range": (100, 800)},   # Telecom
    "51": {"salary_range": (950_000, 1_250_000), "employees_range": (500, 3000)},  # Airlines
    "35": {"salary_range": (1_000_000, 1_350_000), "employees_range": (150, 1000)}, # Energy
    "47": {"salary_range": (550_000, 750_000), "employees_range": (500, 5000)},    # Retail
    "26": {"salary_range": (850_000, 1_100_000), "employees_range": (100, 1500)},  # Manufacturing
    "65": {"salary_range": (950_000, 1_250_000), "employees_range": (100, 500)},   # Insurance
    "default": {"salary_range": (750_000, 1_050_000), "employees_range": (50, 500)},
}


def get_sample_ranges(isat_code: str) -> dict:
    """Get sample data ranges based on ISAT code."""
    if isat_code:
        prefix = isat_code.replace(".", "")[:2]
        if prefix in SAMPLE_DATA_RANGES:
            return SAMPLE_DATA_RANGES[prefix]
    return SAMPLE_DATA_RANGES["default"]


def generate_sample_data(isat_code: str, year: int = 2023) -> dict:
    """Generate sample financial data for testing."""
    ranges = get_sample_ranges(isat_code)

    monthly_salary = random.randint(*ranges["salary_range"])
    employees = random.randint(*ranges["employees_range"])
    annual_salary = monthly_salary * 12
    launakostnadur = annual_salary * employees

    return {
        "year": year,
        "launakostnadur": launakostnadur,
        "starfsmenn": employees,
        "tekjur": int(launakostnadur * random.uniform(2.5, 4.5)),
    }


def import_companies(with_sample_data: bool = False, verbose: bool = True):
    """Import known companies from Skatturinn API."""
    init_db()

    imported = 0
    skipped = 0
    errors = 0

    for kennitala, expected_name in KNOWN_COMPANIES:
        if verbose:
            print(f"Fetching: {expected_name} ({kennitala})...", end=" ")

        try:
            company = fetch_company(kennitala)
        except Exception as e:
            if verbose:
                print(f"ERROR: {e}")
            errors += 1
            continue

        if not company:
            if verbose:
                print("not found")
            skipped += 1
            continue

        if verbose:
            isat_info = f", ISAT: {company.isat_code}" if company.isat_code else ""
            print(f"OK - {company.name}{isat_info}")

        # Add to database
        company_id = get_or_create_company(
            kennitala=company.kennitala,
            name=company.name,
            isat_code=company.isat_code
        )

        # Optionally add sample financial data
        if with_sample_data:
            sample = generate_sample_data(company.isat_code or "")
            save_annual_report(
                company_id=company_id,
                year=sample["year"],
                launakostnadur=sample["launakostnadur"],
                starfsmenn=sample["starfsmenn"],
                tekjur=sample["tekjur"],
                source_pdf="skatturinn.is (sample data)"
            )
            if verbose:
                monthly = sample["launakostnadur"] // sample["starfsmenn"] // 12
                print(f"  -> Sample: {sample['starfsmenn']} employees, ~{monthly:,} kr/month")

        imported += 1

    print(f"\nDone! Imported: {imported}, Skipped: {skipped}, Errors: {errors}")

    if not with_sample_data:
        print("\nNOTE: Companies were added but have no financial data.")
        print("They won't appear in rankings until annual report data is added.")
        print("Run with --with-sample-data to generate test data.")


def fetch_single(kennitala: str, with_sample_data: bool = False):
    """Fetch a single company and optionally add to database."""
    print(f"Fetching company: {kennitala}\n")

    try:
        company = fetch_company(kennitala)
    except Exception as e:
        print(f"Error: {e}")
        return

    if not company:
        print("Company not found.")
        return

    print(f"Name: {company.name}")
    print(f"Kennitala: {company.kennitala}")
    print(f"Status: {company.status}")
    print(f"Legal form: {company.legal_form}")
    print(f"ISAT: {company.isat_code} - {company.isat_name}")
    print(f"Address: {company.address}, {company.postcode} {company.city}")
    print(f"Registered: {company.registered}")

    if with_sample_data:
        init_db()
        company_id = get_or_create_company(
            kennitala=company.kennitala,
            name=company.name,
            isat_code=company.isat_code
        )
        sample = generate_sample_data(company.isat_code or "")
        save_annual_report(
            company_id=company_id,
            year=sample["year"],
            launakostnadur=sample["launakostnadur"],
            starfsmenn=sample["starfsmenn"],
            tekjur=sample["tekjur"],
            source_pdf="skatturinn.is (sample data)"
        )
        monthly = sample["launakostnadur"] // sample["starfsmenn"] // 12
        print(f"\nAdded to database with sample data:")
        print(f"  {sample['starfsmenn']} employees, ~{monthly:,} kr/month")


def main():
    parser = argparse.ArgumentParser(
        description="Import Icelandic companies from Skatturinn API"
    )
    parser.add_argument(
        "--with-sample-data",
        action="store_true",
        help="Generate sample financial data for testing"
    )
    parser.add_argument(
        "--kennitala",
        type=str,
        help="Fetch a specific company by kennitala"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress verbose output"
    )

    args = parser.parse_args()

    if args.kennitala:
        fetch_single(args.kennitala, with_sample_data=args.with_sample_data)
    else:
        import_companies(
            with_sample_data=args.with_sample_data,
            verbose=not args.quiet
        )


if __name__ == "__main__":
    main()
