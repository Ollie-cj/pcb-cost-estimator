"""Tests for cost estimation engine."""

import pytest
from pathlib import Path

from pcb_cost_estimator.models import (
    BomItem,
    BomParseResult,
    ComponentCategory,
    PackageType,
)
from pcb_cost_estimator.cost_estimator import (
    ComponentClassifier,
    PackageClassifier,
    CostEstimator,
)
from pcb_cost_estimator.config import CostModelConfig, CategoryPricing, PackagePricing


class TestComponentClassifier:
    """Test component classification."""

    def test_classify_by_ref_des_resistor(self):
        """Test classification by reference designator for resistor."""
        classifier = ComponentClassifier()
        item = BomItem(
            reference_designator="R1",
            quantity=1,
            category=ComponentCategory.UNKNOWN,
        )
        category, _ = classifier.classify_component(item)
        assert category == ComponentCategory.RESISTOR

    def test_classify_by_ref_des_capacitor(self):
        """Test classification by reference designator for capacitor."""
        classifier = ComponentClassifier()
        item = BomItem(
            reference_designator="C5",
            quantity=1,
            category=ComponentCategory.UNKNOWN,
        )
        category, _ = classifier.classify_component(item)
        assert category == ComponentCategory.CAPACITOR

    def test_classify_by_ref_des_ic(self):
        """Test classification by reference designator for IC."""
        classifier = ComponentClassifier()
        item = BomItem(
            reference_designator="U2",
            quantity=1,
            category=ComponentCategory.UNKNOWN,
        )
        category, _ = classifier.classify_component(item)
        assert category == ComponentCategory.IC

    def test_classify_by_mpn_resistor(self):
        """Test classification by MPN pattern for resistor."""
        classifier = ComponentClassifier()
        item = BomItem(
            reference_designator="R1",
            quantity=1,
            manufacturer_part_number="RC0603FR-0710KL",
            category=ComponentCategory.UNKNOWN,
        )
        category, _ = classifier.classify_component(item)
        assert category == ComponentCategory.RESISTOR

    def test_classify_by_mpn_capacitor(self):
        """Test classification by MPN pattern for capacitor."""
        classifier = ComponentClassifier()
        item = BomItem(
            reference_designator="C1",
            quantity=1,
            manufacturer_part_number="GRM188R71C104KA01D",
            category=ComponentCategory.UNKNOWN,
        )
        category, _ = classifier.classify_component(item)
        assert category == ComponentCategory.CAPACITOR

    def test_classify_by_mpn_ic(self):
        """Test classification by MPN pattern for IC."""
        classifier = ComponentClassifier()
        item = BomItem(
            reference_designator="U1",
            quantity=1,
            manufacturer_part_number="LM358DR",
            category=ComponentCategory.UNKNOWN,
        )
        category, _ = classifier.classify_component(item)
        assert category == ComponentCategory.IC

    def test_classify_by_description(self):
        """Test classification by description keywords."""
        classifier = ComponentClassifier()
        item = BomItem(
            reference_designator="X1",
            quantity=1,
            description="Ceramic Capacitor 100nF 50V",
            category=ComponentCategory.UNKNOWN,
        )
        category, _ = classifier.classify_component(item)
        assert category == ComponentCategory.CAPACITOR

    def test_classify_already_set(self):
        """Test that already-set categories are preserved."""
        classifier = ComponentClassifier()
        item = BomItem(
            reference_designator="R1",
            quantity=1,
            category=ComponentCategory.INDUCTOR,  # Intentionally wrong
        )
        category, _ = classifier.classify_component(item)
        assert category == ComponentCategory.INDUCTOR  # Should keep existing


class TestPackageClassifier:
    """Test package type classification."""

    def test_classify_smd_small(self):
        """Test classification of small SMD packages."""
        classifier = PackageClassifier()
        for pkg in ["0402", "0603"]:
            item = BomItem(
                reference_designator="R1",
                quantity=1,
                package=pkg,
            )
            pkg_type = classifier.classify_package(item)
            assert pkg_type == PackageType.SMD_SMALL

    def test_classify_smd_medium(self):
        """Test classification of medium SMD packages."""
        classifier = PackageClassifier()
        for pkg in ["0805", "1206"]:
            item = BomItem(
                reference_designator="R1",
                quantity=1,
                package=pkg,
            )
            pkg_type = classifier.classify_package(item)
            assert pkg_type == PackageType.SMD_MEDIUM

    def test_classify_soic(self):
        """Test classification of SOIC packages."""
        classifier = PackageClassifier()
        item = BomItem(
            reference_designator="U1",
            quantity=1,
            package="SOIC-8",
        )
        pkg_type = classifier.classify_package(item)
        assert pkg_type == PackageType.SOIC

    def test_classify_qfp(self):
        """Test classification of QFP packages."""
        classifier = PackageClassifier()
        item = BomItem(
            reference_designator="U1",
            quantity=1,
            package="TQFP-48",
        )
        pkg_type = classifier.classify_package(item)
        assert pkg_type == PackageType.QFP

    def test_classify_bga(self):
        """Test classification of BGA packages."""
        classifier = PackageClassifier()
        item = BomItem(
            reference_designator="U1",
            quantity=1,
            package="BGA-256",
        )
        pkg_type = classifier.classify_package(item)
        assert pkg_type == PackageType.BGA

    def test_classify_through_hole(self):
        """Test classification of through-hole packages."""
        classifier = PackageClassifier()
        item = BomItem(
            reference_designator="D1",
            quantity=1,
            package="THT",
        )
        pkg_type = classifier.classify_package(item)
        assert pkg_type == PackageType.THROUGH_HOLE

    def test_classify_no_package_resistor(self):
        """Test package guessing for resistor without package info."""
        classifier = PackageClassifier()
        item = BomItem(
            reference_designator="R1",
            quantity=1,
            category=ComponentCategory.RESISTOR,
        )
        pkg_type = classifier.classify_package(item)
        assert pkg_type == PackageType.SMD_MEDIUM  # Default for resistors

    def test_classify_connector(self):
        """Test classification of connectors."""
        classifier = PackageClassifier()
        item = BomItem(
            reference_designator="J1",
            quantity=1,
            category=ComponentCategory.CONNECTOR,
        )
        pkg_type = classifier.classify_package(item)
        assert pkg_type == PackageType.CONNECTOR


class TestCostEstimator:
    """Test cost estimation."""

    @pytest.fixture
    def basic_config(self):
        """Create a basic cost model configuration."""
        config = CostModelConfig()

        # Add category pricing
        config.category_pricing = {
            "resistor": CategoryPricing(
                base_price_low=0.001,
                base_price_typical=0.005,
                base_price_high=0.02,
            ),
            "capacitor": CategoryPricing(
                base_price_low=0.002,
                base_price_typical=0.01,
                base_price_high=0.05,
            ),
            "ic": CategoryPricing(
                base_price_low=0.50,
                base_price_typical=2.00,
                base_price_high=10.00,
            ),
        }

        # Add package pricing
        config.package_pricing = {
            "smd_small": PackagePricing(multiplier=1.0),
            "smd_medium": PackagePricing(multiplier=1.0),
            "bga": PackagePricing(multiplier=2.0),
        }

        return config

    def test_estimate_component_cost_resistor(self, basic_config):
        """Test cost estimation for a resistor."""
        estimator = CostEstimator(basic_config)
        item = BomItem(
            reference_designator="R1",
            quantity=10,
            category=ComponentCategory.RESISTOR,
            package="0805",
        )

        cost, _ = estimator._estimate_component_cost(item, board_quantity=1)

        assert cost.reference_designator == "R1"
        assert cost.quantity == 10
        assert cost.category == ComponentCategory.RESISTOR
        assert cost.package_type == PackageType.SMD_MEDIUM
        assert cost.unit_cost_typical == 0.005
        assert cost.total_cost_typical == 0.05  # 10 * 0.005
        assert len(cost.price_breaks) == 5  # 5 quantity tiers

    def test_estimate_component_cost_with_package_multiplier(self, basic_config):
        """Test cost estimation with package multiplier."""
        estimator = CostEstimator(basic_config)
        item = BomItem(
            reference_designator="U1",
            quantity=1,
            category=ComponentCategory.IC,
            package="BGA-256",
        )

        cost, _ = estimator._estimate_component_cost(item, board_quantity=1)

        # BGA has 2.0x multiplier
        assert cost.unit_cost_typical == 4.00  # 2.00 * 2.0
        assert cost.package_type == PackageType.BGA

    def test_price_breaks(self, basic_config):
        """Test quantity break pricing calculation."""
        estimator = CostEstimator(basic_config)
        item = BomItem(
            reference_designator="C1",
            quantity=5,
            category=ComponentCategory.CAPACITOR,
            package="0805",
        )

        cost, _ = estimator._estimate_component_cost(item, board_quantity=1)

        # Check price breaks
        assert len(cost.price_breaks) == 5

        # First tier: qty 1, no discount
        assert cost.price_breaks[0].quantity == 1
        assert cost.price_breaks[0].unit_price == 0.01  # No discount

        # Second tier: qty 10, 15% discount
        assert cost.price_breaks[1].quantity == 10
        assert cost.price_breaks[1].unit_price == pytest.approx(0.0085, rel=1e-3)

        # Last tier: qty 10000, 55% discount (45% of original)
        assert cost.price_breaks[4].quantity == 10000
        assert cost.price_breaks[4].unit_price == pytest.approx(0.0045, rel=1e-3)

    def test_estimate_bom_cost(self, basic_config):
        """Test full BoM cost estimation."""
        estimator = CostEstimator(basic_config)

        items = [
            BomItem(reference_designator="R1", quantity=10, category=ComponentCategory.RESISTOR, package="0805"),
            BomItem(reference_designator="C1", quantity=5, category=ComponentCategory.CAPACITOR, package="0805"),
            BomItem(reference_designator="U1", quantity=1, category=ComponentCategory.IC, package="SOIC-8"),
        ]

        bom_result = BomParseResult(items=items)
        cost_estimate = estimator.estimate_bom_cost(bom_result, board_quantity=1)

        # Check component costs
        assert len(cost_estimate.component_costs) == 3

        # Check total component cost
        assert cost_estimate.total_component_cost_typical > 0

        # Check assembly cost
        assert cost_estimate.assembly_cost.total_components == 16  # 10 + 5 + 1
        assert cost_estimate.assembly_cost.unique_components == 3

        # Check overhead costs
        assert cost_estimate.overhead_costs.nre_cost > 0

        # Check total cost per board
        assert cost_estimate.total_cost_per_board_typical > 0

    def test_dnp_items_excluded(self, basic_config):
        """Test that DNP items are excluded from cost estimation."""
        estimator = CostEstimator(basic_config)

        items = [
            BomItem(reference_designator="R1", quantity=10, category=ComponentCategory.RESISTOR, dnp=False),
            BomItem(reference_designator="R2", quantity=5, category=ComponentCategory.RESISTOR, dnp=True),
        ]

        bom_result = BomParseResult(items=items)
        cost_estimate = estimator.estimate_bom_cost(bom_result, board_quantity=1)

        # Only R1 should be included
        assert len(cost_estimate.component_costs) == 1
        assert cost_estimate.component_costs[0].reference_designator == "R1"

    def test_assembly_cost_calculation(self, basic_config):
        """Test assembly cost calculation by package type."""
        estimator = CostEstimator(basic_config)

        items = [
            BomItem(reference_designator="R1", quantity=10, package="0603"),  # SMD small
            BomItem(reference_designator="C1", quantity=5, package="0805"),   # SMD medium
            BomItem(reference_designator="U1", quantity=1, package="BGA-100"), # BGA
        ]

        bom_result = BomParseResult(items=items)
        cost_estimate = estimator.estimate_bom_cost(bom_result, board_quantity=1)

        assembly = cost_estimate.assembly_cost

        # Check package counts
        assert assembly.smd_small_count == 10
        assert assembly.smd_medium_count == 5
        assert assembly.bga_count == 1

        # Check assembly costs
        assert assembly.setup_cost == basic_config.assembly.setup_cost
        assert assembly.placement_cost_per_board > 0
        assert assembly.total_assembly_cost_per_board > 0

    def test_overhead_calculation(self, basic_config):
        """Test overhead cost calculation."""
        estimator = CostEstimator(basic_config)

        items = [
            BomItem(reference_designator="R1", quantity=10, category=ComponentCategory.RESISTOR),
        ]

        bom_result = BomParseResult(items=items)
        cost_estimate = estimator.estimate_bom_cost(bom_result, board_quantity=1)

        overhead = cost_estimate.overhead_costs

        # Check overhead components
        assert overhead.nre_cost == basic_config.overhead.nre_cost
        assert overhead.procurement_overhead >= 0
        assert overhead.supply_chain_risk_factor >= 1.0
        assert overhead.total_overhead > 0

    def test_confidence_intervals(self, basic_config):
        """Test that cost estimates include low/typical/high values."""
        estimator = CostEstimator(basic_config)

        items = [
            BomItem(reference_designator="R1", quantity=10, category=ComponentCategory.RESISTOR),
        ]

        bom_result = BomParseResult(items=items)
        cost_estimate = estimator.estimate_bom_cost(bom_result, board_quantity=1)

        # Check component cost confidence intervals
        comp_cost = cost_estimate.component_costs[0]
        assert comp_cost.unit_cost_low < comp_cost.unit_cost_typical < comp_cost.unit_cost_high
        assert comp_cost.total_cost_low < comp_cost.total_cost_typical < comp_cost.total_cost_high

        # Check total cost confidence intervals
        assert cost_estimate.total_cost_per_board_low < cost_estimate.total_cost_per_board_typical
        assert cost_estimate.total_cost_per_board_typical < cost_estimate.total_cost_per_board_high
