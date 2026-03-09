"""
Startup checks for the Launatrausti application.

Validates database connectivity, required tables, and configuration
before the app starts serving requests. Logs diagnostic information.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional

from . import database

logger = logging.getLogger("launatrausti.startup")

# Tables the app requires to function
REQUIRED_TABLES = [
    "companies",
    "annual_reports",
    "vr_salary_surveys",
    "scrape_log",
    "data_flags",
]


class StartupError(Exception):
    """Raised when a critical startup check fails."""
    pass


def check_database_exists() -> Path:
    """Verify the database file exists and is readable."""
    db_path = database.DB_PATH
    if not db_path.exists():
        raise StartupError(
            f"Database file not found at {db_path}. "
            "Run database.init_db() to create it."
        )
    if not db_path.is_file():
        raise StartupError(f"Database path {db_path} is not a file.")
    logger.info("Database found at %s (%.1f KB)", db_path, db_path.stat().st_size / 1024)
    return db_path


def check_database_tables() -> list[str]:
    """Verify all required tables exist in the database."""
    conn = database.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        existing = {row["name"] for row in cursor.fetchall()}
    finally:
        conn.close()

    missing = [t for t in REQUIRED_TABLES if t not in existing]
    if missing:
        raise StartupError(
            f"Missing required database tables: {', '.join(missing)}. "
            "Run database.init_db() to create them."
        )

    logger.info("All %d required tables present", len(REQUIRED_TABLES))
    return list(existing)


def check_database_integrity() -> bool:
    """Run SQLite integrity check on the database."""
    conn = database.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        ok = result[0] == "ok"
        if not ok:
            raise StartupError(f"Database integrity check failed: {result[0]}")
        logger.info("Database integrity check passed")
        return ok
    finally:
        conn.close()


def check_data_stats() -> dict:
    """Log basic data statistics for diagnostics."""
    conn = database.get_connection()
    try:
        cursor = conn.cursor()
        stats = {}

        for table in REQUIRED_TABLES:
            cursor.execute(f"SELECT COUNT(*) as cnt FROM {table}")
            stats[table] = cursor.fetchone()["cnt"]

        logger.info(
            "Data stats: %d companies, %d reports, %d VR surveys",
            stats.get("companies", 0),
            stats.get("annual_reports", 0),
            stats.get("vr_salary_surveys", 0),
        )
        return stats
    finally:
        conn.close()


def check_templates() -> Path:
    """Verify the templates directory exists and contains expected files."""
    templates_dir = Path(__file__).parent / "templates"
    if not templates_dir.exists():
        raise StartupError(f"Templates directory not found at {templates_dir}")
    if not templates_dir.is_dir():
        raise StartupError(f"Templates path {templates_dir} is not a directory")

    template_files = list(templates_dir.glob("*.html"))
    if not template_files:
        raise StartupError(f"No HTML templates found in {templates_dir}")

    logger.info(
        "Templates directory OK: %d HTML files in %s",
        len(template_files),
        templates_dir,
    )
    return templates_dir


def run_startup_checks() -> dict:
    """
    Run all startup checks. Returns a summary dict.

    Raises StartupError if any critical check fails.
    """
    logging.basicConfig(level=logging.INFO)
    logger.info("Running startup checks...")

    results = {}

    # 1. Database file exists
    db_path = check_database_exists()
    results["db_path"] = str(db_path)

    # 2. Required tables exist
    tables = check_database_tables()
    results["tables"] = tables

    # 3. Database integrity
    check_database_integrity()
    results["integrity"] = "ok"

    # 4. Data statistics
    stats = check_data_stats()
    results["data_stats"] = stats

    # 5. Templates
    templates_dir = check_templates()
    results["templates_dir"] = str(templates_dir)

    logger.info("All startup checks passed")
    return results
