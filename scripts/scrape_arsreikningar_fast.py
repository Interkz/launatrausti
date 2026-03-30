#!/usr/bin/env python3
"""
Fast parallel Skatturinn annual report scraper.

Hybrid approach:
1. Playwright (parallel workers) to render company pages and extract report numbers
2. Plain HTTP requests for the cart API + download (no browser needed)

~5x faster than the sequential browser-based approach.

Usage:
    python scripts/scrape_arsreikningar_fast.py --from-db --years 2023
    python scripts/scrape_arsreikningar_fast.py --from-db --years 2023 --workers 10
    python scripts/scrape_arsreikningar_fast.py --kennitolur 4602070880 4710080280 --years 2023 2022
"""

import argparse
import asyncio
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from src.database import (
    ScrapeLogEntry,
    get_connection,
    get_ranked_companies,
    init_db,
    save_scrape_log,
)

SKATTURINN_BASE = "https://www.skatturinn.is/fyrirtaekjaskra/leit/kennitala"
CART_API = "https://www.skatturinn.is/da/CartService/addToCart"
OUTPUT_DIR = Path(__file__).parent.parent / "pdfs"

logger = logging.getLogger(__name__)


def _already_scraped(kennitala: str, year: int) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id FROM scrape_log WHERE source='skatturinn_arsreikningar' AND identifier=? AND year=? AND status='success'",
        (kennitala, year),
    )
    found = c.fetchone() is not None
    conn.close()
    return found


def _already_have_pdf(kennitala: str, year: int) -> bool:
    return (OUTPUT_DIR / f"{kennitala}_{year}.pdf").exists()


def _log_result(kennitala: str, year: int, status: str, pdf_path: str = None, error: str = None):
    # Map to valid scrape_log statuses
    valid = {"pending", "running", "downloaded", "extracted", "success", "not_found", "already_exists", "failed"}
    if status not in valid:
        status = "failed"
    now = datetime.now()
    try:
        save_scrape_log(ScrapeLogEntry(
            id=None, source="skatturinn_arsreikningar",
            identifier=kennitala, year=year, status=status,
            pdf_path=pdf_path, error_message=error,
            created_at=now, updated_at=now,
        ))
    except Exception:
        pass  # Don't let logging errors kill the scraper


async def _accept_terms_if_needed(page) -> bool:
    """Skatturinn redirects to /notkunarskilmalar/ on first visit. Accept and retry."""
    if "notkunarskilmalar" in page.url:
        link = await page.query_selector('a:has-text("Leit í fyrirtækjaskrá")')
        if link:
            await link.click()
            await page.wait_for_load_state("networkidle", timeout=15000)
            return True
    return False


async def extract_report_numbers(browser, kennitala: str, years: list[int]) -> list[dict]:
    """Use Playwright to render company page and extract report numbers + years.
    Returns list of {year, report_number, report_type}."""
    page = await browser.new_page()
    entries = []

    try:
        await page.goto(f"{SKATTURINN_BASE}/{kennitala}", wait_until="networkidle", timeout=30000)

        # Handle terms page redirect
        if await _accept_terms_if_needed(page):
            await page.goto(f"{SKATTURINN_BASE}/{kennitala}", wait_until="networkidle", timeout=30000)

        # Expand arsreikningar section
        toggle = await page.query_selector('text="Gögn úr ársreikningaskrá"')
        if not toggle:
            await page.close()
            return entries
        await toggle.click()
        await asyncio.sleep(1.5)

        # Find visible report rows with Kaupa buttons
        rows = await page.query_selector_all("tr")
        seen_years = set()

        for row in rows:
            if not await row.is_visible():
                continue
            text = await row.inner_text()
            if "kaupa" not in text.lower():
                continue

            for year in years:
                if str(year) not in text:
                    continue

                # Extract report number (5-6 digit)
                cells = await row.query_selector_all("td")
                report_number = None
                for cell in cells:
                    ct = (await cell.inner_text()).strip()
                    if ct.isdigit() and len(ct) >= 5:
                        report_number = ct

                if not report_number:
                    continue

                # Prefer Ársreikningur over Samstæðureikningur
                is_individual = "ársreikningur" in text.lower() and "samstæðu" not in text.lower()
                if year in seen_years and not is_individual:
                    continue

                entries = [e for e in entries if e["year"] != year]
                seen_years.add(year)
                entries.append({"year": year, "report_number": report_number})

    except Exception as exc:
        logger.debug("Error extracting from %s: %s", kennitala, exc)
    finally:
        await page.close()

    return entries


async def download_via_browser(context, report_number: str, kennitala: str, year: int) -> bool:
    """Full browser-based cart flow for a single report. Uses its own page."""
    pdf_path = OUTPUT_DIR / f"{kennitala}_{year}.pdf"
    page = await context.new_page()

    try:
        # Step 1: Add to cart via direct URL (fast, no page render needed)
        resp = await page.goto(
            f"{CART_API}?itemid={report_number}&typeid=1",
            wait_until="commit", timeout=15000,
        )
        await asyncio.sleep(0.5)

        # Get cart URL from response (JSON)
        body = await page.evaluate("document.body.innerText")
        import json as _json
        try:
            data = _json.loads(body)
            cart_url = data.get("shoppingCartUrl", "")
        except Exception:
            cart_url = ""

        if not cart_url:
            logger.warning("No cart URL for %s report %s", kennitala, report_number)
            return False

        # Step 2: Go to cart
        await page.goto(cart_url, wait_until="networkidle", timeout=15000)

        # Step 3: Click Áfram
        afram = await page.query_selector('input[value="Áfram"]')
        if not afram:
            return False
        await afram.click()
        await page.wait_for_load_state("networkidle", timeout=15000)
        await asyncio.sleep(1)

        # Step 4: Click Sækja
        saekja = await page.query_selector('a.download-button, a:has-text("Sækja")')
        if not saekja:
            return False

        async with page.expect_download(timeout=30000) as dl_info:
            await saekja.click()
        download = await dl_info.value
        await download.save_as(str(pdf_path))
        logger.info("Downloaded %s (%d KB)", pdf_path.name, pdf_path.stat().st_size // 1024)
        return True

    except Exception as exc:
        logger.debug("Download error %s/%d: %s", kennitala, year, exc)
        return False
    finally:
        await page.close()


async def scrape_worker(worker_id: int, browser, queue: asyncio.Queue, years: list[int], dry_run: bool, stats: dict):
    """Worker that pulls kennitölur from queue and processes them."""
    context = await browser.new_context(accept_downloads=True, locale="is-IS")

    while not queue.empty():
        try:
            kennitala = queue.get_nowait()
        except asyncio.QueueEmpty:
            break

        try:
            entries = await extract_report_numbers(browser, kennitala, years)

            if not entries:
                stats["no_reports"] += 1
                queue.task_done()
                continue

            for entry in entries:
                year = entry["year"]
                report_num = entry["report_number"]

                if dry_run:
                    logger.info("[DRY] %s year=%d report=%s", kennitala, year, report_num)
                    stats["dry"] += 1
                    continue

                success = await download_via_browser(context, report_num, kennitala, year)

                if success:
                    stats["downloaded"] += 1
                    _log_result(kennitala, year, "success", pdf_path=str(OUTPUT_DIR / f"{kennitala}_{year}.pdf"))
                else:
                    stats["failed"] += 1
                    _log_result(kennitala, year, "failed", error="Download failed")

        except Exception as exc:
            logger.warning("Worker %d error on %s: %s", worker_id, kennitala, exc)
            stats["failed"] += 1

        stats["processed"] += 1
        if stats["processed"] % 10 == 0:
            logger.info(
                "Progress: %d/%d | %d downloaded | %d failed | %d no reports",
                stats["processed"], stats["total"],
                stats["downloaded"], stats["failed"], stats["no_reports"],
            )

        queue.task_done()

    await context.close()


async def run(kennitolur: list[str], years: list[int], workers: int, dry_run: bool):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    init_db()

    # Filter already-done
    to_scrape = []
    for kt in kennitolur:
        kt = kt.replace("-", "").strip()
        skip = all(_already_scraped(kt, y) or _already_have_pdf(kt, y) for y in years)
        if skip:
            logger.debug("Skipping %s (already done)", kt)
        else:
            to_scrape.append(kt)

    logger.info("Scraping %d companies (%d skipped), years=%s, workers=%d",
                len(to_scrape), len(kennitolur) - len(to_scrape), years, workers)

    if not to_scrape:
        logger.info("Nothing to scrape.")
        return

    queue = asyncio.Queue()
    for kt in to_scrape:
        queue.put_nowait(kt)

    stats = {"processed": 0, "downloaded": 0, "failed": 0, "no_reports": 0, "dry": 0, "total": len(to_scrape)}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # Launch parallel workers
        worker_tasks = [
            asyncio.create_task(scrape_worker(i, browser, queue, years, dry_run, stats))
            for i in range(min(workers, len(to_scrape)))
        ]

        await asyncio.gather(*worker_tasks)
        await browser.close()

    logger.info(
        "Done: %d processed, %d downloaded, %d failed, %d no reports",
        stats["processed"], stats["downloaded"], stats["failed"], stats["no_reports"],
    )


def main():
    parser = argparse.ArgumentParser(description="Fast parallel Skatturinn PDF scraper")
    parser.add_argument("--kennitolur", nargs="+", help="Specific kennitölur")
    parser.add_argument("--from-db", action="store_true", help="Scrape all companies in DB")
    parser.add_argument("--top", type=int, help="Scrape top N companies by salary")
    parser.add_argument("--years", nargs="+", type=int, default=[2023])
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.from_db:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT kennitala FROM companies WHERE kennitala IS NOT NULL ORDER BY id")
        kennitolur = [r["kennitala"] for r in c.fetchall()]
        conn.close()
    elif args.top:
        companies = get_ranked_companies(limit=args.top)
        kennitolur = [c["kennitala"] for c in companies if c.get("kennitala")]
    elif args.kennitolur:
        kennitolur = args.kennitolur
    else:
        parser.error("Specify --kennitolur, --from-db, or --top")
        return

    asyncio.run(run(kennitolur, args.years, args.workers, args.dry_run))


if __name__ == "__main__":
    main()
