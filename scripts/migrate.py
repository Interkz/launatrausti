#!/usr/bin/env python3
"""Database migration runner.

Applies numbered SQL migrations from the migrations/ directory.
Tracks applied versions in a schema_version table.

Usage:
    python scripts/migrate.py              # Apply pending migrations
    python scripts/migrate.py --status     # Show current version and pending migrations
    python scripts/migrate.py --baseline 1 # Mark version 1 as applied without running it
"""

import argparse
import re
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"

# Reuse the same DB path logic as database.py
import os
import shutil

BUNDLED_DB = PROJECT_ROOT / "launatrausti.db"
if os.environ.get("VERCEL"):
    DB_PATH = Path("/tmp/launatrausti.db")
    if not DB_PATH.exists() and BUNDLED_DB.exists():
        shutil.copy(BUNDLED_DB, DB_PATH)
else:
    DB_PATH = BUNDLED_DB

MIGRATION_PATTERN = re.compile(r"^(\d{3})_.+\.sql$")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_schema_version_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def get_current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return row[0] or 0


def discover_migrations() -> list[tuple[int, str, Path]]:
    """Return sorted list of (version, name, path) for all migration files."""
    migrations = []
    if not MIGRATIONS_DIR.exists():
        return migrations

    for f in sorted(MIGRATIONS_DIR.iterdir()):
        match = MIGRATION_PATTERN.match(f.name)
        if match:
            version = int(match.group(1))
            migrations.append((version, f.name, f))

    return migrations


def get_pending_migrations(conn: sqlite3.Connection) -> list[tuple[int, str, Path]]:
    current = get_current_version(conn)
    return [(v, name, path) for v, name, path in discover_migrations() if v > current]


def apply_migration(conn: sqlite3.Connection, version: int, name: str, path: Path):
    sql = path.read_text(encoding="utf-8")
    try:
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_version (version, name) VALUES (?, ?)",
            (version, name),
        )
        conn.commit()
        print(f"  Applied {name}")
    except Exception as e:
        conn.rollback()
        print(f"  FAILED {name}: {e}", file=sys.stderr)
        raise


def cmd_migrate():
    conn = get_connection()
    ensure_schema_version_table(conn)

    pending = get_pending_migrations(conn)
    if not pending:
        current = get_current_version(conn)
        print(f"Database is up to date (version {current}).")
        conn.close()
        return

    print(f"Applying {len(pending)} migration(s)...")
    for version, name, path in pending:
        apply_migration(conn, version, name, path)

    print(f"Done. Current version: {get_current_version(conn)}")
    conn.close()


def cmd_status():
    conn = get_connection()
    ensure_schema_version_table(conn)

    current = get_current_version(conn)
    pending = get_pending_migrations(conn)
    all_migrations = discover_migrations()

    print(f"Database: {DB_PATH}")
    print(f"Current version: {current}")
    print(f"Total migrations: {len(all_migrations)}")
    print(f"Pending: {len(pending)}")

    if pending:
        print("\nPending migrations:")
        for version, name, _ in pending:
            print(f"  {name}")

    conn.close()


def cmd_baseline(version: int):
    conn = get_connection()
    ensure_schema_version_table(conn)

    current = get_current_version(conn)
    if current >= version:
        print(f"Database is already at version {current}, nothing to baseline.")
        conn.close()
        return

    all_migrations = discover_migrations()
    to_mark = [(v, name) for v, name, _ in all_migrations if v > current and v <= version]

    if not to_mark:
        print(f"No migrations found up to version {version}.")
        conn.close()
        return

    for v, name in to_mark:
        conn.execute(
            "INSERT INTO schema_version (version, name) VALUES (?, ?)",
            (v, name),
        )
    conn.commit()

    print(f"Baselined to version {version} ({len(to_mark)} migration(s) marked as applied).")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Database migration runner")
    parser.add_argument("--status", action="store_true", help="Show migration status")
    parser.add_argument(
        "--baseline",
        type=int,
        metavar="VERSION",
        help="Mark migrations up to VERSION as applied without running them",
    )
    args = parser.parse_args()

    if args.status:
        cmd_status()
    elif args.baseline is not None:
        cmd_baseline(args.baseline)
    else:
        cmd_migrate()


if __name__ == "__main__":
    main()
