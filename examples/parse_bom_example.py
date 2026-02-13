#!/usr/bin/env python3
"""Example script demonstrating BoM parser usage."""

from pathlib import Path
from pcb_cost_estimator.bom_parser import BomParser
from pcb_cost_estimator.models import ComponentCategory


def main():
    """Parse sample BoM files and display results."""
    parser = BomParser()

    # Find sample BoM files
    sample_dir = Path(__file__).parent.parent / "data" / "sample_boms"
    bom_files = [
        sample_dir / "example_bom.csv",
        sample_dir / "alternative_headers.tsv",
        sample_dir / "with_dnp_markers.csv",
    ]

    for bom_file in bom_files:
        if not bom_file.exists():
            print(f"⚠️  File not found: {bom_file}")
            continue

        print(f"\n{'='*80}")
        print(f"Parsing: {bom_file.name}")
        print(f"{'='*80}\n")

        # Parse the file
        result = parser.parse_file(bom_file)

        # Display results
        if result.success:
            print(f"✅ Successfully parsed {result.item_count} items")
            print(f"   Total rows processed: {result.total_rows_processed}")
        else:
            print(f"❌ Parsing failed with {len(result.errors)} error(s)")

        # Show warnings
        if result.warnings:
            print(f"\n⚠️  Warnings ({len(result.warnings)}):")
            for warning in result.warnings[:5]:  # Show first 5
                print(f"   - {warning}")
            if len(result.warnings) > 5:
                print(f"   ... and {len(result.warnings) - 5} more")

        # Show errors
        if result.errors:
            print(f"\n❌ Errors ({len(result.errors)}):")
            for error in result.errors:
                print(f"   - {error}")

        # Display sample items
        if result.items:
            print(f"\n📋 Sample Items (showing first 5):")
            for item in result.items[:5]:
                dnp_marker = " [DNP]" if item.dnp else ""
                print(f"   {item.reference_designator:10} "
                      f"Qty: {item.quantity:2} "
                      f"Cat: {item.category:15} "
                      f"{item.manufacturer_part_number or 'N/A':20}{dnp_marker}")

            if len(result.items) > 5:
                print(f"   ... and {len(result.items) - 5} more items")

            # Category breakdown
            categories = {}
            dnp_count = 0
            for item in result.items:
                categories[item.category] = categories.get(item.category, 0) + 1
                if item.dnp:
                    dnp_count += 1

            print(f"\n📊 Category Breakdown:")
            for category, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
                print(f"   {category:15}: {count:3} item(s)")

            if dnp_count > 0:
                print(f"\n⚠️  DNP/DNI items: {dnp_count}")

    print(f"\n{'='*80}\n")
    print("Example completed!")


if __name__ == "__main__":
    main()
