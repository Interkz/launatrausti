#!/usr/bin/env python3
"""
Skatturinn Annual Report PDF Scraper

Downloads annual report PDFs from the Icelandic Tax Authority's company registry
(skatturinn.is) using Playwright browser automation.

The skatturinn.is website renders company pages with JavaScript and lists annual
reports under "Gogn ur arsreikningaskra". This script navigates to each company's
page, discovers the report table, and attempts to download the corresponding PDFs.

Usage:
    # Download for specific companies and years
    python scripts/scrape_arsreikningar.py --kennitolur 4710080280 5810080150 --years 2023 2022

    # Download for all companies in the database
    python scripts/scrape_arsreikningar.py --from-db

    # Download for top N companies by average salary
    python scripts/scrape_arsreikningar.py --top 50

    # Dry run: navigate and report without downloading
    python scripts/scrape_arsreikningar.py --kennitolur 4710080280 --years 2023 --dry-run

    # Debug mode: visible browser
    python scripts/scrape_arsreikningar.py --kennitolur 4710080280 --no-headless
"""

import argparse
import asyncio
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeout
from src.database import (
    ScrapeLogEntry,
    get_connection,
    get_ranked_companies,
    init_db,
    save_scrape_log,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKATTURINN_BASE_URL = "https://www.skatturinn.is/fyrirtaekjaskra/leit/kennitala"
SOURCE_NAME = "skatturinn_arsreikningar"
DEFAULT_YEARS = [2023, 2022]
DEFAULT_RATE_LIMIT = 5.0  # seconds between page loads
PAGE_LOAD_TIMEOUT = 30_000  # milliseconds
ELEMENT_TIMEOUT = 10_000  # milliseconds

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "pdfs"
DEBUG_DIR = DEFAULT_OUTPUT_DIR / "debug"

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ScrapeResult:
    """Result of a single scrape attempt for one kennitala+year combination."""
    kennitala: str
    year: int
    pdf_path: Optional[Path]
    status: str  # 'downloaded', 'already_exists', 'not_found', 'failed'
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_logging(verbose: bool = False) -> None:
    """Configure logging with appropriate level and format."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _ensure_directories(output_dir: Path) -> None:
    """Create output and debug directories if they do not exist."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "debug").mkdir(parents=True, exist_ok=True)


def _check_already_scraped(kennitala: str, year: int) -> bool:
    """Return True if a successful scrape_log entry already exists for this kennitala+year."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id FROM scrape_log
        WHERE source = ? AND identifier = ? AND year = ? AND status = 'success'
        """,
        (SOURCE_NAME, kennitala, year),
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


def _log_scrape(
    kennitala: str,
    year: int,
    status: str,
    pdf_path: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    """Write a scrape_log entry to the database."""
    now = datetime.now()
    entry = ScrapeLogEntry(
        id=None,
        source=SOURCE_NAME,
        identifier=kennitala,
        year=year,
        status=status,
        pdf_path=pdf_path,
        error_message=error_message,
        created_at=now,
        updated_at=now,
    )
    save_scrape_log(entry)


async def _save_debug_screenshot(page: Page, kennitala: str, output_dir: Path) -> None:
    """Capture a screenshot for debugging when a scrape fails."""
    debug_path = output_dir / "debug" / f"{kennitala}_error.png"
    try:
        await page.screenshot(path=str(debug_path), full_page=True)
        logger.info("Debug screenshot saved: %s", debug_path)
    except Exception as exc:
        logger.warning("Could not save debug screenshot: %s", exc)


async def _rate_limit_wait(last_request_time: float, rate_limit_seconds: float) -> float:
    """Enforce minimum delay between page loads. Returns the new 'last request' timestamp."""
    elapsed = time.monotonic() - last_request_time
    if elapsed < rate_limit_seconds:
        wait = rate_limit_seconds - elapsed
        logger.debug("Rate limiting: waiting %.1fs", wait)
        await asyncio.sleep(wait)
    return time.monotonic()


# ---------------------------------------------------------------------------
# Core scraper logic
# ---------------------------------------------------------------------------

async def _navigate_to_company(page: Page, kennitala: str) -> bool:
    """
    Navigate to the Skatturinn company page for the given kennitala.
    Returns True if the page loaded successfully and contains company info.
    """
    url = f"{SKATTURINN_BASE_URL}/{kennitala}"
    logger.info("Navigating to %s", url)

    try:
        response = await page.goto(url, wait_until="networkidle", timeout=PAGE_LOAD_TIMEOUT)
        if response and response.status >= 400:
            logger.error("HTTP %d for kennitala %s", response.status, kennitala)
            return False
    except PlaywrightTimeout:
        logger.error("Timeout loading page for kennitala %s", kennitala)
        return False
    except Exception as exc:
        logger.error("Navigation error for kennitala %s: %s", kennitala, exc)
        return False

    # Wait for the page content to render (JS-based)
    try:
        await page.wait_for_load_state("networkidle", timeout=PAGE_LOAD_TIMEOUT)
    except PlaywrightTimeout:
        logger.warning("Network idle timeout for %s, proceeding anyway", kennitala)

    return True


async def _find_arsreikningar_section(page: Page) -> Optional[object]:
    """
    Locate and EXPAND the annual reports section on the page.

    The section is a collapsible toggle titled "Gögn úr ársreikningaskrá".
    We need to click it to reveal the report table.

    Returns the section element if found and expanded, None otherwise.
    """
    # Click the toggle to expand the section
    toggle = await page.query_selector('text="Gögn úr ársreikningaskrá"')
    if toggle:
        try:
            await toggle.click()
            await asyncio.sleep(2)
            logger.debug("Expanded ársreikningaskrá section")
            return toggle
        except Exception as exc:
            logger.warning("Failed to expand ársreikningaskrá: %s", exc)

    # Fallback selectors
    for selector in [
        "text='Gogn ur arsreikningaskra'",
        "h2:has-text('rsreikningaskr'), h3:has-text('rsreikningaskr')",
    ]:
        try:
            element = await page.wait_for_selector(selector, timeout=ELEMENT_TIMEOUT)
            if element:
                await element.click()
                await asyncio.sleep(2)
                return element
        except (PlaywrightTimeout, Exception):
            continue

    return None


async def _find_report_entries(page: Page, target_years: list[int]) -> list[dict]:
    """
    Parse the annual report table and extract entries for the target years.
    Only considers VISIBLE rows with visible Kaupa buttons (after section expansion).

    Returns a list of dicts with keys: year, report_number, report_type, link_element.
    Prefers "Ársreikningur" over "Samstæðureikningur" for each year.
    """
    entries = []
    seen_years = set()

    try:
        rows = await page.query_selector_all("tr")
        for row in rows:
            if not await row.is_visible():
                continue

            text = await row.inner_text()
            if not text or "kaupa" not in text.lower():
                continue

            # Find visible Kaupa link in this row
            kaupa = await row.query_selector('a:has-text("Kaupa")')
            if not kaupa or not await kaupa.is_visible():
                continue

            for year in target_years:
                if str(year) not in text:
                    continue

                # Extract report number (5-6 digit number)
                cells = await row.query_selector_all("td")
                report_number = None
                for cell in cells:
                    cell_text = (await cell.inner_text()).strip()
                    if cell_text.isdigit() and len(cell_text) >= 5:
                        report_number = cell_text

                # Determine report type
                text_lower = text.lower()
                if "samstæðu" in text_lower or "samstaed" in text_lower:
                    report_type = "consolidated"
                elif "ársreikningur" in text_lower or "arsreikningur" in text_lower:
                    report_type = "individual"
                else:
                    report_type = "unknown"

                # Prefer individual (Ársreikningur) over consolidated
                if year in seen_years and report_type != "individual":
                    continue

                # Remove previous entry for this year if we found a better one
                entries = [e for e in entries if e["year"] != year]
                seen_years.add(year)

                entries.append({
                    "year": year,
                    "report_number": report_number,
                    "report_type": report_type,
                    "row_text": text.strip()[:200],
                    "link_element": kaupa,
                })
                logger.debug(
                    "Found entry: year=%d, report_number=%s, type=%s",
                    year, report_number, report_type,
                )

    except Exception as exc:
        logger.warning("Error parsing report table: %s", exc)

    return entries


async def _attempt_download(
    page: Page,
    entry: dict,
    kennitala: str,
    output_dir: Path,
    dry_run: bool = False,
) -> Optional[Path]:
    """
    Download a PDF via the Skatturinn cart flow:
    1. Click "Kaupa" on the report row (adds to cart)
    2. Navigate to cart via "Karfa" link
    3. Click "Áfram" to proceed
    4. Click "Sækja" to download the PDF
    5. Navigate back to company page for next report

    Returns the path of the saved PDF, or None on failure.
    """
    year = entry["year"]
    report_number = entry.get("report_number")
    pdf_filename = f"{kennitala}_{year}.pdf"
    pdf_path = output_dir / pdf_filename

    if dry_run:
        logger.info(
            "[DRY RUN] kennitala=%s, year=%d, report_number=%s, type=%s, row=%s",
            kennitala, year, report_number, entry.get("report_type"), entry.get("row_text", "")[:80],
        )
        return None

    # Step 1: Click "Kaupa" on the report row
    link = entry.get("link_element")
    if not link:
        logger.warning("No Kaupa link for kennitala=%s year=%d", kennitala, year)
        return None

    try:
        await link.click()
        await asyncio.sleep(1.5)
        logger.info("Added to cart: kennitala=%s year=%d", kennitala, year)
    except Exception as exc:
        logger.error("Failed to click Kaupa: %s", exc)
        return None

    # Step 2: Navigate to cart
    try:
        cart_link = await page.query_selector('a:has-text("Karfa")')
        if not cart_link:
            logger.error("Cart link not found")
            return None
        await cart_link.click()
        await page.wait_for_load_state("networkidle", timeout=PAGE_LOAD_TIMEOUT)
        await asyncio.sleep(2)
    except Exception as exc:
        logger.error("Failed to navigate to cart: %s", exc)
        return None

    # Step 3: Click "Áfram" (Continue)
    try:
        afram = await page.query_selector('input[value="Áfram"]')
        if not afram:
            logger.error("Áfram button not found in cart")
            return None
        await afram.click()
        await page.wait_for_load_state("networkidle", timeout=PAGE_LOAD_TIMEOUT)
        await asyncio.sleep(3)
    except Exception as exc:
        logger.error("Failed to click Áfram: %s", exc)
        return None

    # Step 4: Navigate to "Sækja" tab and click download
    try:
        # The confirmation page has tabs: Vörurnar, Ljúting, Verð, Sækja
        # Click the Sækja tab first
        saekja_tab = await page.query_selector('a:has-text("Sækja"), [href*="Saekja"], td:has-text("Sækja")')
        if saekja_tab and await saekja_tab.is_visible():
            await saekja_tab.click()
            await asyncio.sleep(3)

        # Now look for the actual download button/link
        download_btn = await page.query_selector('a.download-button, a:has-text("Sækja"), input[value*="Sækja"]')
        if not download_btn:
            # Try all visible links
            links = await page.query_selector_all('a')
            for link in links:
                text = (await link.inner_text()).strip()
                vis = await link.is_visible()
                href = await link.get_attribute('href') or ''
                if vis and ('sækja' in text.lower() or 'download' in href.lower()):
                    download_btn = link
                    break

        if not download_btn:
            logger.error("Download button not found")
            await _save_debug_screenshot(page, kennitala, output_dir)
            return None

        async with page.expect_download(timeout=PAGE_LOAD_TIMEOUT) as dl_info:
            await download_btn.click()
        download = await dl_info.value
        await download.save_as(str(pdf_path))
        logger.info("Downloaded: %s (%d bytes)", pdf_path, pdf_path.stat().st_size)
    except PlaywrightTimeout:
        logger.error("Download timeout for kennitala=%s year=%d", kennitala, year)
        await _save_debug_screenshot(page, kennitala, output_dir)
        return None
    except Exception as exc:
        logger.error("Download failed for kennitala=%s year=%d: %s", kennitala, year, exc)
        return None

    # Step 5: Navigate back to company page for next report
    try:
        await page.goto(
            f"{SKATTURINN_BASE_URL}/{kennitala}",
            wait_until="networkidle",
            timeout=PAGE_LOAD_TIMEOUT,
        )
        # Re-expand arsreikningar section
        toggle = await page.query_selector('text="Gögn úr ársreikningaskrá"')
        if toggle:
            await toggle.click()
            await asyncio.sleep(2)
    except Exception:
        logger.debug("Could not navigate back to company page")

    return pdf_path


async def _scrape_single_company(
    page: Page,
    kennitala: str,
    years: list[int],
    output_dir: Path,
    dry_run: bool = False,
) -> list[ScrapeResult]:
    """
    Scrape annual reports for a single company across the requested years.

    This is the main state machine:
    1. Navigate to the company page.
    2. Find the arsreikningar section.
    3. For each target year, find the report entry and attempt download.
    """
    results = []

    # Step 1: Navigate
    if not await _navigate_to_company(page, kennitala):
        await _save_debug_screenshot(page, kennitala, output_dir)
        for year in years:
            result = ScrapeResult(
                kennitala=kennitala,
                year=year,
                pdf_path=None,
                status="failed",
                error="Could not load company page",
            )
            results.append(result)
            _log_scrape(kennitala, year, "failed", error_message="Could not load company page")
        return results

    # Step 2: Find the arsreikningar section
    section = await _find_arsreikningar_section(page)
    if section is None:
        logger.warning("No arsreikningar section found for kennitala %s", kennitala)
        await _save_debug_screenshot(page, kennitala, output_dir)
        for year in years:
            result = ScrapeResult(
                kennitala=kennitala,
                year=year,
                pdf_path=None,
                status="not_found",
                error="Arsreikningar section not found on page",
            )
            results.append(result)
            _log_scrape(kennitala, year, "failed", error_message="Arsreikningar section not found")
        return results

    # Step 3: Find report entries for target years
    report_entries = await _find_report_entries(page, years)
    logger.info(
        "Found %d report entries for kennitala %s (requested years: %s)",
        len(report_entries), kennitala, years,
    )

    # Track which years we found entries for
    years_found = set()
    for entry in report_entries:
        years_found.add(entry["year"])

    # Report missing years
    for year in years:
        if year not in years_found:
            logger.warning("No report entry found for kennitala %s, year %d", kennitala, year)
            result = ScrapeResult(
                kennitala=kennitala,
                year=year,
                pdf_path=None,
                status="not_found",
                error=f"No report entry found for year {year}",
            )
            results.append(result)
            _log_scrape(kennitala, year, "failed", error_message=f"No report found for year {year}")

    # Step 4: Attempt downloads for found entries
    # Group entries by year (prefer individual over consolidated if both exist)
    best_entries = {}
    for entry in report_entries:
        year = entry["year"]
        if year not in best_entries:
            best_entries[year] = entry
        elif entry.get("report_type") == "individual" and best_entries[year].get("report_type") != "individual":
            best_entries[year] = entry

    for year, entry in best_entries.items():
        if dry_run:
            logger.info(
                "[DRY RUN] kennitala=%s, year=%d, report_number=%s, type=%s, row=%s",
                kennitala, year, entry.get("report_number"),
                entry.get("report_type"), entry.get("row_text", "")[:100],
            )
            result = ScrapeResult(
                kennitala=kennitala,
                year=year,
                pdf_path=None,
                status="not_found",
                error="Dry run - no download attempted",
            )
            results.append(result)
            continue

        try:
            _log_scrape(kennitala, year, "running")
            pdf_path = await _attempt_download(page, entry, kennitala, output_dir, dry_run=False)

            if pdf_path and pdf_path.exists():
                result = ScrapeResult(
                    kennitala=kennitala,
                    year=year,
                    pdf_path=pdf_path,
                    status="downloaded",
                )
                _log_scrape(kennitala, year, "success", pdf_path=str(pdf_path))
            else:
                await _save_debug_screenshot(page, f"{kennitala}_{year}", output_dir)
                result = ScrapeResult(
                    kennitala=kennitala,
                    year=year,
                    pdf_path=None,
                    status="failed",
                    error="Download attempted but no PDF saved",
                )
                _log_scrape(kennitala, year, "failed", error_message="Download attempted but no PDF saved")

            results.append(result)

        except Exception as exc:
            logger.error("Error downloading for kennitala=%s, year=%d: %s", kennitala, year, exc)
            await _save_debug_screenshot(page, f"{kennitala}_{year}", output_dir)
            result = ScrapeResult(
                kennitala=kennitala,
                year=year,
                pdf_path=None,
                status="failed",
                error=str(exc),
            )
            results.append(result)
            _log_scrape(kennitala, year, "failed", error_message=str(exc))

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def scrape_arsreikningar(
    kennitolur: list[str],
    years: Optional[list[int]] = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    rate_limit_seconds: float = DEFAULT_RATE_LIMIT,
    headless: bool = True,
    dry_run: bool = False,
) -> list[ScrapeResult]:
    """
    Download annual report PDFs from Skatturinn for the given companies and years.

    For each kennitala:
    1. Check scrape_log -- skip if already downloaded.
    2. Navigate to skatturinn.is/fyrirtaekjaskra/leit/kennitala/{kt}.
    3. Find "Gogn ur arsreikningaskra" section.
    4. Locate the report entry for each target year.
    5. Attempt to download the PDF.
    6. Save as pdfs/{kennitala}_{year}.pdf.
    7. Update scrape_log with status.

    Args:
        kennitolur: List of company kennitala identifiers (10-digit strings).
        years: List of years to download. Defaults to [2023, 2022].
        output_dir: Directory for saving PDFs. Defaults to pdfs/.
        rate_limit_seconds: Minimum seconds between page loads. Default 5.0.
        headless: Run browser in headless mode. Default True.
        dry_run: Navigate and report but do not download. Default False.

    Returns:
        List of ScrapeResult for each kennitala+year combination.
    """
    if years is None:
        years = list(DEFAULT_YEARS)

    _ensure_directories(output_dir)
    init_db()

    all_results: list[ScrapeResult] = []
    last_request_time = 0.0

    logger.info(
        "Starting scrape: %d companies, years=%s, headless=%s, dry_run=%s",
        len(kennitolur), years, headless, dry_run,
    )

    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            accept_downloads=True,
            locale="is-IS",
        )
        page = await context.new_page()

        for i, kennitala in enumerate(kennitolur, 1):
            kennitala = kennitala.replace("-", "").strip()
            logger.info(
                "=== [%d/%d] Processing kennitala: %s ===",
                i, len(kennitolur), kennitala,
            )

            # Check which years still need scraping
            years_to_scrape = []
            for year in years:
                if _check_already_scraped(kennitala, year):
                    logger.info("Already scraped: kennitala=%s, year=%d -- skipping", kennitala, year)
                    all_results.append(ScrapeResult(
                        kennitala=kennitala,
                        year=year,
                        pdf_path=None,
                        status="already_exists",
                    ))
                else:
                    years_to_scrape.append(year)

            if not years_to_scrape:
                logger.info("All requested years already scraped for %s", kennitala)
                continue

            # Rate limiting
            last_request_time = await _rate_limit_wait(last_request_time, rate_limit_seconds)

            # Scrape this company
            try:
                results = await _scrape_single_company(
                    page, kennitala, years_to_scrape, output_dir, dry_run=dry_run,
                )
                all_results.extend(results)
            except Exception as exc:
                logger.error("Unhandled error for kennitala %s: %s", kennitala, exc)
                await _save_debug_screenshot(page, kennitala, output_dir)
                for year in years_to_scrape:
                    all_results.append(ScrapeResult(
                        kennitala=kennitala,
                        year=year,
                        pdf_path=None,
                        status="failed",
                        error=str(exc),
                    ))
                    _log_scrape(kennitala, year, "failed", error_message=str(exc))

        await browser.close()

    # Summary
    downloaded = sum(1 for r in all_results if r.status == "downloaded")
    skipped = sum(1 for r in all_results if r.status == "already_exists")
    not_found = sum(1 for r in all_results if r.status == "not_found")
    failed = sum(1 for r in all_results if r.status == "failed")
    logger.info(
        "Scrape complete: downloaded=%d, already_exists=%d, not_found=%d, failed=%d",
        downloaded, skipped, not_found, failed,
    )

    return all_results


# ---------------------------------------------------------------------------
# Database query modes
# ---------------------------------------------------------------------------

def _get_kennitolur_from_db() -> list[str]:
    """Get all company kennitolur from the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT kennitala FROM companies ORDER BY kennitala")
    rows = cursor.fetchall()
    conn.close()
    return [row["kennitala"] for row in rows]


def _get_top_kennitolur(top_n: int) -> list[str]:
    """Get kennitolur for the top N companies by average salary."""
    companies = get_ranked_companies(limit=top_n, exclude_sample=True)
    if not companies:
        # Fall back to include sample data
        companies = get_ranked_companies(limit=top_n, exclude_sample=False)
    return [c["kennitala"] for c in companies]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Download annual report PDFs from Skatturinn (Icelandic Tax Authority)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --kennitolur 4710080280 5810080150 --years 2023 2022
  %(prog)s --from-db
  %(prog)s --top 50
  %(prog)s --kennitolur 4710080280 --years 2023 --dry-run
  %(prog)s --kennitolur 4710080280 --no-headless  # visible browser for debugging
        """,
    )

    # Source of kennitolur (mutually exclusive)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--kennitolur",
        nargs="+",
        help="Kennitolur to scrape (space-separated)",
    )
    source_group.add_argument(
        "--from-db",
        action="store_true",
        help="Scrape for all companies in the database",
    )
    source_group.add_argument(
        "--top",
        type=int,
        metavar="N",
        help="Scrape for top N companies by average salary",
    )

    # Options
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=DEFAULT_YEARS,
        help=f"Years to download (default: {DEFAULT_YEARS})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for PDFs (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=DEFAULT_RATE_LIMIT,
        help=f"Seconds between page loads (default: {DEFAULT_RATE_LIMIT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Navigate and report but do not download PDFs",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser in visible mode (for debugging)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    return parser.parse_args()


async def async_main() -> None:
    """Async entry point for the CLI."""
    args = parse_args()
    _setup_logging(verbose=args.verbose)

    # Resolve kennitolur
    if args.kennitolur:
        kennitolur = args.kennitolur
    elif args.from_db:
        logger.info("Fetching all companies from database...")
        kennitolur = _get_kennitolur_from_db()
        if not kennitolur:
            logger.error("No companies found in database. Run import scripts first.")
            sys.exit(1)
        logger.info("Found %d companies in database", len(kennitolur))
    elif args.top:
        logger.info("Fetching top %d companies by average salary...", args.top)
        kennitolur = _get_top_kennitolur(args.top)
        if not kennitolur:
            logger.error("No ranked companies found in database.")
            sys.exit(1)
        logger.info("Found %d companies", len(kennitolur))
    else:
        logger.error("No kennitolur source specified")
        sys.exit(1)

    results = await scrape_arsreikningar(
        kennitolur=kennitolur,
        years=args.years,
        output_dir=args.output_dir,
        rate_limit_seconds=args.rate_limit,
        headless=not args.no_headless,
        dry_run=args.dry_run,
    )

    # Print summary table
    print("\n" + "=" * 80)
    print(f"{'Kennitala':<14} {'Year':<6} {'Status':<16} {'Path / Error'}")
    print("-" * 80)
    for r in results:
        detail = ""
        if r.pdf_path:
            detail = str(r.pdf_path)
        elif r.error:
            detail = r.error[:50]
        print(f"{r.kennitala:<14} {r.year:<6} {r.status:<16} {detail}")
    print("=" * 80)

    # Exit code: 0 if any downloads succeeded or all were already_exists, 1 otherwise
    has_success = any(r.status in ("downloaded", "already_exists") for r in results)
    sys.exit(0 if has_success else 1)


def main() -> None:
    """Synchronous entry point."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
