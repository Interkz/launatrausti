"""
Fetch occupation-level salary data from Hagstofa (Statistics Iceland).

Uses PX-Web API to fetch from table VIN02001 — average wages by ISCO occupation.
Stores results in hagstofa_occupations table.

Data: 200+ occupations, p25/median/mean/p75, 2014-2024.
API: Free, no auth, CC BY 4.0 license.

Usage:
    python scripts/fetch_hagstofa_occupations.py
    python scripts/fetch_hagstofa_occupations.py --years 2022,2023,2024
"""

import sys
import os
import argparse
import requests

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src import database

BASE_URL = "https://px.hagstofa.is/pxis/api/v1/is"
TABLE_VIN02001 = "Samfelag/launogtekjur/1_laun/1_laun/VIN02001.px"
TABLE_VIN02004 = "Samfelag/launogtekjur/1_laun/1_laun/VIN02004.px"

# Keep old name for backward compat
TABLE = TABLE_VIN02001

# Stat codes for VIN02001 "Eining" dimension
STAT_CODES = {
    "0": "mean",       # Meðaltal
    "1": "p25",        # Neðri fjórðungsmörk
    "2": "median",     # Miðgildi
    "3": "p75",        # Efri fjórðungsmörk
    "4": "count",      # Fjöldi athugana
}

# Stat codes for VIN02004 "Eining" dimension (decile distributions)
VIN02004_STAT_CODES = {
    "1": "p10",        # 10%
    "11": "p90",       # 90%
}


def fetch_metadata():
    """Fetch table metadata to discover dimension codes."""
    url = f"{BASE_URL}/{TABLE}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


SALARY_TYPES = {
    "0": "grunnlaun",      # Base salary
    "3": "heildarlaun",    # Total compensation
}


def fetch_batch(years: list[int], salary_type_code: str = "3") -> dict:
    """Fetch occupation wage data for a batch of years."""
    url = f"{BASE_URL}/{TABLE}"

    query = {
        "query": [
            {"code": "Ár", "selection": {"filter": "item", "values": [str(y) for y in years]}},
            {"code": "Starf", "selection": {"filter": "all", "values": ["*"]}},
            {"code": "Kyn", "selection": {"filter": "item", "values": ["0"]}},  # All genders
            {"code": "Laun og vinnutími", "selection": {"filter": "item", "values": [salary_type_code]}},
            {"code": "Eining", "selection": {"filter": "item", "values": list(STAT_CODES.keys())}},
        ],
        "response": {"format": "json-stat2"}
    }

    resp = requests.post(url, json=query, timeout=60)
    resp.raise_for_status()
    return resp.json()


def parse_and_save(data: dict, salary_type: str = "heildarlaun") -> int:
    """Parse JSON-stat2 response and save to database. Returns row count."""
    dims = data["dimension"]
    values = data["value"]

    year_dim = dims["Ár"]["category"]
    occ_dim = dims["Starf"]["category"]
    stat_dim = dims["Eining"]["category"]

    year_codes = list(year_dim["index"].keys())
    occ_codes = list(occ_dim["index"].keys())
    occ_labels = occ_dim["label"]
    stat_codes = list(stat_dim["index"].keys())

    # Dimensions order: Ár × Starf × Eining
    # (Kyn and Laun og vinnutími are fixed at 1 value each)
    n_occ = len(occ_codes)
    n_stat = len(stat_codes)

    # Build occupation data: {(isco_code, year): {mean, median, p25, p75, count}}
    occ_data = {}
    for y_idx, year_code in enumerate(year_codes):
        year = int(year_code)
        for o_idx, occ_code in enumerate(occ_codes):
            key = (occ_code, year)
            if key not in occ_data:
                occ_data[key] = {"name": occ_labels.get(occ_code, occ_code)}

            for s_idx, stat_code in enumerate(stat_codes):
                val_idx = y_idx * (n_occ * n_stat) + o_idx * n_stat + s_idx
                if val_idx < len(values) and values[val_idx] is not None:
                    stat_name = STAT_CODES.get(stat_code, stat_code)
                    val = values[val_idx]
                    # Values are in thousands of ISK — convert to full ISK
                    if stat_name == "count":
                        occ_data[key][stat_name] = int(val)
                    else:
                        occ_data[key][stat_name] = int(val * 1000)

    # Save to database
    saved = 0
    for (isco_code, year), stats in occ_data.items():
        if not any(stats.get(k) for k in ["mean", "median", "p25", "p75"]):
            continue  # Skip empty rows

        database.save_hagstofa_occupation(
            isco_code=isco_code,
            occupation_name=stats["name"],
            year=year,
            mean=stats.get("mean"),
            median=stats.get("median"),
            p25=stats.get("p25"),
            p75=stats.get("p75"),
            observation_count=stats.get("count"),
            salary_type=salary_type,
        )
        saved += 1

    return saved


def fetch_vin02004_batch(years: list[int], salary_type_code: str = "3") -> dict:
    """Fetch decile distribution data from VIN02004 for occupational classes."""
    url = f"{BASE_URL}/{TABLE_VIN02004}"

    # VIN02004 uses "Starfsstétt" (occupational class) instead of "Starf" (occupation)
    # and "Launþegahópur" (employee group) instead of individual occupations
    query = {
        "query": [
            {"code": "Ár", "selection": {"filter": "item", "values": [str(y) for y in years]}},
            {"code": "Launþegahópur", "selection": {"filter": "item", "values": ["0"]}},  # Alls
            {"code": "Starfsstétt", "selection": {"filter": "all", "values": ["*"]}},
            {"code": "Kyn", "selection": {"filter": "item", "values": ["0"]}},  # All genders
            {"code": "Laun og vinnutími", "selection": {"filter": "item", "values": [salary_type_code]}},
            {"code": "Eining", "selection": {"filter": "item", "values": list(VIN02004_STAT_CODES.keys())}},
        ],
        "response": {"format": "json-stat2"}
    }

    resp = requests.post(url, json=query, timeout=60)
    resp.raise_for_status()
    return resp.json()


def parse_and_save_vin02004(data: dict, salary_type: str = "heildarlaun") -> int:
    """Parse VIN02004 JSON-stat2 response and update p10/p90 in existing records."""
    dims = data["dimension"]
    values = data["value"]

    year_dim = dims["Ár"]["category"]
    occ_dim = dims["Starfsstétt"]["category"]
    stat_dim = dims["Eining"]["category"]

    year_codes = list(year_dim["index"].keys())
    occ_codes = list(occ_dim["index"].keys())
    occ_labels = occ_dim["label"]
    stat_codes = list(stat_dim["index"].keys())

    n_occ = len(occ_codes)
    n_stat = len(stat_codes)

    # VIN02004 uses occupational class codes (0-10), not ISCO codes
    # Map class codes to ISCO major group codes
    CLASS_TO_ISCO = {
        "1": "1",   # Stjórnendur
        "2": "2",   # Sérfræðingar
        "3": "3",   # Tæknar og sérmenntað starfsfólk
        "4": "4",   # Skrifstofufólk
        "5": "5",   # Þjónustu-, sölu- og afgreiðslufólk
        "6": "7",   # Iðnaðarmenn (ISCO 7)
        "7": "8",   # Véla- og vélgæslufólk (ISCO 8)
        "8": "9",   # Ósérhæft starfsfólk (ISCO 9)
    }

    updated = 0
    conn = database.get_connection()
    cursor = conn.cursor()

    for y_idx, year_code in enumerate(year_codes):
        year = int(year_code)
        for o_idx, occ_code in enumerate(occ_codes):
            stats = {}
            for s_idx, stat_code in enumerate(stat_codes):
                val_idx = y_idx * (n_occ * n_stat) + o_idx * n_stat + s_idx
                if val_idx < len(values) and values[val_idx] is not None:
                    stat_name = VIN02004_STAT_CODES.get(stat_code, stat_code)
                    stats[stat_name] = int(values[val_idx] * 1000)

            if not stats.get("p10") and not stats.get("p90"):
                continue

            # Update matching hagstofa_occupations rows where isco_code starts with the major group
            isco_prefix = CLASS_TO_ISCO.get(occ_code)
            if isco_prefix:
                cursor.execute("""
                    UPDATE hagstofa_occupations
                    SET p10 = ?, p90 = ?
                    WHERE isco_code LIKE ? AND year = ? AND salary_type = ?
                """, (stats.get("p10"), stats.get("p90"),
                      f"{isco_prefix}%", year, salary_type))
                updated += cursor.rowcount

    conn.commit()
    conn.close()
    return updated


def main():
    parser = argparse.ArgumentParser(description="Fetch Hagstofa occupation wage data")
    parser.add_argument("--years", type=str, default=None,
                        help="Comma-separated years (default: 2014-2024)")
    parser.add_argument("--metadata", action="store_true",
                        help="Print table metadata and exit")
    parser.add_argument("--vin02004-only", action="store_true",
                        help="Only fetch VIN02004 decile data (p10/p90)")
    args = parser.parse_args()

    if args.metadata:
        meta = fetch_metadata()
        for var in meta["variables"]:
            print(f"\n{var['code']} — {var['text']}:")
            for code, label in zip(var["values"], var["valueTexts"]):
                print(f"  {code}: {label}")
        return

    if args.years:
        all_years = [int(y.strip()) for y in args.years.split(",")]
    else:
        all_years = list(range(2014, 2025))

    print(f"Fetching occupation data for {len(all_years)} years: {all_years}")

    batch_size = 6
    total_saved = 0

    if not args.vin02004_only:
        # Phase 1: Fetch VIN02001 (occupation-level data: mean, median, p25, p75)
        for st_code, st_name in SALARY_TYPES.items():
            print(f"\n{'='*40}")
            print(f"VIN02001: Fetching {st_name} (code={st_code})")
            print(f"{'='*40}")

            for i in range(0, len(all_years), batch_size):
                batch_years = all_years[i:i + batch_size]
                print(f"\n  Batch: years {batch_years}")

                try:
                    data = fetch_batch(batch_years, salary_type_code=st_code)
                    saved = parse_and_save(data, salary_type=st_name)
                    total_saved += saved
                    print(f"  Saved {saved} records")
                except requests.exceptions.HTTPError as e:
                    print(f"  API error: {e}")
                    if "Too many values" in str(e.response.text if hasattr(e, 'response') else ''):
                        print("  Reducing batch size...")
                        for y in batch_years:
                            try:
                                data = fetch_batch([y], salary_type_code=st_code)
                                saved = parse_and_save(data, salary_type=st_name)
                                total_saved += saved
                                print(f"    Year {y}: {saved} records")
                            except Exception as e2:
                                print(f"    Year {y} failed: {e2}")
                except Exception as e:
                    print(f"  Error: {e}")

    # Phase 2: Fetch VIN02004 (occupational class deciles: p10, p90)
    total_decile_updated = 0
    for st_code, st_name in SALARY_TYPES.items():
        print(f"\n{'='*40}")
        print(f"VIN02004: Fetching {st_name} deciles (p10/p90)")
        print(f"{'='*40}")

        for i in range(0, len(all_years), batch_size):
            batch_years = all_years[i:i + batch_size]
            print(f"\n  Batch: years {batch_years}")

            try:
                data = fetch_vin02004_batch(batch_years, salary_type_code=st_code)
                updated = parse_and_save_vin02004(data, salary_type=st_name)
                total_decile_updated += updated
                print(f"  Updated {updated} records with p10/p90")
            except Exception as e:
                print(f"  Error: {e}")

    print(f"\nVIN02004: Updated {total_decile_updated} records with decile data")

    # Summary
    from src.database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM hagstofa_occupations")
    total = cursor.fetchone()["cnt"]
    cursor.execute("SELECT COUNT(DISTINCT isco_code) as cnt FROM hagstofa_occupations")
    occupations = cursor.fetchone()["cnt"]
    cursor.execute("SELECT MIN(year) as min_y, MAX(year) as max_y FROM hagstofa_occupations")
    yr = cursor.fetchone()
    conn.close()

    print(f"\nDone! Total: {total_saved} new/updated records")
    print(f"Database: {total} total records, {occupations} occupations, years {yr['min_y']}-{yr['max_y']}")


if __name__ == "__main__":
    main()
