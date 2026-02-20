"""Detailed cost estimator tests with known components and price validation."""

import pytest
from pathlib import Path

from pcb_cost_estimator.models import (
    BomItem,
    BomParseResult,
    ComponentCategory,
    PackageType,
)
from pcb_cost_estimator.cost_estimator import CostEstimator
from pcb_cost_estimator.bom_parser import BomParser


@pytest.mark.unit
class TestCostEstimatorPriceRanges:
    """Test cost estimator with known component types and expected price ranges."""

    @pytest.fixture
    def estimator(self):
        """Create a cost estimator instance."""
        return CostEstimator()

    def test_resistor_price_range(self, estimator):
        """Test that resistor costs fall within expected range."""
        items = [
            BomItem(
                reference_designator="R1",
                quantity=1,
                manufacturer="Vishay",
                manufacturer_part_number="CRCW0603100K",
                description="Resistor 100K 1% 1/10W",
                package="0603",
                value="100K",
                category=ComponentCategory.RESISTOR,
            )
        ]
        parse_result = BomParseResult(
            items=items,
            item_count=1,
            warnings=[],
            errors=[],
            success=True,
        )

        cost_estimate = estimator.estimate_bom_cost(parse_result)

        # Total per board includes NRE overhead, so could be large at qty=1
        assert cost_estimate.total_cost_per_board_typical > 0

        # Component cost should be in reasonable range (resistors: $0.001-$0.02)
        assert len(cost_estimate.component_costs) == 1
        comp_cost = cost_estimate.component_costs[0]
        assert comp_cost.unit_cost_low >= 0.0001
        assert comp_cost.unit_cost_high <= 1.0

    def test_capacitor_price_range(self, estimator):
        """Test that capacitor costs fall within expected range."""
        items = [
            BomItem(
                reference_designator="C1",
                quantity=1,
                manufacturer="Murata",
                manufacturer_part_number="GRM188R71C104KA01D",
                description="Cap Ceramic 0.1uF 16V X7R",
                package="0603",
                value="0.1uF",
                category=ComponentCategory.CAPACITOR,
            )
        ]
        parse_result = BomParseResult(
            items=items,
            item_count=1,
            warnings=[],
            errors=[],
            success=True,
        )

        cost_estimate = estimator.estimate_bom_cost(parse_result)

        # Ceramic capacitors should typically be $0.002 - $0.05 for common values
        comp_cost = cost_estimate.component_costs[0]
        assert comp_cost.unit_cost_low >= 0.0001
        assert comp_cost.unit_cost_high <= 0.2

    def test_ic_price_range(self, estimator):
        """Test that IC costs fall within expected range."""
        items = [
            BomItem(
                reference_designator="U1",
                quantity=1,
                manufacturer="STMicroelectronics",
                manufacturer_part_number="STM32F407VGT6",
                description="MCU ARM Cortex-M4 1MB Flash",
                package="LQFP-100",
                category=ComponentCategory.IC,
            )
        ]
        parse_result = BomParseResult(
            items=items,
            item_count=1,
            warnings=[],
            errors=[],
            success=True,
        )

        cost_estimate = estimator.estimate_bom_cost(parse_result)

        # ICs can range widely, but should be $0.50 - $10+ for MCUs
        comp_cost = cost_estimate.component_costs[0]
        assert comp_cost.unit_cost_low >= 0.1
        assert comp_cost.unit_cost_high <= 50.0

    def test_connector_price_range(self, estimator):
        """Test that connector costs fall within expected range."""
        items = [
            BomItem(
                reference_designator="J1",
                quantity=1,
                manufacturer="Amphenol",
                manufacturer_part_number="10118194-0001LF",
                description="USB Micro-B Connector",
                package="SMD",
                category=ComponentCategory.CONNECTOR,
            )
        ]
        parse_result = BomParseResult(
            items=items,
            item_count=1,
            warnings=[],
            errors=[],
            success=True,
        )

        cost_estimate = estimator.estimate_bom_cost(parse_result)

        # Connectors typically $0.10 - $2.00 for USB
        comp_cost = cost_estimate.component_costs[0]
        assert comp_cost.unit_cost_low >= 0.01
        assert comp_cost.unit_cost_high <= 10.0

    def test_led_price_range(self, estimator):
        """Test that LED costs fall within expected range."""
        items = [
            BomItem(
                reference_designator="D1",
                quantity=1,
                manufacturer="Kingbright",
                manufacturer_part_number="APT1608LSECK",
                description="LED Red 630nm",
                package="0603",
                category=ComponentCategory.LED,
            )
        ]
        parse_result = BomParseResult(
            items=items,
            item_count=1,
            warnings=[],
            errors=[],
            success=True,
        )

        cost_estimate = estimator.estimate_bom_cost(parse_result)

        # LEDs typically $0.02 - $0.30 for standard indicator LEDs
        comp_cost = cost_estimate.component_costs[0]
        assert comp_cost.unit_cost_low >= 0.001
        assert comp_cost.unit_cost_high <= 1.0

    def test_quantity_breaks(self, estimator):
        """Test that quantity breaks provide volume discounts."""
        items = [
            BomItem(
                reference_designator="R1",
                quantity=100,
                category=ComponentCategory.RESISTOR,
                package="0603",
            )
        ]
        parse_result = BomParseResult(
            items=items,
            item_count=1,
            warnings=[],
            errors=[],
            success=True,
        )

        cost_estimate = estimator.estimate_bom_cost(parse_result)

        comp_cost = cost_estimate.component_costs[0]

        # Should have multiple price breaks
        assert len(comp_cost.price_breaks) > 1

        # Higher quantities should have lower or equal unit prices
        prices = [pb.unit_price for pb in comp_cost.price_breaks]
        for i in range(len(prices) - 1):
            assert prices[i] >= prices[i + 1]

    def test_assembly_cost_calculation(self, estimator):
        """Test that assembly costs scale with component count."""
        # Small BoM
        small_items = [
            BomItem(reference_designator=f"R{i}", quantity=1, category=ComponentCategory.RESISTOR)
            for i in range(10)
        ]
        small_result = BomParseResult(
            items=small_items,
            item_count=10,
            warnings=[],
            errors=[],
            success=True,
        )
        small_estimate = estimator.estimate_bom_cost(small_result)

        # Large BoM
        large_items = [
            BomItem(reference_designator=f"R{i}", quantity=1, category=ComponentCategory.RESISTOR)
            for i in range(100)
        ]
        large_result = BomParseResult(
            items=large_items,
            item_count=100,
            warnings=[],
            errors=[],
            success=True,
        )
        large_estimate = estimator.estimate_bom_cost(large_result)

        # Large BoM should have higher assembly costs
        assert large_estimate.assembly_cost.total_assembly_cost_per_board > small_estimate.assembly_cost.total_assembly_cost_per_board

    def test_package_complexity_affects_assembly_cost(self, estimator):
        """Test that complex packages have higher assembly costs."""
        # Simple SMD package
        simple_items = [
            BomItem(
                reference_designator="R1",
                quantity=1,
                category=ComponentCategory.RESISTOR,
                package="0603",
            )
        ]
        simple_result = BomParseResult(
            items=simple_items,
            item_count=1,
            warnings=[],
            errors=[],
            success=True,
        )
        simple_estimate = estimator.estimate_bom_cost(simple_result)

        # Complex BGA package
        complex_items = [
            BomItem(
                reference_designator="U1",
                quantity=1,
                category=ComponentCategory.IC,
                package="BGA-256",
            )
        ]
        complex_result = BomParseResult(
            items=complex_items,
            item_count=1,
            warnings=[],
            errors=[],
            success=True,
        )
        complex_estimate = estimator.estimate_bom_cost(complex_result)

        # BGA assembly should cost more than simple SMD
        assert complex_estimate.assembly_cost.total_assembly_cost_per_board > simple_estimate.assembly_cost.total_assembly_cost_per_board

    def test_dnp_components_excluded_from_cost(self, estimator):
        """Test that DNP components are not included in cost."""
        items = [
            BomItem(
                reference_designator="R1",
                quantity=1,
                category=ComponentCategory.RESISTOR,
                dnp=False,
            ),
            BomItem(
                reference_designator="R2",
                quantity=1,
                category=ComponentCategory.RESISTOR,
                dnp=True,
            ),
        ]
        parse_result = BomParseResult(
            items=items,
            item_count=2,
            warnings=[],
            errors=[],
            success=True,
        )

        cost_estimate = estimator.estimate_bom_cost(parse_result)

        # Should only have 1 component cost (for R1, not R2)
        assert len(cost_estimate.component_costs) == 1
        assert cost_estimate.component_costs[0].reference_designator == "R1"

    def test_overhead_costs_included(self, estimator):
        """Test that overhead costs are calculated."""
        items = [
            BomItem(
                reference_designator="R1",
                quantity=1,
                category=ComponentCategory.RESISTOR,
            )
        ]
        parse_result = BomParseResult(
            items=items,
            item_count=1,
            warnings=[],
            errors=[],
            success=True,
        )

        cost_estimate = estimator.estimate_bom_cost(parse_result)

        # Should have overhead costs
        assert cost_estimate.overhead_costs.nre_cost >= 0
        assert cost_estimate.overhead_costs.markup_percentage > 0
        assert cost_estimate.overhead_costs.total_overhead > 0


@pytest.mark.unit
class TestCostEstimatorWithRealBoms:
    """Test cost estimator with realistic BoM fixtures."""

    @pytest.fixture
    def parser(self):
        """Create a parser instance."""
        return BomParser()

    @pytest.fixture
    def estimator(self):
        """Create a cost estimator instance."""
        return CostEstimator()

    def test_arduino_shield_cost_estimate(self, parser, estimator):
        """Test cost estimation for Arduino shield BoM."""
        fixture_path = Path(__file__).parent / "fixtures" / "arduino_shield_simple.csv"
        parse_result = parser.parse_file(fixture_path)

        cost_estimate = estimator.estimate_bom_cost(parse_result)

        assert cost_estimate.total_cost_per_board_low > 0
        assert cost_estimate.total_cost_per_board_typical > 0
        assert cost_estimate.total_cost_per_board_high > 0

        # Verify cost ordering
        assert cost_estimate.total_cost_per_board_low <= cost_estimate.total_cost_per_board_typical
        assert cost_estimate.total_cost_per_board_typical <= cost_estimate.total_cost_per_board_high

        # Arduino shield components typically $5-50; NRE ($500) is included in per-board cost
        assert cost_estimate.total_cost_per_board_typical >= 1.0

        # Should have costs broken down by component
        assert len(cost_estimate.component_costs) > 0

    def test_iot_board_cost_estimate(self, parser, estimator):
        """Test cost estimation for IoT board BoM."""
        fixture_path = Path(__file__).parent / "fixtures" / "iot_board_medium.csv"
        parse_result = parser.parse_file(fixture_path)

        cost_estimate = estimator.estimate_bom_cost(parse_result)

        assert cost_estimate.total_cost_per_board_typical > 0

        # IoT board should cost more than simple shield
        assert cost_estimate.total_cost_per_board_typical >= 10.0

        # Should have assembly costs
        assert cost_estimate.assembly_cost.total_assembly_cost_per_board > 0

        # Should have multiple component categories
        categories = {cc.category for cc in cost_estimate.component_costs}
        assert len(categories) >= 3

    def test_mixed_signal_cost_estimate(self, parser, estimator):
        """Test cost estimation for complex mixed-signal board BoM."""
        fixture_path = Path(__file__).parent / "fixtures" / "mixed_signal_complex.csv"
        parse_result = parser.parse_file(fixture_path)

        cost_estimate = estimator.estimate_bom_cost(parse_result)

        assert cost_estimate.total_cost_per_board_typical > 0

        # Complex board should be most expensive
        assert cost_estimate.total_cost_per_board_typical >= 50.0

        # Should have significant assembly costs due to component count
        assert cost_estimate.assembly_cost.total_assembly_cost_per_board > 20.0

        # Should have overhead costs
        assert cost_estimate.overhead_costs.total_overhead > 0


@pytest.mark.unit
class TestCostEstimatorEdgeCases:
    """Test cost estimator edge cases."""

    @pytest.fixture
    def estimator(self):
        """Create a cost estimator instance."""
        return CostEstimator()

    def test_empty_bom(self, estimator):
        """Test cost estimation for empty BoM."""
        parse_result = BomParseResult(
            items=[],
            item_count=0,
            warnings=[],
            errors=[],
            success=True,
        )

        cost_estimate = estimator.estimate_bom_cost(parse_result)

        # Should have minimal costs (just overhead/NRE)
        assert cost_estimate.total_cost_per_board_typical >= 0

    def test_unknown_category_component(self, estimator):
        """Test component with unknown category."""
        items = [
            BomItem(
                reference_designator="X1",
                quantity=1,
                category=ComponentCategory.UNKNOWN,
            )
        ]
        parse_result = BomParseResult(
            items=items,
            item_count=1,
            warnings=[],
            errors=[],
            success=True,
        )

        cost_estimate = estimator.estimate_bom_cost(parse_result)

        # Should still provide estimate
        assert cost_estimate.total_cost_per_board_typical > 0
        assert len(cost_estimate.component_costs) == 1

    def test_unknown_package_type(self, estimator):
        """Test component with unknown package."""
        items = [
            BomItem(
                reference_designator="U1",
                quantity=1,
                category=ComponentCategory.IC,
                package="UNKNOWN_PACKAGE",
            )
        ]
        parse_result = BomParseResult(
            items=items,
            item_count=1,
            warnings=[],
            errors=[],
            success=True,
        )

        cost_estimate = estimator.estimate_bom_cost(parse_result)

        # Should still provide estimate with default package pricing
        assert cost_estimate.total_cost_per_board_typical > 0

    def test_very_large_quantity(self, estimator):
        """Test component with very large quantity."""
        items = [
            BomItem(
                reference_designator="R1",
                quantity=100000,
                category=ComponentCategory.RESISTOR,
            )
        ]
        parse_result = BomParseResult(
            items=items,
            item_count=1,
            warnings=[],
            errors=[],
            success=True,
        )

        cost_estimate = estimator.estimate_bom_cost(parse_result)

        # Should handle large quantities
        assert cost_estimate.total_cost_per_board_typical > 0
        comp_cost = cost_estimate.component_costs[0]

        # Should have volume pricing applied
        assert len(comp_cost.price_breaks) > 0

    def test_mixed_package_types(self, estimator):
        """Test BoM with mixed SMD and through-hole packages."""
        items = [
            BomItem(
                reference_designator="R1",
                quantity=1,
                category=ComponentCategory.RESISTOR,
                package="0603",  # SMD
            ),
            BomItem(
                reference_designator="J1",
                quantity=1,
                category=ComponentCategory.CONNECTOR,
                package="TH",  # Through-hole
            ),
        ]
        parse_result = BomParseResult(
            items=items,
            item_count=2,
            warnings=[],
            errors=[],
            success=True,
        )

        cost_estimate = estimator.estimate_bom_cost(parse_result)

        # Should handle both package types
        assert len(cost_estimate.component_costs) == 2

        # Assembly cost should account for different packages
        assert cost_estimate.assembly_cost.total_assembly_cost_per_board > 0
