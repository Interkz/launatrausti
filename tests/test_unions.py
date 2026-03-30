"""Tests for union comparison feature."""

import pytest
from unittest.mock import patch
import src.database as db


@pytest.fixture
def sample_unions(test_db):
    """Insert sample union data for testing."""
    with patch.object(db, "DB_PATH", test_db):
        for union_data in [
            {
                "name": "VR",
                "name_en": "VR — Store & Office Workers' Union",
                "federation": "ASÍ",
                "website": "https://www.vr.is",
                "sector": "Verslun og skrifstofa",
                "members": 37000,
                "fee_pct": 0.70,
                "sick_fund_pct": 1.00,
                "holiday_fund_pct": 0.25,
                "education_fund_pct": 0.30,
                "rehab_fund_pct": 0.10,
                "employer_pension_pct": 11.50,
                "employee_pension_pct": 4.00,
                "sick_pay_pct": 80,
                "sick_pay_days": 270,
                "holiday_homes": 1,
                "education_grants": 1,
                "death_benefit": 800000,
                "min_wage": 438000,
            },
            {
                "name": "BHM",
                "name_en": "BHM — Association of Academics",
                "federation": "BHM",
                "website": "https://www.bhm.is",
                "sector": "Háskólamenntað fólk",
                "members": 18500,
                "fee_pct": 0.80,
                "sick_fund_pct": 0.65,
                "holiday_fund_pct": 0.25,
                "education_fund_pct": 0.40,
                "rehab_fund_pct": 0.10,
                "employer_pension_pct": 11.50,
                "employee_pension_pct": 4.00,
                "sick_pay_pct": 80,
                "sick_pay_days": 180,
                "holiday_homes": 1,
                "education_grants": 1,
                "min_wage": 520000,
            },
        ]:
            db.save_union(union_data)
        return 2


def test_unions_table_exists(test_db):
    """Unions table is created on init."""
    with patch.object(db, "DB_PATH", test_db):
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='unions'")
        assert cursor.fetchone() is not None
        conn.close()


def test_save_and_get_unions(sample_unions, test_db):
    """Saved unions are retrievable."""
    with patch.object(db, "DB_PATH", test_db):
        unions = db.get_all_unions()
        assert len(unions) == 2
        names = [u["name"] for u in unions]
        assert "VR" in names
        assert "BHM" in names


def test_union_upsert(sample_unions, test_db):
    """Saving same union again updates it."""
    with patch.object(db, "DB_PATH", test_db):
        db.save_union({"name": "VR", "members": 40000, "fee_pct": 0.70})
        unions = db.get_all_unions()
        vr = next(u for u in unions if u["name"] == "VR")
        assert vr["members"] == 40000
        assert len(unions) == 2  # No duplicate


def test_union_fee_calculation(sample_unions, test_db):
    """Fee percentages are stored and usable."""
    with patch.object(db, "DB_PATH", test_db):
        unions = db.get_all_unions()
        vr = next(u for u in unions if u["name"] == "VR")
        salary = 750000
        fee = int(salary * vr["fee_pct"] / 100)
        assert fee == 5250  # 0.70% of 750k


def test_union_ordered_by_members(sample_unions, test_db):
    """Unions are returned sorted by member count desc."""
    with patch.object(db, "DB_PATH", test_db):
        unions = db.get_all_unions()
        assert unions[0]["name"] == "VR"  # 37000 > 18500
        assert unions[1]["name"] == "BHM"


def test_get_union_by_id(sample_unions, test_db):
    """Can retrieve individual union by ID."""
    with patch.object(db, "DB_PATH", test_db):
        unions = db.get_all_unions()
        uid = unions[0]["id"]
        union = db.get_union_by_id(uid)
        assert union is not None
        assert union["name"] == "VR"


def test_get_union_by_id_not_found(test_db):
    """Returns None for non-existent union."""
    with patch.object(db, "DB_PATH", test_db):
        union = db.get_union_by_id(99999)
        assert union is None


def test_union_sick_pay_data(sample_unions, test_db):
    """Sick pay data is stored correctly."""
    with patch.object(db, "DB_PATH", test_db):
        unions = db.get_all_unions()
        vr = next(u for u in unions if u["name"] == "VR")
        bhm = next(u for u in unions if u["name"] == "BHM")
        assert vr["sick_pay_days"] == 270
        assert bhm["sick_pay_days"] == 180
        assert vr["sick_pay_pct"] == 80
