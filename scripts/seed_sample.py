#!/usr/bin/env python3
"""
Seed the database with sample data for testing the web interface.
This creates fake data - replace with real extracted data in production.

Usage:
    python scripts/seed_sample.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import get_or_create_company, save_annual_report, get_ranked_companies


# Sample data based on publicly known large Icelandic companies
# These are ESTIMATED/FAKE numbers for testing purposes only
SAMPLE_DATA = [
    {
        "kennitala": "5501692829",
        "name": "Marel hf.",
        "reports": [
            {"year": 2023, "launakostnadur": 45_000_000_000, "starfsmenn": 7500, "tekjur": 180_000_000_000},
            {"year": 2022, "launakostnadur": 42_000_000_000, "starfsmenn": 7200, "tekjur": 165_000_000_000},
        ]
    },
    {
        "kennitala": "6906861229",
        "name": "Síminn hf.",
        "reports": [
            {"year": 2023, "launakostnadur": 8_500_000_000, "starfsmenn": 850, "tekjur": 35_000_000_000},
            {"year": 2022, "launakostnadur": 8_000_000_000, "starfsmenn": 820, "tekjur": 33_000_000_000},
        ]
    },
    {
        "kennitala": "4710990149",
        "name": "Landsbankinn hf.",
        "reports": [
            {"year": 2023, "launakostnadur": 18_000_000_000, "starfsmenn": 1100, "tekjur": 85_000_000_000},
            {"year": 2022, "launakostnadur": 16_500_000_000, "starfsmenn": 1050, "tekjur": 75_000_000_000},
        ]
    },
    {
        "kennitala": "4200694339",
        "name": "Icelandair Group hf.",
        "reports": [
            {"year": 2023, "launakostnadur": 32_000_000_000, "starfsmenn": 4500, "tekjur": 280_000_000_000},
            {"year": 2022, "launakostnadur": 28_000_000_000, "starfsmenn": 4000, "tekjur": 220_000_000_000},
        ]
    },
    {
        "kennitala": "5101692079",
        "name": "Össur hf.",
        "reports": [
            {"year": 2023, "launakostnadur": 25_000_000_000, "starfsmenn": 4000, "tekjur": 110_000_000_000},
            {"year": 2022, "launakostnadur": 23_000_000_000, "starfsmenn": 3800, "tekjur": 100_000_000_000},
        ]
    },
    {
        "kennitala": "5106852399",
        "name": "Arion banki hf.",
        "reports": [
            {"year": 2023, "launakostnadur": 15_000_000_000, "starfsmenn": 900, "tekjur": 70_000_000_000},
            {"year": 2022, "launakostnadur": 14_000_000_000, "starfsmenn": 880, "tekjur": 62_000_000_000},
        ]
    },
    {
        "kennitala": "6604140790",
        "name": "CCP Games hf.",
        "reports": [
            {"year": 2023, "launakostnadur": 5_500_000_000, "starfsmenn": 350, "tekjur": 12_000_000_000},
            {"year": 2022, "launakostnadur": 5_000_000_000, "starfsmenn": 320, "tekjur": 11_000_000_000},
        ]
    },
    {
        "kennitala": "6804080550",
        "name": "Vodafone Iceland",
        "reports": [
            {"year": 2023, "launakostnadur": 4_200_000_000, "starfsmenn": 380, "tekjur": 28_000_000_000},
            {"year": 2022, "launakostnadur": 4_000_000_000, "starfsmenn": 370, "tekjur": 26_000_000_000},
        ]
    },
    {
        "kennitala": "4612872009",
        "name": "Eimskip hf.",
        "reports": [
            {"year": 2023, "launakostnadur": 12_000_000_000, "starfsmenn": 1800, "tekjur": 95_000_000_000},
            {"year": 2022, "launakostnadur": 11_000_000_000, "starfsmenn": 1700, "tekjur": 88_000_000_000},
        ]
    },
    {
        "kennitala": "5901052320",
        "name": "Kvika banki hf.",
        "reports": [
            {"year": 2023, "launakostnadur": 6_000_000_000, "starfsmenn": 350, "tekjur": 25_000_000_000},
            {"year": 2022, "launakostnadur": 5_500_000_000, "starfsmenn": 330, "tekjur": 22_000_000_000},
        ]
    },
]


def main():
    print("Seeding database with sample data...")
    print("=" * 50)
    print("WARNING: This is FAKE data for testing purposes!")
    print("=" * 50)
    print()

    for company_data in SAMPLE_DATA:
        company_id = get_or_create_company(
            kennitala=company_data["kennitala"],
            name=company_data["name"]
        )
        print(f"Company: {company_data['name']} (id={company_id})")

        for report in company_data["reports"]:
            report_id = save_annual_report(
                company_id=company_id,
                year=report["year"],
                launakostnadur=report["launakostnadur"],
                starfsmenn=report["starfsmenn"],
                tekjur=report.get("tekjur"),
                source_pdf="sample_data"
            )
            avg = report["launakostnadur"] // report["starfsmenn"]
            print(f"  {report['year']}: {avg:,} kr/year avg")

        print()

    print("=" * 50)
    print("Sample data seeded successfully!")
    print()

    # Show ranked preview
    print("Top 5 by average salary (2023):")
    print("-" * 50)
    for rank, company in enumerate(get_ranked_companies(year=2023, limit=5), 1):
        monthly = company["avg_salary"] // 12
        print(f"{rank}. {company['name']}: {monthly:,} kr/month")


if __name__ == "__main__":
    main()
