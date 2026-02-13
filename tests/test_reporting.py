"""Tests for the reporting module."""

import json
import tempfile
from pathlib import Path

import pytest

from pcb_cost_estimator.models import (
    AssemblyCost,
    ComponentCategory,
    ComponentCostEstimate,
    CostEstimate,
    OverheadCosts,
    PackageType,
    PriceBreak,
)
from pcb_cost_estimator.reporting import CostReportGenerator, generate_report


@pytest.fixture
def sample_cost_estimate():
    """Create a sample cost estimate for testing."""
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
            ],
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
            ],
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
            ],
        ),
    ]

    assembly = AssemblyCost(
        total_components=31,
        unique_components=3,
        smd_small_count=30,
        qfn_count=1,
        setup_cost=50.00,
        placement_cost_per_board=2.50,
        total_assembly_cost_per_board=2.50,
    )

    overhead = OverheadCosts(
        nre_cost=100.00,
        procurement_overhead=0.50,
        supply_chain_risk_factor=1.1,
        markup_percentage=20.0,
        total_overhead=1.50,
    )

    total_comp_low = sum(c.total_cost_low for c in components)
    total_comp_typical = sum(c.total_cost_typical for c in components)
    total_comp_high = sum(c.total_cost_high for c in components)

    return CostEstimate(
        file_path="test_bom.csv",
        currency="USD",
        component_costs=components,
        assembly_cost=assembly,
        overhead_costs=overhead,
        total_component_cost_low=total_comp_low,
        total_component_cost_typical=total_comp_typical,
        total_component_cost_high=total_comp_high,
        total_cost_per_board_low=total_comp_low
        + assembly.total_assembly_cost_per_board
        + overhead.total_overhead,
        total_cost_per_board_typical=total_comp_typical
        + assembly.total_assembly_cost_per_board
        + overhead.total_overhead,
        total_cost_per_board_high=total_comp_high
        + assembly.total_assembly_cost_per_board
        + overhead.total_overhead,
        warnings=[
            "Component U1 (STM32F103C8T6) may have long lead times",
            "High-cost component detected: U1 at $10.00",
        ],
        notes=["LLM enrichment was used for 1 unknown component"],
    )


def test_cost_report_generator_init(sample_cost_estimate):
    """Test CostReportGenerator initialization."""
    generator = CostReportGenerator(sample_cost_estimate)
    assert generator.cost_estimate == sample_cost_estimate
    assert generator.VOLUME_TIERS == [1, 100, 1000, 10000]


def test_calculate_volume_costs(sample_cost_estimate):
    """Test volume cost calculation."""
    generator = CostReportGenerator(sample_cost_estimate)
    volume_costs = generator._calculate_volume_costs()

    assert len(volume_costs) == 4
    assert all(vol in volume_costs for vol in [1, 100, 1000, 10000])

    # Check structure
    for vol, costs in volume_costs.items():
        assert "components" in costs
        assert "assembly" in costs
        assert "overhead" in costs
        assert "total" in costs
        assert costs["total"] > 0

    # Verify that higher volumes have lower per-unit costs
    assert volume_costs[10000]["components"] <= volume_costs[1000]["components"]
    assert volume_costs[1000]["components"] <= volume_costs[100]["components"]


def test_calculate_cost_by_category(sample_cost_estimate):
    """Test cost breakdown by category."""
    generator = CostReportGenerator(sample_cost_estimate)
    category_costs = generator._calculate_cost_by_category()

    assert len(category_costs) > 0
    assert all("category" in cat for cat in category_costs)
    assert all("count" in cat for cat in category_costs)
    assert all("total_cost" in cat for cat in category_costs)
    assert all("percentage" in cat for cat in category_costs)

    # Verify percentages sum to ~100%
    total_pct = sum(cat["percentage"] for cat in category_costs)
    assert 99.0 < total_pct < 101.0

    # Verify sorted by cost descending
    costs = [cat["total_cost"] for cat in category_costs]
    assert costs == sorted(costs, reverse=True)


def test_get_top_cost_drivers(sample_cost_estimate):
    """Test top cost drivers identification."""
    generator = CostReportGenerator(sample_cost_estimate)
    drivers = generator._get_top_cost_drivers(limit=10)

    assert len(drivers) <= 10
    assert len(drivers) == len(sample_cost_estimate.component_costs)

    # Verify structure
    for driver in drivers:
        assert "reference" in driver
        assert "total_cost" in driver
        assert "percentage" in driver
        assert driver["total_cost"] >= 0

    # Verify sorted by cost descending
    costs = [d["total_cost"] for d in drivers]
    assert costs == sorted(costs, reverse=True)

    # Verify most expensive is U1
    assert drivers[0]["reference"] == "U1"
    assert drivers[0]["total_cost"] == 10.00


def test_extract_risk_flags(sample_cost_estimate):
    """Test risk flag extraction."""
    generator = CostReportGenerator(sample_cost_estimate)
    risks = generator._extract_risk_flags()

    assert "obsolescence" in risks
    assert "high_cost" in risks
    assert "single_source" in risks
    assert "price_warnings" in risks
    assert "other" in risks

    # Should have at least high-cost risk for U1
    assert len(risks["high_cost"]) > 0
    assert any(r["component"] == "U1" for r in risks["high_cost"])


def test_get_assembly_breakdown(sample_cost_estimate):
    """Test assembly breakdown."""
    generator = CostReportGenerator(sample_cost_estimate)
    breakdown = generator._get_assembly_breakdown()

    assert len(breakdown) > 0
    assert all("package_type" in item for item in breakdown)
    assert all("count" in item for item in breakdown)
    assert all("percentage" in item for item in breakdown)

    # Verify counts match assembly cost
    total_count = sum(item["count"] for item in breakdown)
    assert total_count == sample_cost_estimate.assembly_cost.total_components


def test_generate_json_report(sample_cost_estimate):
    """Test JSON report generation."""
    generator = CostReportGenerator(sample_cost_estimate)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_report.json"
        report = generator.generate_json_report(output_path)

        # Verify file was created
        assert output_path.exists()

        # Verify report structure
        assert "metadata" in report
        assert "executive_summary" in report
        assert "volume_tier_comparison" in report
        assert "cost_breakdown_by_category" in report
        assert "top_cost_drivers" in report
        assert "assembly_breakdown" in report
        assert "overhead_costs" in report
        assert "risk_assessment" in report
        assert "itemized_components" in report
        assert "warnings" in report
        assert "notes" in report
        assert "assumptions" in report

        # Verify metadata
        assert report["metadata"]["currency"] == "USD"

        # Verify executive summary
        assert report["executive_summary"]["total_components"] == 3
        assert "cost_per_board" in report["executive_summary"]
        assert "confidence_interval" in report["executive_summary"]

        # Verify volume tiers
        assert len(report["volume_tier_comparison"]["tiers"]) == 4

        # Verify itemized components
        assert len(report["itemized_components"]) == 3

        # Verify file content matches return value
        with open(output_path, "r") as f:
            file_content = json.load(f)
        assert file_content == report


def test_generate_csv_export(sample_cost_estimate):
    """Test CSV export generation."""
    generator = CostReportGenerator(sample_cost_estimate)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_report.csv"
        generator.generate_csv_export(output_path)

        # Verify file was created
        assert output_path.exists()

        # Read and verify content
        with open(output_path, "r") as f:
            content = f.read()

        # Check for expected headers
        assert "Reference Designator" in content
        assert "Quantity" in content
        assert "Category" in content
        assert "MPN" in content
        assert "Unit Cost" in content
        assert "Total Cost" in content

        # Check for component data
        assert "U1" in content
        assert "STM32F103C8T6" in content
        assert "R1-R10" in content

        # Check for summary section
        assert "SUMMARY" in content
        assert "VOLUME TIER PRICING" in content


def test_generate_markdown_report(sample_cost_estimate):
    """Test Markdown report generation."""
    generator = CostReportGenerator(sample_cost_estimate)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_report.md"
        generator.generate_markdown_report(output_path)

        # Verify file was created
        assert output_path.exists()

        # Read and verify content
        with open(output_path, "r") as f:
            content = f.read()

        # Check for expected sections
        assert "# PCB Cost Estimate Report" in content
        assert "## Executive Summary" in content
        assert "## Volume Tier Comparison" in content
        assert "## Cost Breakdown by Category" in content
        assert "## Top 10 Cost Drivers" in content
        assert "## Assembly Cost Breakdown" in content

        # Check for markdown tables
        assert "|" in content  # Markdown tables use pipes

        # Check for component data
        assert "U1" in content
        assert "STM32F103C8T6" in content


def test_generate_report_table_format(sample_cost_estimate, capsys):
    """Test generate_report with table format."""
    # This will print to stdout
    result = generate_report(sample_cost_estimate, format="table")

    # Should return None for table format
    assert result is None

    # Capture output
    captured = capsys.readouterr()
    # Rich output contains the title
    assert "Cost Estimate Report" in captured.out or "Executive Summary" in captured.out


def test_generate_report_json_format(sample_cost_estimate):
    """Test generate_report with JSON format."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test.json"
        result = generate_report(sample_cost_estimate, format="json", output_path=output_path)

        assert result is not None
        assert isinstance(result, dict)
        assert output_path.exists()


def test_generate_report_csv_format(sample_cost_estimate):
    """Test generate_report with CSV format."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test.csv"
        result = generate_report(sample_cost_estimate, format="csv", output_path=output_path)

        assert result is None
        assert output_path.exists()


def test_generate_report_markdown_format(sample_cost_estimate):
    """Test generate_report with Markdown format."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test.md"
        result = generate_report(sample_cost_estimate, format="markdown", output_path=output_path)

        assert result is None
        assert output_path.exists()


def test_generate_report_invalid_format(sample_cost_estimate):
    """Test generate_report with invalid format."""
    with pytest.raises(ValueError, match="Unknown format"):
        generate_report(sample_cost_estimate, format="invalid")


def test_generate_report_csv_requires_output(sample_cost_estimate):
    """Test that CSV format requires output path."""
    with pytest.raises(ValueError, match="output_path required"):
        generate_report(sample_cost_estimate, format="csv")


def test_generate_report_markdown_requires_output(sample_cost_estimate):
    """Test that Markdown format requires output path."""
    with pytest.raises(ValueError, match="output_path required"):
        generate_report(sample_cost_estimate, format="markdown")


def test_volume_cost_calculation_edge_cases(sample_cost_estimate):
    """Test volume cost calculation with edge cases."""
    # Test with no price breaks
    sample_cost_estimate.component_costs[0].price_breaks = []

    generator = CostReportGenerator(sample_cost_estimate)
    volume_costs = generator._calculate_volume_costs()

    # Should still work, falling back to typical cost
    assert len(volume_costs) == 4
    for costs in volume_costs.values():
        assert costs["total"] > 0
