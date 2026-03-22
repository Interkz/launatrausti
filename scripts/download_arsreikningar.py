"""
Download annual report PDFs from Skatturinn using the cart API.

Flow: addToCart → cart page → Áfram → confirmation → download PDF

Usage:
    python scripts/download_arsreikningar.py --kennitala 4710080280 --year 2023
    python scripts/download_arsreikningar.py --batch top_companies.txt
"""

import sys
import os
import json
import argparse
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from playwright.sync_api import sync_playwright

OUTPUT_DIR = Path(__file__).parent.parent / "pdfs"

# Top Icelandic companies by kennitala
TOP_COMPANIES = {
    "4710080280": "Landsbankinn hf.",
    "5810080150": "Arion banki hf.",
    "4910080160": "Íslandsbanki hf.",
    "4602070880": "Síminn hf.",
    "6906801509": "Icelandair Group hf.",
    "6804170640": "Marel hf.",
    "5503850189": "Eimskip hf.",
    "6804012550": "Vodafone Iceland ehf.",
    "5612872189": "Össur hf.",
    "4210984099": "CCP Games hf.",
    "6712012750": "Kvika banki hf.",
    "5907951129": "Origo hf.",
    "5901692339": "Hagar hf.",
    "5602693259": "Festi hf.",
    "6801170670": "TM hf.",
    "5812031390": "Ölgerðin Egill Skallagrímsson ehf.",
}


def get_report_ids(page, kennitala: str, years: list[int]) -> list[dict]:
    """Navigate to company page, find report IDs for requested years."""
    url = f"https://www.skatturinn.is/fyrirtaekjaskra/leit/kennitala/{kennitala}"
    page.goto(url, wait_until="networkidle", timeout=30000)

    # Expand arsreikningar section
    heading = page.query_selector('.collapse:has-text("rsreikningaskr")')
    if heading:
        heading.click()
        page.wait_for_timeout(1000)

    # Parse table rows
    results = []
    rows = page.query_selector_all(".annualTable tbody tr")
    for row in rows:
        tds = row.query_selector_all("td")
        if len(tds) < 5:
            continue

        year_text = tds[0].inner_text().strip()
        try:
            report_year = int(year_text)
        except ValueError:
            continue

        if report_year not in years:
            continue

        item_td = tds[4]
        itemid = item_td.get_attribute("data-itemid")
        typeid = item_td.get_attribute("data-typeid")
        report_type = item_td.inner_text().strip().split("\n")[0]

        if itemid and typeid == "1":  # typeid 1 = individual, 2 = consolidated
            results.append({
                "year": report_year,
                "itemid": itemid,
                "typeid": typeid,
                "type": report_type,
                "kennitala": kennitala,
            })

    return results


def download_pdf(page, itemid: str, typeid: str, output_path: Path) -> bool:
    """Add to cart → checkout → download PDF. Returns True on success."""
    # Step 1: Add to cart
    page.goto(
        f"https://www.skatturinn.is/da/CartService/addToCart?itemid={itemid}&typeid={typeid}",
        wait_until="networkidle", timeout=10000,
    )
    try:
        resp = json.loads(page.inner_text("body"))
        cart_url = resp["shoppingCartUrl"]
    except (json.JSONDecodeError, KeyError):
        print(f"  Failed to add {itemid} to cart")
        return False

    # Step 2: Go to cart
    page.goto(cart_url, wait_until="networkidle", timeout=30000)

    # Step 3: Click Áfram
    afram = page.query_selector('input[value*="fram"]')
    if not afram:
        print(f"  Áfram button not found")
        return False

    afram.click()
    page.wait_for_load_state("networkidle", timeout=30000)

    # Step 4: Click download button
    download_btn = page.query_selector(".download-button, input[name*='Saekja']")
    if not download_btn:
        print(f"  Download button not found")
        return False

    with page.expect_download(timeout=60000) as download_info:
        download_btn.click()
    download = download_info.value
    download.save_as(str(output_path))
    return True


def main():
    parser = argparse.ArgumentParser(description="Download annual report PDFs from Skatturinn")
    parser.add_argument("--kennitala", type=str, help="Single kennitala to download")
    parser.add_argument("--years", type=str, default="2023,2022", help="Comma-separated years")
    parser.add_argument("--top", action="store_true", help="Download for all top companies")
    parser.add_argument("--dry-run", action="store_true", help="List available reports without downloading")
    args = parser.parse_args()

    years = [int(y.strip()) for y in args.years.split(",")]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.kennitala:
        companies = {args.kennitala: args.kennitala}
    elif args.top:
        companies = TOP_COMPANIES
    else:
        print("Specify --kennitala or --top")
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        total_downloaded = 0
        for kennitala, name in companies.items():
            print(f"\n=== {name} ({kennitala}) ===")

            reports = get_report_ids(page, kennitala, years)
            if not reports:
                print(f"  No individual reports found for years {years}")
                continue

            for report in reports:
                pdf_path = OUTPUT_DIR / f"{kennitala}_{report['year']}.pdf"
                if pdf_path.exists():
                    print(f"  {report['year']}: already exists ({pdf_path.name})")
                    continue

                if args.dry_run:
                    print(f"  {report['year']}: itemid={report['itemid']} ({report['type']})")
                    continue

                print(f"  {report['year']}: downloading (itemid={report['itemid']})...", end=" ")
                try:
                    ok = download_pdf(page, report["itemid"], report["typeid"], pdf_path)
                    if ok:
                        size_kb = pdf_path.stat().st_size / 1024
                        print(f"OK ({size_kb:.0f} KB)")
                        total_downloaded += 1
                    else:
                        print("FAILED")
                except Exception as e:
                    print(f"ERROR: {e}")

                time.sleep(2)  # Rate limit

        browser.close()

    print(f"\nDone! Downloaded {total_downloaded} PDFs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
