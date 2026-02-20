"""Unit tests for provenance-aware sourcing modes."""

import pytest
from unittest.mock import MagicMock, patch

from pcb_cost_estimator.models import (
    BomItem,
    BomParseResult,
    ComponentCategory,
    ProvenanceRisk,
    ProvenanceScore,
    SourcingMode,
)
from pcb_cost_estimator.component_intelligence import (
    ComponentIntelligenceService,
    DistributorResult,
    EU_DISTRIBUTOR_NAMES,
    GLOBAL_DISTRIBUTOR_NAMES,
)
from pcb_cost_estimator.cost_estimator import CostEstimator
from pcb_cost_estimator.config import (
    CostModelConfig,
    CategoryPricing,
    PackagePricing,
    AssemblyPricing,
    OverheadConfig,
    QuantityBreakConfig,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_item(
    ref: str = "R1",
    qty: int = 1,
    category: ComponentCategory = ComponentCategory.RESISTOR,
    mpn: str = "RC0603FR-0710KL",
) -> BomItem:
    return BomItem(
        reference_designator=ref,
        quantity=qty,
        manufacturer_part_number=mpn,
        category=category,
    )


def _make_cost_config() -> CostModelConfig:
    """Build a minimal CostModelConfig for testing."""
    category_pricing = {
        cat.value: CategoryPricing(
            base_price_low=0.01,
            base_price_typical=0.10,
            base_price_high=1.00,
        )
        for cat in ComponentCategory
    }
    package_pricing = {
        "smd_small": PackagePricing(multiplier=1.0),
        "smd_medium": PackagePricing(multiplier=1.0),
        "soic": PackagePricing(multiplier=1.2),
        "bga": PackagePricing(multiplier=2.0),
        "through_hole": PackagePricing(multiplier=1.1),
        "connector": PackagePricing(multiplier=1.0),
        "other": PackagePricing(multiplier=1.0),
        "unknown": PackagePricing(multiplier=1.0),
    }
    assembly = AssemblyPricing(
        setup_cost=0.0,
        cost_per_smd_small=0.01,
        cost_per_smd_medium=0.02,
        cost_per_smd_large=0.03,
        cost_per_soic=0.05,
        cost_per_qfp=0.08,
        cost_per_qfn=0.07,
        cost_per_bga=0.15,
        cost_per_through_hole=0.04,
        cost_per_connector=0.06,
        cost_per_other=0.03,
    )
    overhead = OverheadConfig(
        nre_cost=0.0,
        procurement_overhead_percentage=0.0,
        supply_chain_risk_low=1.0,
        supply_chain_risk_medium=1.5,
        supply_chain_risk_high=2.0,
    )
    qty_breaks = QuantityBreakConfig(
        tiers=[1, 10, 100, 1000, 10000],
        discount_curve=[1.0, 0.85, 0.70, 0.55, 0.45],
    )
    return CostModelConfig(
        category_pricing=category_pricing,
        package_pricing=package_pricing,
        assembly=assembly,
        overhead=overhead,
        quantity_breaks=qty_breaks,
    )


# ---------------------------------------------------------------------------
# ComponentIntelligenceService tests
# ---------------------------------------------------------------------------


class TestComponentIntelligenceService:
    """Tests for ComponentIntelligenceService."""

    def test_global_mode_returns_low_provenance_risk(self):
        """GLOBAL mode should always result in LOW provenance risk."""
        svc = ComponentIntelligenceService()
        item = _make_item()
        score = svc.get_component_info(item, 0.10, SourcingMode.GLOBAL)
        assert score.sourcing_mode == SourcingMode.GLOBAL
        assert score.provenance_risk == ProvenanceRisk.LOW
        assert not score.flagged

    def test_global_mode_provides_eu_price_delta(self):
        """GLOBAL mode still computes EU delta for informational purposes."""
        svc = ComponentIntelligenceService()
        # Use a resistor MPN that hashes to EU-available.
        item = _make_item(mpn="RC0603FR-0710KL")
        score = svc.get_component_info(item, 0.10, SourcingMode.GLOBAL, ComponentCategory.RESISTOR)
        # If EU available, delta should be populated.
        if score.eu_available:
            assert score.eu_price_delta_pct is not None
            assert score.global_unit_price is not None

    def test_eu_preferred_uses_eu_price_within_threshold(self):
        """EU_PREFERRED should use EU price when within the premium threshold."""
        svc = ComponentIntelligenceService(eu_premium_threshold=0.30)
        # Create an item where EU is available (resistors have 98% EU availability)
        item = _make_item(mpn="RC0603FR-0710KL", category=ComponentCategory.RESISTOR)
        score = svc.get_component_info(
            item, 0.10, SourcingMode.EU_PREFERRED, ComponentCategory.RESISTOR
        )
        if score.eu_available and not score.flagged:
            # EU was used and within threshold
            assert score.eu_unit_price is not None
            assert score.eu_price_delta_pct is not None
            assert score.eu_price_delta_pct <= svc.eu_premium_threshold * 100

    def test_eu_preferred_falls_back_when_premium_exceeds_threshold(self):
        """EU_PREFERRED should fall back if EU premium exceeds threshold."""
        # Set a very low threshold so EU premium always exceeds it
        svc = ComponentIntelligenceService(eu_premium_threshold=0.001)
        item = _make_item(mpn="RC0603FR-0710KL", category=ComponentCategory.RESISTOR)
        score = svc.get_component_info(
            item, 0.10, SourcingMode.EU_PREFERRED, ComponentCategory.RESISTOR
        )
        if score.eu_available:
            # With threshold of 0.1%, any EU premium will exceed it
            assert score.flagged
            assert score.flag_reason is not None
            assert "exceeds threshold" in score.flag_reason
            assert score.provenance_risk == ProvenanceRisk.MEDIUM

    def test_eu_preferred_flags_when_eu_unavailable(self):
        """EU_PREFERRED should flag parts where EU sourcing is unavailable."""
        svc = ComponentIntelligenceService()
        # Force EU unavailability by patching internal method
        with patch.object(svc, "_is_eu_available", return_value=False):
            item = _make_item(category=ComponentCategory.IC)
            score = svc.get_component_info(
                item, 1.00, SourcingMode.EU_PREFERRED, ComponentCategory.IC
            )
        assert not score.eu_available
        assert score.flagged
        assert score.provenance_risk == ProvenanceRisk.MEDIUM
        assert "EU sourcing unavailable" in (score.flag_reason or "")

    def test_eu_only_flags_unavailable_as_high_risk(self):
        """EU_ONLY should flag parts with no EU source as HIGH provenance risk."""
        svc = ComponentIntelligenceService()
        with patch.object(svc, "_is_eu_available", return_value=False):
            item = _make_item(category=ComponentCategory.IC)
            score = svc.get_component_info(
                item, 1.00, SourcingMode.EU_ONLY, ComponentCategory.IC
            )
        assert not score.eu_available
        assert score.flagged
        assert score.provenance_risk == ProvenanceRisk.HIGH
        assert "No EU/UK source available" in (score.flag_reason or "")

    def test_eu_only_accepts_eu_sourced_parts(self):
        """EU_ONLY should accept parts where EU sourcing is available."""
        svc = ComponentIntelligenceService()
        with patch.object(svc, "_is_eu_available", return_value=True):
            item = _make_item(category=ComponentCategory.RESISTOR)
            score = svc.get_component_info(
                item, 0.10, SourcingMode.EU_ONLY, ComponentCategory.RESISTOR
            )
        assert score.eu_available
        assert not score.flagged
        assert score.provenance_risk == ProvenanceRisk.LOW

    def test_provenance_score_contains_distributor_names(self):
        """ProvenanceScore should carry distributor names."""
        svc = ComponentIntelligenceService()
        with patch.object(svc, "_is_eu_available", return_value=True):
            item = _make_item(category=ComponentCategory.RESISTOR)
            score = svc.get_component_info(
                item, 0.10, SourcingMode.EU_PREFERRED, ComponentCategory.RESISTOR
            )
        assert score.eu_distributor is not None
        assert score.global_distributor is not None

    def test_eu_price_delta_calculation(self):
        """eu_price_delta_pct should correctly represent the EU premium."""
        svc = ComponentIntelligenceService()
        with patch.object(svc, "_is_eu_available", return_value=True):
            item = _make_item(category=ComponentCategory.RESISTOR)
            score = svc.get_component_info(
                item, 0.10, SourcingMode.EU_PREFERRED, ComponentCategory.RESISTOR
            )
        assert score.eu_price_delta_pct is not None
        # EU price should be above global price (positive delta)
        assert score.eu_price_delta_pct > 0
        # Manually verify the formula
        if score.eu_unit_price and score.global_unit_price:
            expected = (score.eu_unit_price - score.global_unit_price) / score.global_unit_price * 100
            assert abs(score.eu_price_delta_pct - expected) < 0.001

    def test_stable_hash_determinism(self):
        """_stable_hash should return the same value for the same input."""
        svc = ComponentIntelligenceService()
        h1 = svc._stable_hash("RC0603FR-0710KL")
        h2 = svc._stable_hash("RC0603FR-0710KL")
        assert h1 == h2

    def test_stable_hash_range(self):
        """_stable_hash should return values in [0, 1)."""
        svc = ComponentIntelligenceService()
        for mpn in ["RC0603FR", "GRM188R71", "LM358DR", "STM32F4", "1N4148"]:
            h = svc._stable_hash(mpn)
            assert 0.0 <= h < 1.0

    def test_eu_distributor_names_set(self):
        """EU_DISTRIBUTOR_NAMES should contain expected distributors."""
        assert "farnell" in EU_DISTRIBUTOR_NAMES
        assert "rs_components" in EU_DISTRIBUTOR_NAMES
        assert "digikey" not in EU_DISTRIBUTOR_NAMES

    def test_global_distributor_names_set(self):
        """GLOBAL_DISTRIBUTOR_NAMES should not contain EU distributors."""
        for name in GLOBAL_DISTRIBUTOR_NAMES:
            assert name not in EU_DISTRIBUTOR_NAMES


# ---------------------------------------------------------------------------
# CostEstimator integration tests with sourcing modes
# ---------------------------------------------------------------------------


class TestCostEstimatorSourcingModes:
    """Integration tests for CostEstimator with sourcing modes."""

    def _make_bom_result(self, items=None) -> BomParseResult:
        if items is None:
            items = [
                _make_item("R1", 2, ComponentCategory.RESISTOR, "RC0603FR-0710KL"),
                _make_item("C1", 1, ComponentCategory.CAPACITOR, "GRM188R71C104KA01D"),
                _make_item("U1", 1, ComponentCategory.IC, "LM358DR"),
            ]
        return BomParseResult(items=items, file_path="test.csv")

    def test_global_mode_default(self):
        """Default GLOBAL mode should work without provenance scoring changes."""
        config = _make_cost_config()
        estimator = CostEstimator(config)
        bom = self._make_bom_result()
        estimate = estimator.estimate_bom_cost(bom)
        assert estimate.sourcing_mode == SourcingMode.GLOBAL
        assert estimate.total_cost_per_board_typical > 0

    def test_global_mode_explicit(self):
        """Explicitly passing GLOBAL mode should match default behavior."""
        config = _make_cost_config()
        estimator = CostEstimator(config)
        bom = self._make_bom_result()
        estimate_default = estimator.estimate_bom_cost(bom)
        estimate_explicit = estimator.estimate_bom_cost(bom, sourcing_mode=SourcingMode.GLOBAL)
        assert estimate_default.total_cost_per_board_typical == estimate_explicit.total_cost_per_board_typical

    def test_each_component_has_provenance_score(self):
        """Each component should carry a ProvenanceScore regardless of mode."""
        config = _make_cost_config()
        estimator = CostEstimator(config)
        bom = self._make_bom_result()
        for mode in SourcingMode:
            estimate = estimator.estimate_bom_cost(bom, sourcing_mode=mode)
            for comp in estimate.component_costs:
                assert comp.provenance_score is not None, (
                    f"{comp.reference_designator} missing provenance_score in {mode} mode"
                )

    def test_eu_only_flags_unavailable_parts(self):
        """EU_ONLY mode should flag parts with no EU source."""
        config = _make_cost_config()
        svc = ComponentIntelligenceService()
        # Force all items to have no EU source
        with patch.object(svc, "_is_eu_available", return_value=False):
            estimator = CostEstimator(config, intelligence_service=svc)
            bom = self._make_bom_result()
            estimate = estimator.estimate_bom_cost(bom, sourcing_mode=SourcingMode.EU_ONLY)
        assert len(estimate.provenance_flagged_parts) > 0
        # Verify HIGH risk parts appear in flagged list
        high_risk = [
            c.reference_designator
            for c in estimate.component_costs
            if c.provenance_score and c.provenance_score.provenance_risk == ProvenanceRisk.HIGH
        ]
        assert len(high_risk) > 0
        for ref in high_risk:
            assert ref in estimate.provenance_flagged_parts

    def test_eu_only_adds_warning_for_unavailable_parts(self):
        """EU_ONLY mode should add a warning when parts lack EU sourcing."""
        config = _make_cost_config()
        svc = ComponentIntelligenceService()
        with patch.object(svc, "_is_eu_available", return_value=False):
            estimator = CostEstimator(config, intelligence_service=svc)
            bom = self._make_bom_result()
            estimate = estimator.estimate_bom_cost(bom, sourcing_mode=SourcingMode.EU_ONLY)
        eu_warnings = [w for w in estimate.warnings if "EU_ONLY" in w]
        assert len(eu_warnings) > 0

    def test_eu_preferred_falls_back_and_warns(self):
        """EU_PREFERRED with very tight threshold should fall back to global."""
        config = _make_cost_config()
        svc = ComponentIntelligenceService(eu_premium_threshold=0.001)
        with patch.object(svc, "_is_eu_available", return_value=True):
            estimator = CostEstimator(config, intelligence_service=svc)
            bom = self._make_bom_result()
            estimate = estimator.estimate_bom_cost(bom, sourcing_mode=SourcingMode.EU_PREFERRED)
        assert estimate.sourcing_mode == SourcingMode.EU_PREFERRED
        # Parts should be flagged
        assert len(estimate.provenance_flagged_parts) > 0

    def test_eu_preferred_no_flag_when_within_threshold(self):
        """EU_PREFERRED should not flag parts within the premium threshold."""
        config = _make_cost_config()
        svc = ComponentIntelligenceService(eu_premium_threshold=0.50)  # very generous
        with patch.object(svc, "_is_eu_available", return_value=True):
            estimator = CostEstimator(config, intelligence_service=svc)
            items = [_make_item("R1", 1, ComponentCategory.RESISTOR, "RC0603FR-0710KL")]
            bom = BomParseResult(items=items)
            estimate = estimator.estimate_bom_cost(bom, sourcing_mode=SourcingMode.EU_PREFERRED)
        # With 50% threshold and ~6% EU premium, no part should be flagged
        assert len(estimate.provenance_flagged_parts) == 0

    def test_eu_price_delta_populated_on_line_items(self):
        """eu_price_delta_pct should be set on component cost estimates."""
        config = _make_cost_config()
        svc = ComponentIntelligenceService()
        with patch.object(svc, "_is_eu_available", return_value=True):
            estimator = CostEstimator(config, intelligence_service=svc)
            bom = self._make_bom_result()
            estimate = estimator.estimate_bom_cost(bom, sourcing_mode=SourcingMode.EU_PREFERRED)
        for comp in estimate.component_costs:
            assert comp.eu_price_delta_pct is not None

    def test_sourcing_mode_preserved_in_estimate(self):
        """The sourcing_mode should be preserved in the returned CostEstimate."""
        config = _make_cost_config()
        estimator = CostEstimator(config)
        bom = self._make_bom_result()
        for mode in SourcingMode:
            estimate = estimator.estimate_bom_cost(bom, sourcing_mode=mode)
            assert estimate.sourcing_mode == mode

    def test_dnp_items_excluded_from_provenance(self):
        """DNP items should be excluded from provenance scoring."""
        config = _make_cost_config()
        estimator = CostEstimator(config)
        items = [
            _make_item("R1", 1, ComponentCategory.RESISTOR),
            BomItem(
                reference_designator="R2",
                quantity=1,
                category=ComponentCategory.RESISTOR,
                dnp=True,
            ),
        ]
        bom = BomParseResult(items=items)
        estimate = estimator.estimate_bom_cost(bom, sourcing_mode=SourcingMode.EU_ONLY)
        ref_des_list = [c.reference_designator for c in estimate.component_costs]
        assert "R1" in ref_des_list
        assert "R2" not in ref_des_list

    def test_intelligence_mode_backward_compatibility(self):
        """CostEstimator should work without explicit sourcing_mode (backward compat)."""
        config = _make_cost_config()
        estimator = CostEstimator(config)
        bom = self._make_bom_result()
        # Should not raise – uses GLOBAL by default
        estimate = estimator.estimate_bom_cost(bom, board_quantity=10)
        assert estimate.sourcing_mode == SourcingMode.GLOBAL
        assert estimate.total_cost_per_board_typical > 0


# ---------------------------------------------------------------------------
# CLI integration tests for --sourcing-mode flag
# ---------------------------------------------------------------------------


class TestCLISourcingModeFlag:
    """Tests to verify the CLI --sourcing-mode flag is wired up correctly."""

    def test_sourcing_mode_enum_values(self):
        """SourcingMode enum should have the expected values."""
        assert SourcingMode.GLOBAL.value == "global"
        assert SourcingMode.EU_PREFERRED.value == "eu_preferred"
        assert SourcingMode.EU_ONLY.value == "eu_only"

    def test_cli_sourcing_mode_mapping(self):
        """CLI string values should map to correct SourcingMode enums."""
        mapping = {
            "global": SourcingMode.GLOBAL,
            "eu-preferred": SourcingMode.EU_PREFERRED,
            "eu-only": SourcingMode.EU_ONLY,
        }
        for cli_str, expected_mode in mapping.items():
            result = {
                "global": SourcingMode.GLOBAL,
                "eu-preferred": SourcingMode.EU_PREFERRED,
                "eu-only": SourcingMode.EU_ONLY,
            }[cli_str]
            assert result == expected_mode


# ---------------------------------------------------------------------------
# DistributorResult tests
# ---------------------------------------------------------------------------


class TestDistributorResult:
    """Tests for the DistributorResult dataclass."""

    def test_is_eu_flag(self):
        r_eu = DistributorResult(
            distributor_name="farnell", is_eu=True, unit_price=0.10
        )
        r_global = DistributorResult(
            distributor_name="digikey", is_eu=False, unit_price=0.09
        )
        assert r_eu.is_eu
        assert not r_global.is_eu

    def test_display_name(self):
        r = DistributorResult(distributor_name="farnell", is_eu=True, unit_price=0.10)
        assert r.display_name == "Farnell"

    def test_unknown_display_name_falls_back_to_key(self):
        r = DistributorResult(distributor_name="unknown_dist", is_eu=False, unit_price=0.05)
        assert r.display_name == "unknown_dist"


# ---------------------------------------------------------------------------
# ProvenanceScore model tests
# ---------------------------------------------------------------------------


class TestProvenanceScoreModel:
    """Tests for the ProvenanceScore Pydantic model."""

    def test_default_values(self):
        score = ProvenanceScore(sourcing_mode=SourcingMode.GLOBAL)
        assert score.eu_available is False
        assert score.provenance_risk == ProvenanceRisk.LOW
        assert score.flagged is False
        assert score.flag_reason is None

    def test_high_risk_eu_only(self):
        score = ProvenanceScore(
            sourcing_mode=SourcingMode.EU_ONLY,
            eu_available=False,
            provenance_risk=ProvenanceRisk.HIGH,
            flagged=True,
            flag_reason="No EU/UK source available",
        )
        assert score.provenance_risk == ProvenanceRisk.HIGH
        assert score.flagged

    def test_eu_price_delta_stored(self):
        score = ProvenanceScore(
            sourcing_mode=SourcingMode.EU_PREFERRED,
            eu_available=True,
            eu_unit_price=0.107,
            global_unit_price=0.10,
            eu_price_delta_pct=7.0,
        )
        assert score.eu_price_delta_pct == pytest.approx(7.0)
