"""
Launatrausti data pipeline orchestrator.

Runs the full data pipeline end-to-end, or individual stages:

  Stage 1: Cleanup sample data (flag + optionally delete)
  Stage 2: Download VR survey PDFs
  Stage 3: Parse VR surveys into database
  Stage 4: Scrape Skatturinn annual report PDFs (for companies in DB)
  Stage 5: Scrape Rikisreikningur government institution PDFs
  Stage 6: Extract all downloaded PDFs (batch mode, Claude API)
  Stage 7: Print summary statistics

Usage:
    python scripts/run_pipeline.py                  # Run all stages
    python scripts/run_pipeline.py --dry-run        # Dry run (no side effects)
    python scripts/run_pipeline.py --stage 7        # Run only stage 7
    python scripts/run_pipeline.py --skip-scrape    # Skip stages 4 and 5
    python scripts/run_pipeline.py --delete-sample  # Delete sample data in stage 1
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

# Project root: one level up from scripts/
PROJECT_ROOT = Path(__file__).resolve().parent.parent

TOTAL_STAGES = 11


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def banner(stage: int, description: str) -> None:
    """Print a visible stage header."""
    print()
    print("=" * 70)
    print(f"  [STAGE {stage}/{TOTAL_STAGES}] {description}")
    print("=" * 70)
    print()


def run_script(args: list[str], *, verbose: bool = False) -> subprocess.CompletedProcess:
    """Run a Python script as a subprocess and return the result.

    Uses sys.executable to ensure the correct interpreter is used.
    Streams output to stdout/stderr in real time.
    """
    cmd = [sys.executable] + args
    if verbose:
        print(f"  $ {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        # Let child process inherit stdout/stderr so output streams live
        stdout=None,
        stderr=None,
    )
    return result


def format_elapsed(seconds: float) -> str:
    """Format elapsed time in a human-readable way."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.1f}s"


# ---------------------------------------------------------------------------
# Stage functions
# ---------------------------------------------------------------------------

def run_stage_1(dry_run: bool = False, delete_sample: bool = False, verbose: bool = False) -> bool:
    """Stage 1: Cleanup sample data (flag + optionally delete)."""
    banner(1, "Cleanup sample data")

    args = ["scripts/cleanup_sample_data.py"]

    if dry_run:
        args.append("--dry-run")
    elif delete_sample:
        args.append("--delete")
    else:
        args.append("--flag-only")

    result = run_script(args, verbose=verbose)

    if result.returncode != 0:
        print(f"  [ERROR] Stage 1 exited with code {result.returncode}")
        return False

    print("  [OK] Sample data cleanup complete.")
    return True


def run_stage_2(dry_run: bool = False, verbose: bool = False) -> bool:
    """Stage 2: Download VR survey PDFs."""
    banner(2, "Download VR survey PDFs")

    args = ["scripts/parse_vr_surveys.py", "--download-only"]

    result = run_script(args, verbose=verbose)

    if result.returncode != 0:
        print(f"  [ERROR] Stage 2 exited with code {result.returncode}")
        return False

    print("  [OK] VR PDF download complete.")
    return True


def run_stage_3(dry_run: bool = False, verbose: bool = False) -> bool:
    """Stage 3: Parse VR surveys into database."""
    banner(3, "Parse VR surveys into database")

    args = ["scripts/parse_vr_surveys.py", "--all"]
    if dry_run:
        args.append("--dry-run")

    result = run_script(args, verbose=verbose)

    if result.returncode != 0:
        print(f"  [ERROR] Stage 3 exited with code {result.returncode}")
        return False

    print("  [OK] VR survey parsing complete.")
    return True


def run_stage_4(dry_run: bool = False, verbose: bool = False) -> bool:
    """Stage 4: Scrape Skatturinn annual report PDFs (for companies in DB)."""
    banner(4, "Scrape Skatturinn annual report PDFs")

    args = ["scripts/scrape_arsreikningar.py", "--from-db"]
    if dry_run:
        args.append("--dry-run")

    result = run_script(args, verbose=verbose)

    if result.returncode != 0:
        print(f"  [ERROR] Stage 4 exited with code {result.returncode}")
        return False

    print("  [OK] Skatturinn scraping complete.")
    return True


def run_stage_5(dry_run: bool = False, verbose: bool = False) -> bool:
    """Stage 5: Scrape Rikisreikningur government institution PDFs."""
    banner(5, "Scrape Rikisreikningur government institution PDFs")

    args = ["scripts/scrape_rikisreikningur.py"]
    if dry_run:
        args.append("--dry-run")

    result = run_script(args, verbose=verbose)

    if result.returncode != 0:
        print(f"  [ERROR] Stage 5 exited with code {result.returncode}")
        return False

    print("  [OK] Rikisreikningur scraping complete.")
    return True


def run_stage_6(dry_run: bool = False, verbose: bool = False) -> bool:
    """Stage 6: Extract all downloaded PDFs (batch mode, Claude API)."""
    banner(6, "Extract financial data from downloaded PDFs")

    pdfs_dir = PROJECT_ROOT / "pdfs"

    if not pdfs_dir.is_dir():
        print(f"  [SKIP] No pdfs/ directory found at {pdfs_dir}")
        print("  Run stages 2-5 first to download PDFs.")
        return True  # Not a failure, just nothing to do

    args = ["scripts/extract_pdf.py", "--batch", "pdfs/"]
    if dry_run:
        args.append("--dry-run")

    result = run_script(args, verbose=verbose)

    if result.returncode != 0:
        print(f"  [ERROR] Stage 6 exited with code {result.returncode}")
        return False

    print("  [OK] PDF extraction complete.")
    return True


def run_stage_8(dry_run: bool = False, verbose: bool = False) -> bool:
    """Stage 8: Scrape job listings from Alfred.is and Starfatorg."""
    banner(8, "Scrape job listings (Alfred + Starfatorg)")

    args = ["scripts/scrape_jobs.py"]
    if dry_run:
        args.append("--dry-run")

    result = run_script(args, verbose=verbose)

    if result.returncode != 0:
        print(f"  [ERROR] Stage 8 exited with code {result.returncode}")
        return False

    print("  [OK] Job scraping complete.")
    return True


def run_stage_9(dry_run: bool = False, verbose: bool = False) -> bool:
    """Stage 9: Extract structured fields from job descriptions (Claude API)."""
    banner(9, "Extract job fields via AI")

    args = ["scripts/extract_jobs.py"]
    if dry_run:
        args.append("--dry-run")

    result = run_script(args, verbose=verbose)

    if result.returncode != 0:
        print(f"  [ERROR] Stage 9 exited with code {result.returncode}")
        return False

    print("  [OK] Job field extraction complete.")
    return True


def run_stage_10(dry_run: bool = False, verbose: bool = False) -> bool:
    """Stage 10: Match job employers to companies in database."""
    banner(10, "Match job employers to companies")

    if dry_run:
        print("  [SKIP] Dry run — skipping company matching")
        return True

    args = ["scripts/match_companies.py"]
    result = run_script(args, verbose=verbose)

    if result.returncode != 0:
        print(f"  [ERROR] Stage 10 exited with code {result.returncode}")
        return False

    print("  [OK] Company matching complete.")
    return True


def run_stage_11(dry_run: bool = False, verbose: bool = False) -> bool:
    """Stage 11: Pre-compute salary estimates for job listings."""
    banner(11, "Estimate salaries for job listings")

    if dry_run:
        print("  [SKIP] Dry run — skipping salary estimation")
        return True

    args = ["scripts/estimate_salaries.py"]
    result = run_script(args, verbose=verbose)

    if result.returncode != 0:
        print(f"  [ERROR] Stage 11 exited with code {result.returncode}")
        return False

    print("  [OK] Salary estimation complete.")
    return True


def run_stage_7(verbose: bool = False) -> bool:
    """Stage 7: Print summary statistics from database."""
    banner(7, "Platform summary statistics")

    try:
        # Import database directly for stats (safe, no side effects)
        sys.path.insert(0, str(PROJECT_ROOT))
        from src.database import get_platform_stats

        stats = get_platform_stats()

        print(f"  Companies:          {stats['total_companies']:>8,}")
        print(f"  Annual reports:     {stats['total_reports']:>8,}")
        print(f"  VR salary surveys:  {stats['total_vr_surveys']:>8,}")
        print(f"  Scrape log entries: {stats['total_scrape_entries']:>8,}")
        print(f"  Distinct sources:   {stats['total_sources']:>8,}")
        print(f"  Report PDF sources: {stats['report_sources']:>8,}")

        yr_min, yr_max = stats["year_range"]
        if yr_min is not None:
            print(f"  Year range:         {yr_min} - {yr_max}")
        else:
            print("  Year range:         (no data)")

        print()
        print("  [OK] Stats printed.")
        return True

    except Exception as e:
        print(f"  [ERROR] Could not load stats: {e}")
        return False


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline(
    stage: int | None = None,
    dry_run: bool = False,
    skip_scrape: bool = False,
    skip_jobs: bool = False,
    delete_sample: bool = False,
    verbose: bool = False,
) -> None:
    """Run the full pipeline or a single stage."""

    stage_functions = {
        1: lambda: run_stage_1(dry_run=dry_run, delete_sample=delete_sample, verbose=verbose),
        2: lambda: run_stage_2(dry_run=dry_run, verbose=verbose),
        3: lambda: run_stage_3(dry_run=dry_run, verbose=verbose),
        4: lambda: run_stage_4(dry_run=dry_run, verbose=verbose),
        5: lambda: run_stage_5(dry_run=dry_run, verbose=verbose),
        6: lambda: run_stage_6(dry_run=dry_run, verbose=verbose),
        7: lambda: run_stage_7(verbose=verbose),
        8: lambda: run_stage_8(dry_run=dry_run, verbose=verbose),
        9: lambda: run_stage_9(dry_run=dry_run, verbose=verbose),
        10: lambda: run_stage_10(dry_run=dry_run, verbose=verbose),
        11: lambda: run_stage_11(dry_run=dry_run, verbose=verbose),
    }

    # Determine which stages to run
    if stage is not None:
        stages_to_run = [stage]
    else:
        stages_to_run = list(range(1, TOTAL_STAGES + 1))
        if skip_scrape:
            stages_to_run = [s for s in stages_to_run if s not in (4, 5)]

    if skip_jobs:
        stages_to_run = [s for s in stages_to_run if s not in (8, 9, 10, 11)]

    if dry_run:
        print("*** DRY RUN MODE -- no data will be modified ***")

    pipeline_start = time.time()
    results: dict[int, tuple[bool, float]] = {}
    errors: list[int] = []

    for s in stages_to_run:
        stage_start = time.time()
        try:
            success = stage_functions[s]()
        except Exception as e:
            print(f"  [EXCEPTION] Stage {s} raised: {e}")
            success = False

        elapsed = time.time() - stage_start
        results[s] = (success, elapsed)

        if not success:
            errors.append(s)

        print(f"  Time: {format_elapsed(elapsed)}")

    # ---------------------------------------------------------------------------
    # Final summary
    # ---------------------------------------------------------------------------
    total_elapsed = time.time() - pipeline_start

    print()
    print("=" * 70)
    print("  PIPELINE SUMMARY")
    print("=" * 70)

    for s in stages_to_run:
        success, elapsed = results[s]
        status = "OK" if success else "FAILED"
        print(f"  Stage {s}: {status:>6}  ({format_elapsed(elapsed)})")

    print(f"\n  Total time: {format_elapsed(total_elapsed)}")

    if errors:
        print(f"\n  Errors in stage(s): {', '.join(str(e) for e in errors)}")
    else:
        print("\n  All stages completed successfully.")

    print()

    # Exit with non-zero if any stage failed
    if errors:
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Launatrausti data pipeline orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Stages:
  1  Cleanup sample data (flag + optionally delete)
  2  Download VR survey PDFs
  3  Parse VR surveys into database
  4  Scrape Skatturinn annual report PDFs
  5  Scrape Rikisreikningur government institution PDFs
  6  Extract financial data from all downloaded PDFs
  7  Print summary statistics
  8  Scrape job listings (Alfred + Starfatorg)
  9  Extract job fields via AI (Claude API)
  10 Match job employers to companies
  11 Estimate salaries for job listings

Examples:
  %(prog)s                     Run all stages
  %(prog)s --dry-run           Run all stages without side effects
  %(prog)s --stage 7           Print current database stats
  %(prog)s --skip-scrape       Skip web scraping (stages 4 & 5)
  %(prog)s --skip-jobs         Skip job stages (8-11)
  %(prog)s --delete-sample     Delete sample data in stage 1
        """,
    )

    parser.add_argument(
        "--stage",
        type=int,
        choices=range(1, TOTAL_STAGES + 1),
        metavar="N",
        help=f"Run only stage N (1-{TOTAL_STAGES})",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Run all stages in dry-run mode (no side effects)",
    )
    parser.add_argument(
        "--skip-scrape",
        action="store_true",
        help="Skip stages 4 and 5 (web scraping)",
    )
    parser.add_argument(
        "--skip-jobs",
        action="store_true",
        help="Skip stages 8-11 (job scraping and processing)",
    )
    parser.add_argument(
        "--delete-sample",
        action="store_true",
        help="Actually delete sample data in stage 1 (default: only flag)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print detailed output including subprocess commands",
    )

    args = parser.parse_args()

    run_pipeline(
        stage=args.stage,
        dry_run=args.dry_run,
        skip_scrape=args.skip_scrape,
        skip_jobs=args.skip_jobs,
        delete_sample=args.delete_sample,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
