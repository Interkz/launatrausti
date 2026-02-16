#!/usr/bin/env python3
"""
Scrape Rikisreikningur (government annual accounts) PDFs.

Downloads annual account PDFs for Icelandic government institutions from
arsreikningar.rikisreikningur.is. Parses the listing page to find institutions,
ministries, file IDs, and years, then downloads the corresponding PDFs.

Usage:
    # Download all institution PDFs
    python scripts/scrape_rikisreikningur.py

    # List institutions without downloading
    python scripts/scrape_rikisreikningur.py --list-only

    # Filter by ministry name
    python scripts/scrape_rikisreikningur.py --ministry "Forsaetisraduneytid"

    # Filter by year
    python scripts/scrape_rikisreikningur.py --year 2023

    # Dry run (check what would be downloaded)
    python scripts/scrape_rikisreikningur.py --dry-run
"""

import sys
import re
import time
import argparse
import unicodedata
import logging
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import save_scrape_log, ScrapeLogEntry, get_connection, init_db

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package is required. Install with: pip install requests>=2.31.0")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: 'beautifulsoup4' package is required. Install with: pip install beautifulsoup4>=4.12.0")
    sys.exit(1)


# --- Configuration ---

LISTING_URL = "https://arsreikningar.rikisreikningur.is/stofnun"
FILE_URL_TEMPLATE = "https://arsreikningar.rikisreikningur.is/Stofnun/GetFile/{id}"
SOURCE_NAME = "rikisreikningur"
DEFAULT_OUTPUT_DIR = Path("pdfs/rikis/")
DEFAULT_RATE_LIMIT = 2.0

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# --- Data classes ---

@dataclass
class InstitutionInfo:
    """Represents a government institution entry from the listing page."""
    name: str
    file_id: int
    ministry: str
    year: int


@dataclass
class ScrapeResult:
    """Result of a single PDF download attempt."""
    institution: InstitutionInfo
    success: bool
    pdf_path: Optional[str] = None
    error: Optional[str] = None


# --- Utility functions ---

def slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug.

    Handles Icelandic characters by transliterating to ASCII,
    replaces spaces and special characters with underscores,
    and lowercases the result.
    """
    # Normalize unicode and transliterate to ASCII
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    # Replace non-alphanumeric characters with underscores
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text)
    # Collapse multiple underscores and strip leading/trailing
    text = re.sub(r"_+", "_", text).strip("_")
    return text.lower()


def _get_session() -> requests.Session:
    """Create a requests session with appropriate headers."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "is,en;q=0.5",
    })
    return session


# --- Scraping functions ---

def scrape_institution_list() -> list[InstitutionInfo]:
    """Parse the listing page to get all institution names + file IDs.

    Fetches the listing page at arsreikningar.rikisreikningur.is/stofnun
    and parses the HTML table to extract institution information.

    Returns:
        List of InstitutionInfo objects. May be empty if the page uses
        JavaScript rendering that requests+BeautifulSoup cannot handle.
    """
    session = _get_session()

    logger.info("Fetching institution listing from %s", LISTING_URL)

    try:
        response = session.get(LISTING_URL, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error("Failed to fetch listing page: %s", e)
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    institutions: list[InstitutionInfo] = []

    # The page renders an HTML table with columns:
    # Ar (Year) | Raduneytid (Ministry) | Stofnun (Institution) | Skra (File link) | Undirritad (Signed)
    # PDF links follow the pattern: ../../Stofnun/GetFile/{file_id}

    # Find all table rows
    rows = soup.find_all("tr")

    if not rows:
        logger.warning(
            "No table rows found in HTML. The page may use JavaScript rendering "
            "that requires a browser engine (Playwright/Selenium). "
            "Try inspecting the page manually."
        )
        return []

    file_id_pattern = re.compile(r"Stofnun/GetFile/(\d+)", re.IGNORECASE)
    parsed_count = 0

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        # Extract year from first cell
        year_text = cells[0].get_text(strip=True)
        try:
            year = int(year_text)
        except (ValueError, TypeError):
            continue

        # Extract ministry from second cell
        ministry = cells[1].get_text(strip=True)

        # Extract institution name from third cell
        institution_name = cells[2].get_text(strip=True)

        # Extract file ID from the link in the fourth cell
        link = cells[3].find("a")
        if not link or not link.get("href"):
            continue

        href = link["href"]
        match = file_id_pattern.search(href)
        if not match:
            continue

        file_id = int(match.group(1))

        institutions.append(InstitutionInfo(
            name=institution_name,
            file_id=file_id,
            ministry=ministry,
            year=year,
        ))
        parsed_count += 1

    if parsed_count == 0:
        logger.warning(
            "Parsed 0 institutions from %d table rows. The page structure may "
            "have changed, or JavaScript rendering is required. Inspect the page "
            "HTML to diagnose.",
            len(rows),
        )
    else:
        logger.info("Parsed %d institutions from listing page", parsed_count)

    return institutions


def _is_already_scraped(source: str, identifier: str, year: Optional[int]) -> bool:
    """Check if an entry exists in scrape_log with status 'success'."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id FROM scrape_log
        WHERE source = ? AND identifier = ? AND year = ? AND status = 'success'
        """,
        (source, identifier, year),
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


def _save_institution_as_company(name: str, year: int) -> None:
    """Register the institution in the companies table with sector='public'.

    Uses a synthetic kennitala derived from the institution name since
    government institutions on this listing don't always carry a kennitala.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Use the institution code (e.g. "00101") as a stable identifier if present
    # Format: "00101 - Embætti forseta Íslands"
    code_match = re.match(r"^(\d{5})\s*-\s*(.+)$", name)
    if code_match:
        kennitala = f"RIKIS-{code_match.group(1)}"
        display_name = code_match.group(2).strip()
    else:
        kennitala = f"RIKIS-{slugify(name)[:20]}"
        display_name = name

    # Check if company already exists
    cursor.execute("SELECT id FROM companies WHERE kennitala = ?", (kennitala,))
    row = cursor.fetchone()

    now = datetime.now().isoformat()

    if row:
        cursor.execute(
            "UPDATE companies SET name = ?, sector = 'public', updated_at = ? WHERE id = ?",
            (display_name, now, row["id"]),
        )
    else:
        cursor.execute(
            "INSERT INTO companies (kennitala, name, sector, updated_at) VALUES (?, ?, 'public', ?)",
            (kennitala, display_name, now),
        )

    conn.commit()
    conn.close()


def download_institution_pdfs(
    institutions: list[InstitutionInfo],
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    rate_limit_seconds: float = DEFAULT_RATE_LIMIT,
    dry_run: bool = False,
) -> list[ScrapeResult]:
    """Download PDFs for a list of institutions.

    Checks scrape_log for idempotency -- institutions already successfully
    downloaded are skipped. Downloads are rate-limited.

    Args:
        institutions: List of InstitutionInfo to download.
        output_dir: Directory to save PDFs into.
        rate_limit_seconds: Seconds to wait between downloads.
        dry_run: If True, log what would be downloaded without actually downloading.

    Returns:
        List of ScrapeResult for each institution processed.
    """
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    session = _get_session()
    results: list[ScrapeResult] = []
    downloaded_count = 0
    skipped_count = 0
    failed_count = 0

    total = len(institutions)

    for i, inst in enumerate(institutions, 1):
        identifier = str(inst.file_id)

        # Check idempotency via scrape_log
        if _is_already_scraped(SOURCE_NAME, identifier, inst.year):
            logger.debug(
                "[%d/%d] Skipping %s (%d) — already downloaded",
                i, total, inst.name, inst.year,
            )
            skipped_count += 1
            results.append(ScrapeResult(
                institution=inst,
                success=True,
                error="skipped (already downloaded)",
            ))
            continue

        # Build filename
        name_slug = slugify(inst.name)
        if not name_slug:
            name_slug = f"institution_{inst.file_id}"
        filename = f"{name_slug}_{inst.year}.pdf"
        pdf_path = output_dir / filename

        if dry_run:
            logger.info(
                "[%d/%d] Would download: %s (%d) -> %s",
                i, total, inst.name, inst.year, pdf_path,
            )
            results.append(ScrapeResult(institution=inst, success=True))
            continue

        # Log as 'running'
        now = datetime.now()
        save_scrape_log(ScrapeLogEntry(
            id=None,
            source=SOURCE_NAME,
            identifier=identifier,
            year=inst.year,
            status="running",
            pdf_path=str(pdf_path),
            error_message=None,
            created_at=now,
            updated_at=now,
        ))

        # Download PDF
        url = FILE_URL_TEMPLATE.format(id=inst.file_id)
        logger.info(
            "[%d/%d] Downloading: %s (%d) [file_id=%d]",
            i, total, inst.name, inst.year, inst.file_id,
        )

        try:
            resp = session.get(url, timeout=60)
            resp.raise_for_status()

            # Verify we got a PDF (check content type or magic bytes)
            content_type = resp.headers.get("Content-Type", "")
            if "pdf" not in content_type.lower() and not resp.content[:5] == b"%PDF-":
                raise ValueError(
                    f"Expected PDF but got Content-Type: {content_type}"
                )

            # Save PDF
            pdf_path.write_bytes(resp.content)

            # Log success
            now = datetime.now()
            save_scrape_log(ScrapeLogEntry(
                id=None,
                source=SOURCE_NAME,
                identifier=identifier,
                year=inst.year,
                status="success",
                pdf_path=str(pdf_path),
                error_message=None,
                created_at=now,
                updated_at=now,
            ))

            # Register institution as company with sector='public'
            _save_institution_as_company(inst.name, inst.year)

            downloaded_count += 1
            results.append(ScrapeResult(
                institution=inst,
                success=True,
                pdf_path=str(pdf_path),
            ))

            logger.info(
                "  Saved: %s (%d bytes)", pdf_path, len(resp.content),
            )

        except Exception as e:
            error_msg = str(e)
            logger.error("  Failed: %s", error_msg)

            # Log failure
            now = datetime.now()
            save_scrape_log(ScrapeLogEntry(
                id=None,
                source=SOURCE_NAME,
                identifier=identifier,
                year=inst.year,
                status="failed",
                pdf_path=str(pdf_path),
                error_message=error_msg,
                created_at=now,
                updated_at=now,
            ))

            failed_count += 1
            results.append(ScrapeResult(
                institution=inst,
                success=False,
                error=error_msg,
            ))

        # Rate limit between downloads
        if i < total:
            time.sleep(rate_limit_seconds)

    logger.info(
        "Done: %d downloaded, %d skipped, %d failed (out of %d total)",
        downloaded_count, skipped_count, failed_count, total,
    )

    return results


# --- Filtering ---

def filter_institutions(
    institutions: list[InstitutionInfo],
    ministry: Optional[str] = None,
    year: Optional[int] = None,
) -> list[InstitutionInfo]:
    """Filter institution list by ministry name and/or year.

    Ministry matching is case-insensitive substring match, and also
    works on the ASCII-transliterated form (so "Forsaetisraduneytid"
    matches "Forsætisráðuneyti").
    """
    filtered = institutions

    if year is not None:
        filtered = [inst for inst in filtered if inst.year == year]

    if ministry is not None:
        ministry_lower = ministry.lower()
        # Also create ASCII version for matching
        ministry_ascii = slugify(ministry)

        def _matches_ministry(inst: InstitutionInfo) -> bool:
            inst_ministry_lower = inst.ministry.lower()
            inst_ministry_ascii = slugify(inst.ministry)
            return (
                ministry_lower in inst_ministry_lower
                or ministry_ascii in inst_ministry_ascii
            )

        filtered = [inst for inst in filtered if _matches_ministry(inst)]

    return filtered


# --- Display ---

def print_institution_list(institutions: list[InstitutionInfo]) -> None:
    """Print a formatted table of institutions."""
    if not institutions:
        print("No institutions found.")
        print(
            "\nNote: If the listing page uses JavaScript rendering, "
            "the scraper may not be able to parse the HTML directly. "
            "Consider inspecting the page with browser developer tools."
        )
        return

    # Group by year, then by ministry
    from collections import defaultdict
    by_year: dict[int, list[InstitutionInfo]] = defaultdict(list)
    for inst in institutions:
        by_year[inst.year].append(inst)

    for year in sorted(by_year.keys(), reverse=True):
        year_insts = by_year[year]
        print(f"\n{'='*70}")
        print(f"  Year: {year}  ({len(year_insts)} institutions)")
        print(f"{'='*70}")

        current_ministry = None
        for inst in sorted(year_insts, key=lambda x: (x.ministry, x.name)):
            if inst.ministry != current_ministry:
                current_ministry = inst.ministry
                print(f"\n  {current_ministry}")
                print(f"  {'-' * len(current_ministry)}")
            print(f"    {inst.name}  [file_id={inst.file_id}]")

    print(f"\nTotal: {len(institutions)} institution entries")

    # Show unique ministry count
    ministries = set(inst.ministry for inst in institutions)
    years = set(inst.year for inst in institutions)
    print(f"Ministries: {len(ministries)}")
    print(f"Years: {sorted(years, reverse=True)}")


# --- CLI ---

def main():
    parser = argparse.ArgumentParser(
        description="Scrape Rikisreikningur (government annual accounts) PDFs"
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Just print the institution list, don't download anything",
    )
    parser.add_argument(
        "--ministry",
        type=str,
        default=None,
        help="Filter by ministry name (case-insensitive substring match, ASCII-safe)",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Filter by year (e.g. 2023)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be downloaded without actually downloading",
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
        help=f"Seconds between downloads (default: {DEFAULT_RATE_LIMIT})",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug-level logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Initialize database
    init_db()

    # Scrape the institution listing
    institutions = scrape_institution_list()

    if not institutions:
        logger.warning("No institutions found. See warnings above.")
        sys.exit(0)

    # Apply filters
    institutions = filter_institutions(
        institutions,
        ministry=args.ministry,
        year=args.year,
    )

    if not institutions:
        logger.warning("No institutions match the given filters.")
        sys.exit(0)

    if args.list_only:
        print_institution_list(institutions)
        sys.exit(0)

    # Download PDFs
    results = download_institution_pdfs(
        institutions=institutions,
        output_dir=args.output_dir,
        rate_limit_seconds=args.rate_limit,
        dry_run=args.dry_run,
    )

    # Summary
    success = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)

    if args.dry_run:
        print(f"\nDry run complete: {len(results)} institutions would be processed.")
    else:
        print(f"\nComplete: {success} succeeded, {failed} failed.")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
