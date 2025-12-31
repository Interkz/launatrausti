#!/usr/bin/env python3
"""
Fetch company information from Skatturinn API and store in database.

Usage:
    # Fetch sample companies
    python scripts/fetch_companies.py --sample

    # Fetch specific companies by kennitala
    python scripts/fetch_companies.py 6204830369 6407070540

    # Fetch from a file (one kennitala per line)
    python scripts/fetch_companies.py --file kennitolur.txt
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.skatturinn_api import fetch_company, fetch_companies_batch, SAMPLE_KENNITOLUR, CompanyInfo
from src.database import get_or_create_company, get_connection


def save_company_to_db(company: CompanyInfo) -> int:
    """Save company info to database, returns company_id."""
    conn = get_connection()
    cursor = conn.cursor()

    # Check if exists
    cursor.execute("SELECT id FROM companies WHERE kennitala = ?", (company.kennitala,))
    row = cursor.fetchone()

    if row:
        # Update existing
        cursor.execute("""
            UPDATE companies
            SET name = ?, isat_code = ?
            WHERE kennitala = ?
        """, (company.name, company.isat_code, company.kennitala))
        company_id = row["id"]
    else:
        # Insert new
        cursor.execute("""
            INSERT INTO companies (kennitala, name, isat_code)
            VALUES (?, ?, ?)
        """, (company.kennitala, company.name, company.isat_code))
        company_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return company_id


def main():
    parser = argparse.ArgumentParser(
        description="Fetch company info from Skatturinn API"
    )
    parser.add_argument(
        "kennitolur",
        nargs="*",
        help="Kennitölur to fetch"
    )
    parser.add_argument(
        "--sample", "-s",
        action="store_true",
        help="Fetch sample well-known companies"
    )
    parser.add_argument(
        "--file", "-f",
        type=Path,
        help="File with kennitölur (one per line)"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Fetch but don't save to database"
    )

    args = parser.parse_args()

    # Collect kennitölur to fetch
    kennitolur = []

    if args.sample:
        kennitolur.extend(SAMPLE_KENNITOLUR)

    if args.file:
        if not args.file.exists():
            print(f"Error: File not found: {args.file}")
            sys.exit(1)
        with open(args.file) as f:
            for line in f:
                kt = line.strip()
                if kt and not kt.startswith("#"):
                    kennitolur.append(kt)

    kennitolur.extend(args.kennitolur)

    if not kennitolur:
        print("No kennitölur specified. Use --sample, --file, or provide kennitölur.")
        parser.print_help()
        sys.exit(1)

    # Remove duplicates while preserving order
    seen = set()
    unique_kennitolur = []
    for kt in kennitolur:
        kt_clean = kt.replace("-", "").strip()
        if kt_clean not in seen:
            seen.add(kt_clean)
            unique_kennitolur.append(kt_clean)

    print(f"Fetching {len(unique_kennitolur)} companies from Skatturinn API...")
    print("=" * 50)

    success_count = 0
    not_found_count = 0
    error_count = 0

    for i, kt in enumerate(unique_kennitolur, 1):
        print(f"[{i}/{len(unique_kennitolur)}] {kt}...", end=" ")

        try:
            company = fetch_company(kt)

            if company:
                print(f"{company.name}")
                print(f"    ISAT: {company.isat_code or 'N/A'} | Status: {company.status}")

                if not args.dry_run:
                    company_id = save_company_to_db(company)
                    print(f"    Saved (id={company_id})")

                success_count += 1
            else:
                print("Not found")
                not_found_count += 1

        except Exception as e:
            print(f"Error: {e}")
            error_count += 1

    print("=" * 50)
    print(f"Done! Fetched: {success_count}, Not found: {not_found_count}, Errors: {error_count}")

    if args.dry_run:
        print("(Dry run - nothing saved to database)")


if __name__ == "__main__":
    main()
