"""Tests for startup checks."""

import pytest
from unittest.mock import patch
from pathlib import Path

import src.database as db
from src.startup import (
    check_database_exists,
    check_database_tables,
    check_database_integrity,
    check_data_stats,
    check_templates,
    run_startup_checks,
    StartupError,
)


def test_check_database_exists(test_db):
    """Should pass when database file exists."""
    with patch.object(db, "DB_PATH", test_db):
        result = check_database_exists()
        assert result == test_db


def test_check_database_exists_missing(tmp_path):
    """Should raise StartupError when database file is missing."""
    missing = tmp_path / "nonexistent.db"
    with patch.object(db, "DB_PATH", missing):
        with pytest.raises(StartupError, match="not found"):
            check_database_exists()


def test_check_database_tables(test_db):
    """Should pass when all required tables exist."""
    with patch.object(db, "DB_PATH", test_db):
        tables = check_database_tables()
        assert "companies" in tables
        assert "annual_reports" in tables


def test_check_database_integrity(test_db):
    """Should pass integrity check on a valid database."""
    with patch.object(db, "DB_PATH", test_db):
        assert check_database_integrity() is True


def test_check_data_stats(test_db, sample_company):
    """Should return row counts for all tables."""
    with patch.object(db, "DB_PATH", test_db):
        stats = check_data_stats()
        assert stats["companies"] >= 1
        assert isinstance(stats["annual_reports"], int)


def test_check_templates():
    """Should find templates directory with HTML files."""
    result = check_templates()
    assert result.is_dir()


def test_run_startup_checks(test_db):
    """Should run all checks and return summary dict."""
    with patch.object(db, "DB_PATH", test_db):
        results = run_startup_checks()
        assert results["integrity"] == "ok"
        assert "data_stats" in results
        assert "tables" in results
