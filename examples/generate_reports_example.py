"""
Example script demonstrating all report generation formats.

This example shows how to use the reporting module to generate
cost reports in multiple formats: CLI table, JSON, CSV, and Markdown.
"""

from pathlib import Path
import sys

# Add src to path if running directly
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pcb_cost_estimator.bom_parser import BomParser
from pcb_cost_estimator.cost_estimator import CostEstimator
from pcb_cost_estimator.reporting import generate_report
from pcb_cost_estimator.config import load_cost_model_config


def main():
    """Run report generation example."""
    # Parse a sample BOM
    bom_file = Path(__file__).parent.parent / "data" / "sample_boms" / "example_bom.csv"

    if not bom_file.exists():
        print(f"Error: Sample BOM file not found at {bom_file}")
        return

    print(f"Parsing BOM file: {bom_file}")
    parser = BomParser()
    bom_result = parser.parse_file(bom_file)

    if not bom_result.success:
        print(f"Error parsing BOM: {bom_result.errors}")
        return

    print(f"Successfully parsed {len(bom_result.items)} components")

    # Load cost model and estimate costs
    cost_config = load_cost_model_config()
    estimator = CostEstimator(cost_config)

    print("Estimating costs...")
    cost_estimate = estimator.estimate_bom_cost(bom_result, board_quantity=1)

    print(f"\nTotal cost per board: ${cost_estimate.total_cost_per_board_typical:.2f}")

    # Create output directory
    output_dir = Path(__file__).parent.parent / "output" / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 80)
    print("GENERATING REPORTS")
    print("=" * 80 + "\n")

    # 1. CLI Table (displayed directly)
    print("1. CLI Table Format (displayed below):")
    print("-" * 80)
    generate_report(cost_estimate, format='table')

    # 2. JSON Report
    json_path = output_dir / "cost_report.json"
    print(f"\n2. JSON Report")
    print(f"   Generating: {json_path}")
    json_report = generate_report(cost_estimate, format='json', output_path=json_path)
    print(f"   ✓ Generated with {len(json_report['itemized_components'])} components")
    print(f"   ✓ {len(json_report['volume_tier_comparison']['tiers'])} volume tiers")

    # 3. CSV Export
    csv_path = output_dir / "cost_report.csv"
    print(f"\n3. CSV Export")
    print(f"   Generating: {csv_path}")
    generate_report(cost_estimate, format='csv', output_path=csv_path)
    print(f"   ✓ Generated - import into Excel/Google Sheets")

    # 4. Markdown Report
    md_path = output_dir / "cost_report.md"
    print(f"\n4. Markdown Report")
    print(f"   Generating: {md_path}")
    generate_report(cost_estimate, format='markdown', output_path=md_path)
    print(f"   ✓ Generated - human-readable documentation")

    print("\n" + "=" * 80)
    print("REPORT GENERATION COMPLETE")
    print("=" * 80)
    print(f"\nAll reports saved to: {output_dir}")
    print("\nGenerated files:")
    print(f"  - {json_path.name} (detailed JSON breakdown)")
    print(f"  - {csv_path.name} (spreadsheet-importable)")
    print(f"  - {md_path.name} (human-readable documentation)")
    print()


if __name__ == "__main__":
    main()
