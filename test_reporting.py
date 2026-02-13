#!/usr/bin/env python3
"""
Quick test script to verify the reporting module functionality.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from pcb_cost_estimator.models import (
    CostEstimate,
    ComponentCostEstimate,
    AssemblyCost,
    OverheadCosts,
    ComponentCategory,
    PackageType,
    PriceBreak
)
from pcb_cost_estimator.reporting import CostReportGenerator

# Create a sample cost estimate for testing
def create_test_estimate():
    """Create a test CostEstimate with sample data."""

    # Create some sample components
    components = [
        ComponentCostEstimate(
            reference_designator="U1",
            quantity=1,
            category=ComponentCategory.IC,
            package_type=PackageType.QFN,
            unit_cost_low=8.50,
            unit_cost_typical=10.00,
            unit_cost_high=12.00,
            total_cost_low=8.50,
            total_cost_typical=10.00,
            total_cost_high=12.00,
            manufacturer="STMicroelectronics",
            manufacturer_part_number="STM32F103C8T6",
            description="ARM Cortex-M3 MCU",
            price_breaks=[
                PriceBreak(quantity=1, unit_price=12.00, total_price=12.00),
                PriceBreak(quantity=100, unit_price=10.00, total_price=10.00),
                PriceBreak(quantity=1000, unit_price=8.50, total_price=8.50),
                PriceBreak(quantity=10000, unit_price=7.50, total_price=7.50),
            ]
        ),
        ComponentCostEstimate(
            reference_designator="R1-R10",
            quantity=10,
            category=ComponentCategory.RESISTOR,
            package_type=PackageType.SMD_SMALL,
            unit_cost_low=0.005,
            unit_cost_typical=0.01,
            unit_cost_high=0.015,
            total_cost_low=0.05,
            total_cost_typical=0.10,
            total_cost_high=0.15,
            manufacturer="Yageo",
            manufacturer_part_number="RC0805FR-0710KL",
            description="10k 0805 1% Resistor",
            price_breaks=[
                PriceBreak(quantity=1, unit_price=0.015, total_price=0.15),
                PriceBreak(quantity=100, unit_price=0.01, total_price=0.10),
                PriceBreak(quantity=1000, unit_price=0.005, total_price=0.05),
                PriceBreak(quantity=10000, unit_price=0.003, total_price=0.03),
            ]
        ),
        ComponentCostEstimate(
            reference_designator="C1-C20",
            quantity=20,
            category=ComponentCategory.CAPACITOR,
            package_type=PackageType.SMD_SMALL,
            unit_cost_low=0.01,
            unit_cost_typical=0.02,
            unit_cost_high=0.03,
            total_cost_low=0.20,
            total_cost_typical=0.40,
            total_cost_high=0.60,
            manufacturer="Murata",
            manufacturer_part_number="GRM21BR61C106KE15L",
            description="10uF 16V X5R 0805",
            price_breaks=[
                PriceBreak(quantity=1, unit_price=0.03, total_price=0.60),
                PriceBreak(quantity=100, unit_price=0.02, total_price=0.40),
                PriceBreak(quantity=1000, unit_price=0.01, total_price=0.20),
                PriceBreak(quantity=10000, unit_price=0.008, total_price=0.16),
            ]
        ),
        ComponentCostEstimate(
            reference_designator="J1",
            quantity=1,
            category=ComponentCategory.CONNECTOR,
            package_type=PackageType.CONNECTOR,
            unit_cost_low=0.80,
            unit_cost_typical=1.00,
            unit_cost_high=1.20,
            total_cost_low=0.80,
            total_cost_typical=1.00,
            total_cost_high=1.20,
            manufacturer="Molex",
            manufacturer_part_number="22-23-2021",
            description="2-pin header connector",
            price_breaks=[
                PriceBreak(quantity=1, unit_price=1.20, total_price=1.20),
                PriceBreak(quantity=100, unit_price=1.00, total_price=1.00),
                PriceBreak(quantity=1000, unit_price=0.80, total_price=0.80),
                PriceBreak(quantity=10000, unit_price=0.70, total_price=0.70),
            ]
        ),
    ]

    # Assembly cost
    assembly = AssemblyCost(
        total_components=32,
        unique_components=4,
        smd_small_count=30,
        qfn_count=1,
        connector_count=1,
        setup_cost=50.00,
        placement_cost_per_board=2.50,
        total_assembly_cost_per_board=2.50
    )

    # Overhead costs
    overhead = OverheadCosts(
        nre_cost=100.00,
        procurement_overhead=0.50,
        supply_chain_risk_factor=1.1,
        markup_percentage=20.0,
        total_overhead=1.50
    )

    # Total costs
    total_comp_low = sum(c.total_cost_low for c in components)
    total_comp_typical = sum(c.total_cost_typical for c in components)
    total_comp_high = sum(c.total_cost_high for c in components)

    cost_estimate = CostEstimate(
        file_path="test_bom.csv",
        currency="USD",
        component_costs=components,
        assembly_cost=assembly,
        overhead_costs=overhead,
        total_component_cost_low=total_comp_low,
        total_component_cost_typical=total_comp_typical,
        total_component_cost_high=total_comp_high,
        total_cost_per_board_low=total_comp_low + assembly.total_assembly_cost_per_board + overhead.total_overhead,
        total_cost_per_board_typical=total_comp_typical + assembly.total_assembly_cost_per_board + overhead.total_overhead,
        total_cost_per_board_high=total_comp_high + assembly.total_assembly_cost_per_board + overhead.total_overhead,
        warnings=[
            "Component U1 (STM32F103C8T6) may have long lead times",
            "High-cost component detected: U1 at $10.00"
        ],
        notes=[
            "LLM enrichment was used for 1 unknown component",
            "Price estimates based on typical market rates"
        ]
    )

    return cost_estimate


def test_cli_table():
    """Test CLI table generation."""
    print("\n" + "="*80)
    print("TEST 1: CLI Table Format")
    print("="*80 + "\n")

    estimate = create_test_estimate()
    generator = CostReportGenerator(estimate)
    generator.generate_cli_table()

    print("\n✓ CLI table test completed\n")


def test_json_report():
    """Test JSON report generation."""
    print("\n" + "="*80)
    print("TEST 2: JSON Report Format")
    print("="*80 + "\n")

    estimate = create_test_estimate()
    generator = CostReportGenerator(estimate)

    output_path = Path("/tmp/test_cost_report.json")
    report = generator.generate_json_report(output_path)

    print(f"✓ JSON report generated: {output_path}")
    print(f"  - Executive summary: {report['executive_summary']['total_components']} components")
    print(f"  - Volume tiers: {len(report['volume_tier_comparison']['tiers'])} tiers")
    print(f"  - Cost drivers: {len(report['top_cost_drivers'])} items")
    print(f"  - Categories: {len(report['cost_breakdown_by_category'])} categories")
    print()


def test_csv_export():
    """Test CSV export."""
    print("\n" + "="*80)
    print("TEST 3: CSV Export Format")
    print("="*80 + "\n")

    estimate = create_test_estimate()
    generator = CostReportGenerator(estimate)

    output_path = Path("/tmp/test_cost_report.csv")
    generator.generate_csv_export(output_path)

    print(f"✓ CSV export generated: {output_path}")

    # Show first few lines
    with open(output_path, 'r') as f:
        lines = f.readlines()[:5]
    print(f"  First {len(lines)} lines:")
    for line in lines:
        print(f"    {line.rstrip()}")
    print()


def test_markdown_report():
    """Test Markdown report generation."""
    print("\n" + "="*80)
    print("TEST 4: Markdown Report Format")
    print("="*80 + "\n")

    estimate = create_test_estimate()
    generator = CostReportGenerator(estimate)

    output_path = Path("/tmp/test_cost_report.md")
    generator.generate_markdown_report(output_path)

    print(f"✓ Markdown report generated: {output_path}")

    # Show first few lines
    with open(output_path, 'r') as f:
        lines = f.readlines()[:10]
    print(f"  First {len(lines)} lines:")
    for line in lines:
        print(f"    {line.rstrip()}")
    print()


if __name__ == "__main__":
    print("\n" + "="*80)
    print("PCB Cost Estimator - Reporting Module Test Suite")
    print("="*80)

    try:
        test_cli_table()
        test_json_report()
        test_csv_export()
        test_markdown_report()

        print("\n" + "="*80)
        print("ALL TESTS PASSED ✓")
        print("="*80 + "\n")

        print("Generated files:")
        print("  - /tmp/test_cost_report.json")
        print("  - /tmp/test_cost_report.csv")
        print("  - /tmp/test_cost_report.md")
        print()

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
