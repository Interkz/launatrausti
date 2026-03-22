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
TABLE = "Samfelag/launogtekjur/1_laun/1_laun/VIN02001.px"

# Stat codes for the "Eining" dimension
STAT_CODES = {
    "0": "mean",       # Meðaltal
    "1": "p25",        # Neðri fjórðungsmörk
    "2": "median",     # Miðgildi
    "3": "p75",        # Efri fjórðungsmörk
    "4": "count",      # Fjöldi athugana
}


def fetch_metadata():
    """Fetch table metadata to discover dimension codes."""
    url = f"{BASE_URL}/{TABLE}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_batch(years: list[int]) -> dict:
    """Fetch occupation wage data for a batch of years."""
    url = f"{BASE_URL}/{TABLE}"

    query = {
        "query": [
            {"code": "Ár", "selection": {"filter": "item", "values": [str(y) for y in years]}},
            {"code": "Starf", "selection": {"filter": "all", "values": ["*"]}},
            {"code": "Kyn", "selection": {"filter": "item", "values": ["0"]}},  # All genders
            {"code": "Laun og vinnutími", "selection": {"filter": "item", "values": ["3"]}},  # Heildarlaun fullvinnandi
            {"code": "Eining", "selection": {"filter": "item", "values": list(STAT_CODES.keys())}},
        ],
        "response": {"format": "json-stat2"}
    }

    resp = requests.post(url, json=query, timeout=60)
    resp.raise_for_status()
    return resp.json()


def parse_and_save(data: dict) -> int:
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
        )
        saved += 1

    return saved


def main():
    parser = argparse.ArgumentParser(description="Fetch Hagstofa occupation wage data")
    parser.add_argument("--years", type=str, default=None,
                        help="Comma-separated years (default: 2014-2024)")
    parser.add_argument("--metadata", action="store_true",
                        help="Print table metadata and exit")
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

    # PX-Web has a ~10K values per request limit
    # With ~250 occupations × 5 stats = ~1,250 per year
    # Safe batch size: ~7 years per request
    batch_size = 6
    total_saved = 0

    for i in range(0, len(all_years), batch_size):
        batch_years = all_years[i:i + batch_size]
        print(f"\nBatch {i // batch_size + 1}: years {batch_years}")

        try:
            data = fetch_batch(batch_years)
            saved = parse_and_save(data)
            total_saved += saved
            print(f"  Saved {saved} records")
        except requests.exceptions.HTTPError as e:
            print(f"  API error: {e}")
            if "Too many values" in str(e.response.text if hasattr(e, 'response') else ''):
                print("  Reducing batch size...")
                # Try one year at a time
                for y in batch_years:
                    try:
                        data = fetch_batch([y])
                        saved = parse_and_save(data)
                        total_saved += saved
                        print(f"    Year {y}: {saved} records")
                    except Exception as e2:
                        print(f"    Year {y} failed: {e2}")
        except Exception as e:
            print(f"  Error: {e}")

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
