#!/usr/bin/env python3
"""
Match job listing employers to companies in the database.

Usage:
    python scripts/match_companies.py
    python scripts/match_companies.py --verbose
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import init_db
from src.company_matcher import match_all_unmatched

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Match job employers to companies")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    init_db()
    stats = match_all_unmatched()

    print(f"\nMatching results:")
    print(f"  Matched: {stats['matched']}")
    print(f"  Unmatched: {stats['unmatched']}")
    if stats["new_employers"]:
        print(f"  Top unmatched employers:")
        for name in stats["new_employers"][:20]:
            print(f"    - {name}")


if __name__ == "__main__":
    main()
