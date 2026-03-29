#!/usr/bin/env python3
"""
Pre-compute salary estimates for all active job listings.

Usage:
    python scripts/estimate_salaries.py
    python scripts/estimate_salaries.py --verbose
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import init_db
from src.salary_engine import estimate_all_jobs

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Estimate salaries for job listings")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    init_db()
    updated = estimate_all_jobs()
    print(f"\nUpdated salary estimates for {updated} jobs")


if __name__ == "__main__":
    main()
