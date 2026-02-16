#!/usr/bin/env python3
"""
CLI script to extract financial data from annual report PDFs.

Usage:
    python scripts/extract_pdf.py <pdf_path> [--kennitala <kt>]
    python scripts/extract_pdf.py --batch <dir> [--source-type rikisreikningur]

Example:
    python scripts/extract_pdf.py pdfs/5501692829_2023.pdf
    python scripts/extract_pdf.py pdfs/marel_2023.pdf --kennitala 5501692829
    python scripts/extract_pdf.py --batch pdfs/
    python scripts/extract_pdf.py --batch pdfs/rikis/ --source-type rikisreikningur
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.extractor import extract_from_pdf, extract_from_pdf_v2, extract_batch, ExtractedData, ExtractedDataV2
from src.database import get_or_create_company, save_annual_report


def format_isk(amount: int) -> str:
    """Format ISK amount with thousand separators."""
    return f"{amount:,.0f}".replace(",", ".") + " kr"


def main():
    parser = argparse.ArgumentParser(
        description="Extract financial data from Icelandic annual report PDFs"
    )
    parser.add_argument("pdf_path", type=Path, nargs="?", help="Path to the PDF file")
    parser.add_argument(
        "--kennitala", "-k",
        help="Company kennitala (if not found in PDF)"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Extract and display data without saving to database"
    )
    parser.add_argument(
        "--batch", "-b",
        type=Path,
        metavar="DIR",
        help="Process all PDFs in directory (batch mode)"
    )
    parser.add_argument(
        "--source-type", "-s",
        default="pdf",
        help="Source type label for batch mode (default: pdf)"
    )
    parser.add_argument(
        "--pattern",
        default="*.pdf",
        help="Glob pattern for batch mode (default: *.pdf)"
    )
    parser.add_argument(
        "--no-skip",
        action="store_true",
        help="Don't skip already-extracted PDFs in batch mode"
    )

    args = parser.parse_args()

    # Batch mode
    if args.batch:
        if not args.batch.is_dir():
            print(f"Error: Not a directory: {args.batch}")
            sys.exit(1)

        print(f"Batch processing: {args.batch}")
        print(f"Source type: {args.source_type}")
        print(f"Pattern: {args.pattern}")
        print("=" * 50)

        results = extract_batch(
            pdf_dir=args.batch,
            pattern=args.pattern,
            skip_extracted=not args.no_skip,
            source_type=args.source_type,
        )

        if results:
            print(f"\nSuccessfully extracted {len(results)} reports")
        sys.exit(0)

    # Single file mode
    if not args.pdf_path:
        parser.error("pdf_path is required when not using --batch")

    if not args.pdf_path.exists():
        print(f"Error: File not found: {args.pdf_path}")
        sys.exit(1)

    print(f"Processing: {args.pdf_path}")
    print("-" * 50)

    try:
        data: ExtractedDataV2 = extract_from_pdf_v2(args.pdf_path, source_type=args.source_type)

        # Override kennitala if provided
        if args.kennitala:
            data = ExtractedDataV2(
                company_name=data.company_name,
                kennitala=args.kennitala,
                year=data.year,
                launakostnadur=data.launakostnadur,
                starfsmenn=data.starfsmenn,
                tekjur=data.tekjur,
                confidence=data.confidence,
                raw_text_snippet=data.raw_text_snippet,
                hagnadur=data.hagnadur,
                rekstrarkostnadur=data.rekstrarkostnadur,
                eiginfjarhlufall=data.eiginfjarhlufall,
                source_type=data.source_type,
            )

        # Calculate average salary
        avg_salary = int(data.launakostnadur / data.starfsmenn) if data.starfsmenn > 0 else 0
        monthly_salary = avg_salary // 12

        # Display results
        print(f"Company:          {data.company_name}")
        print(f"Kennitala:        {data.kennitala or 'Not found'}")
        print(f"Year:             {data.year}")
        print(f"Wage Costs:       {format_isk(data.launakostnadur)}")
        print(f"Employees:        {data.starfsmenn:.1f}")
        if data.tekjur:
            print(f"Revenue:          {format_isk(data.tekjur)}")
        if data.hagnadur is not None:
            print(f"Net Profit:       {format_isk(data.hagnadur)}")
        if data.rekstrarkostnadur is not None:
            print(f"Operating Exp:    {format_isk(data.rekstrarkostnadur)}")
        if data.eiginfjarhlufall is not None:
            print(f"Equity Ratio:     {data.eiginfjarhlufall:.1%}")
        print(f"Confidence:       {data.confidence:.0%}")
        print("-" * 50)
        print(f"Avg Annual Salary:  {format_isk(avg_salary)}")
        print(f"Avg Monthly Salary: {format_isk(monthly_salary)}")

        if args.dry_run:
            print("\n[Dry run - not saved to database]")
        else:
            if not data.kennitala:
                print("\nWarning: No kennitala found. Use --kennitala to specify.")
                print("Data not saved.")
                sys.exit(1)

            # Save to database
            company_id = get_or_create_company(
                kennitala=data.kennitala,
                name=data.company_name
            )

            report_id = save_annual_report(
                company_id=company_id,
                year=data.year,
                launakostnadur=data.launakostnadur,
                starfsmenn=data.starfsmenn,
                tekjur=data.tekjur,
                source_pdf=str(args.pdf_path),
                hagnadur=data.hagnadur,
                rekstrarkostnadur=data.rekstrarkostnadur,
                eiginfjarhlufall=data.eiginfjarhlufall,
                source_type=data.source_type,
                confidence=data.confidence,
            )

            print(f"\nSaved to database (company_id={company_id}, report_id={report_id})")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
