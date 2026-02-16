#!/usr/bin/env python3
"""Cleanup script for sample/fake data in launatrausti database."""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.database import get_connection


def flag_sample_data(dry_run=False):
    """Flag annual_reports where source_pdf='sample_data' with is_sample=1."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT COUNT(*) FROM annual_reports WHERE source_pdf = 'sample_data' AND (is_sample = 0 OR is_sample IS NULL)"
    )
    count = cursor.fetchone()[0]

    if dry_run:
        print(f"Would flag {count} reports as sample data.")
    else:
        cursor.execute(
            "UPDATE annual_reports SET is_sample = 1 WHERE source_pdf = 'sample_data'"
        )
        conn.commit()
        print(f"Flagged {count} reports as sample data.")

    conn.close()
    return count


def delete_sample_data(dry_run=False):
    """Delete flagged sample data and orphan companies."""
    conn = get_connection()
    cursor = conn.cursor()

    # Count what would be deleted
    cursor.execute("SELECT COUNT(*) FROM annual_reports WHERE is_sample = 1")
    reports_count = cursor.fetchone()[0]

    # Find companies that would become orphans
    cursor.execute("""
        SELECT COUNT(DISTINCT c.id) FROM companies c
        WHERE NOT EXISTS (
            SELECT 1 FROM annual_reports ar
            WHERE ar.company_id = c.id AND (ar.is_sample = 0 OR ar.is_sample IS NULL)
        )
        AND EXISTS (
            SELECT 1 FROM annual_reports ar2 WHERE ar2.company_id = c.id
        )
    """)
    orphan_count = cursor.fetchone()[0]

    if dry_run:
        print(f"Would delete {reports_count} sample reports.")
        print(f"Would delete {orphan_count} orphaned companies.")
    else:
        cursor.execute("DELETE FROM annual_reports WHERE is_sample = 1")
        cursor.execute("""
            DELETE FROM companies WHERE id NOT IN (
                SELECT DISTINCT company_id FROM annual_reports
            )
            AND id IN (
                SELECT DISTINCT company_id FROM data_flags WHERE flag_type = 'sample_data'
            )
        """)
        # Simpler: delete companies with no reports at all
        cursor.execute("""
            DELETE FROM companies WHERE id NOT IN (
                SELECT DISTINCT company_id FROM annual_reports
            )
        """)
        conn.commit()
        actual_orphans = cursor.rowcount
        print(f"Deleted {reports_count} sample reports.")
        print(f"Deleted {orphan_count} orphaned companies.")

    conn.close()
    return reports_count, orphan_count


def main():
    parser = argparse.ArgumentParser(description="Cleanup sample/fake data from launatrausti database")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="Show what would happen without making changes")
    group.add_argument("--delete", action="store_true", help="Delete flagged sample data and orphan companies")
    group.add_argument("--flag-only", action="store_true", help="Only flag sample data, don't delete")

    args = parser.parse_args()

    if args.dry_run:
        print("=== DRY RUN (no changes will be made) ===")
        flag_sample_data(dry_run=True)
        delete_sample_data(dry_run=True)
    elif args.delete:
        flag_sample_data(dry_run=False)
        delete_sample_data(dry_run=False)
    else:
        # Default: flag only
        flag_sample_data(dry_run=False)


if __name__ == "__main__":
    main()
