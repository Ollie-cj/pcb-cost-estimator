"""Component intelligence service for provenance-aware distributor sourcing."""

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .models import (
    BomItem,
    ComponentCategory,
    ProvenanceRisk,
    ProvenanceScore,
    SourcingMode,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Distributor metadata
# ---------------------------------------------------------------------------

#: Distributors that stock from EU/UK warehouses and are considered EU sources.
EU_DISTRIBUTOR_NAMES: Set[str] = {
    "farnell",
    "rs_components",
    "rs components",
    "mouser_eu",
    "digikey_eu",
    "conrad",
    "tme",
    "reichelt",
    "buerklin",
    "distrelec",
}

#: Global (non-EU) distributors.
GLOBAL_DISTRIBUTOR_NAMES: Set[str] = {
    "digikey",
    "mouser",
    "arrow",
    "avnet",
    "future_electronics",
    "newark",
}

# Distributor display names for reporting.
DISTRIBUTOR_DISPLAY_NAMES: Dict[str, str] = {
    "farnell": "Farnell",
    "rs_components": "RS Components",
    "mouser_eu": "Mouser (EU)",
    "digikey_eu": "Digi-Key (EU)",
    "conrad": "Conrad Electronic",
    "tme": "TME",
    "reichelt": "Reichelt",
    "buerklin": "Bürklin",
    "distrelec": "Distrelec",
    "digikey": "Digi-Key",
    "mouser": "Mouser",
    "arrow": "Arrow Electronics",
    "avnet": "Avnet",
    "future_electronics": "Future Electronics",
    "newark": "Newark",
}

# ---------------------------------------------------------------------------
# Per-category EU availability and premium
#
# EU availability: probability (0-1) that a component in this category can
# be sourced from an EU/UK distributor.
#
# EU premium: typical price markup compared to global pricing when sourcing
# from an EU distributor.  E.g. 0.08 means +8 %.
# ---------------------------------------------------------------------------

_EU_AVAILABILITY: Dict[str, float] = {
    ComponentCategory.RESISTOR.value: 0.98,
    ComponentCategory.CAPACITOR.value: 0.97,
    ComponentCategory.INDUCTOR.value: 0.95,
    ComponentCategory.CONNECTOR.value: 0.92,
    ComponentCategory.DIODE.value: 0.93,
    ComponentCategory.TRANSISTOR.value: 0.92,
    ComponentCategory.LED.value: 0.88,
    ComponentCategory.CRYSTAL.value: 0.85,
    ComponentCategory.SWITCH.value: 0.90,
    ComponentCategory.RELAY.value: 0.87,
    ComponentCategory.FUSE.value: 0.92,
    ComponentCategory.IC.value: 0.80,
    ComponentCategory.TRANSFORMER.value: 0.72,
    ComponentCategory.OTHER.value: 0.68,
    ComponentCategory.UNKNOWN.value: 0.65,
}

_EU_PREMIUM: Dict[str, float] = {
    ComponentCategory.RESISTOR.value: 0.06,
    ComponentCategory.CAPACITOR.value: 0.07,
    ComponentCategory.INDUCTOR.value: 0.10,
    ComponentCategory.CONNECTOR.value: 0.09,
    ComponentCategory.DIODE.value: 0.08,
    ComponentCategory.TRANSISTOR.value: 0.09,
    ComponentCategory.LED.value: 0.11,
    ComponentCategory.CRYSTAL.value: 0.12,
    ComponentCategory.SWITCH.value: 0.10,
    ComponentCategory.RELAY.value: 0.12,
    ComponentCategory.FUSE.value: 0.08,
    ComponentCategory.IC.value: 0.13,
    ComponentCategory.TRANSFORMER.value: 0.15,
    ComponentCategory.OTHER.value: 0.14,
    ComponentCategory.UNKNOWN.value: 0.15,
}


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------


@dataclass
class DistributorResult:
    """Price quote returned by a single distributor."""

    distributor_name: str
    is_eu: bool
    unit_price: float
    in_stock: bool = True
    min_quantity: int = 1
    lead_time_days: int = 3
    currency: str = "USD"

    @property
    def display_name(self) -> str:
        return DISTRIBUTOR_DISPLAY_NAMES.get(self.distributor_name, self.distributor_name)


# ---------------------------------------------------------------------------
# ComponentIntelligenceService
# ---------------------------------------------------------------------------


class ComponentIntelligenceService:
    """Service that queries multiple distributors and applies sourcing-mode
    filtering to return the best price for a component.

    In production this would fan out HTTP requests to real distributor APIs
    (e.g. Octopart, Nexar, Farnell, RS Components).  Here we use a
    deterministic simulation based on component category and MPN hash so that
    the logic can be tested without network access.

    Parameters
    ----------
    eu_premium_threshold:
        Maximum EU premium (as a fraction of the global price) before
        EU_PREFERRED mode falls back to global pricing.  Default is 0.30
        (30 %).
    """

    def __init__(self, eu_premium_threshold: float = 0.30) -> None:
        self.eu_premium_threshold = eu_premium_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def _to_category(value: object) -> ComponentCategory:
        """Normalize *value* to a :class:`ComponentCategory` enum member.

        Handles plain strings (stored by Pydantic when ``use_enum_values=True``),
        enum members, and *None*.
        """
        if isinstance(value, ComponentCategory):
            return value
        if isinstance(value, str):
            try:
                return ComponentCategory(value)
            except ValueError:
                return ComponentCategory.UNKNOWN
        return ComponentCategory.UNKNOWN

    def get_component_info(
        self,
        item: BomItem,
        base_unit_price: float,
        sourcing_mode: SourcingMode = SourcingMode.GLOBAL,
        category: Optional[ComponentCategory] = None,
    ) -> ProvenanceScore:
        """Return a :class:`ProvenanceScore` for *item* under *sourcing_mode*.

        Parameters
        ----------
        item:
            The BoM item to evaluate.
        base_unit_price:
            The unconstrained (global) unit price for the component.
        sourcing_mode:
            Controls which distributor results are considered.
        category:
            Pre-classified component category.  If *None*, falls back to the
            item's own category field.

        Returns
        -------
        ProvenanceScore
            Populated provenance information including EU vs global pricing.
        """
        if category is None:
            category = self._to_category(item.category)
        else:
            category = self._to_category(category)

        # Simulate distributor results (synchronous wrapper).
        distributor_results = self._simulate_distributor_results(
            item=item,
            base_unit_price=base_unit_price,
            category=category,
        )

        return self._build_provenance_score(
            item=item,
            distributor_results=distributor_results,
            sourcing_mode=sourcing_mode,
            base_unit_price=base_unit_price,
        )

    async def get_component_info_async(
        self,
        item: BomItem,
        base_unit_price: float,
        sourcing_mode: SourcingMode = SourcingMode.GLOBAL,
        category: Optional[ComponentCategory] = None,
    ) -> ProvenanceScore:
        """Async version of :meth:`get_component_info`.

        In a real implementation this would fan out httpx async requests to
        distributor APIs in parallel.  Here it delegates to the synchronous
        simulation.
        """
        # Simulate IO latency (no-op in tests / CI).
        await asyncio.sleep(0)
        return self.get_component_info(
            item=item,
            base_unit_price=base_unit_price,
            sourcing_mode=sourcing_mode,
            category=self._to_category(category) if category is not None else None,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _stable_hash(self, value: str) -> float:
        """Return a stable float in [0, 1) derived from *value*.

        Used to make deterministic pseudo-random decisions (e.g. EU
        availability) that vary per component but are reproducible.
        """
        digest = hashlib.sha256(value.encode()).hexdigest()
        return int(digest[:8], 16) / 0xFFFFFFFF

    def _is_eu_available(self, item: BomItem, category: ComponentCategory) -> bool:
        """Determine (deterministically) whether EU sourcing is available."""
        base_probability = _EU_AVAILABILITY.get(category.value, 0.65)
        # Use MPN or ref_des as seed for deterministic outcome.
        seed = item.manufacturer_part_number or item.reference_designator
        return self._stable_hash(seed) < base_probability

    def _simulate_distributor_results(
        self,
        item: BomItem,
        base_unit_price: float,
        category: ComponentCategory,
    ) -> List[DistributorResult]:
        """Return simulated distributor results for *item*.

        Global distributors always return the base price.  EU distributors
        apply a category-specific premium.  EU availability is deterministic
        per component.
        """
        results: List[DistributorResult] = []

        # Global distributor (always available).
        results.append(
            DistributorResult(
                distributor_name="digikey",
                is_eu=False,
                unit_price=base_unit_price,
                in_stock=True,
            )
        )
        results.append(
            DistributorResult(
                distributor_name="mouser",
                is_eu=False,
                unit_price=base_unit_price * 1.01,  # slight variation
                in_stock=True,
            )
        )

        # EU distributor – only added when the component is EU-available.
        if self._is_eu_available(item, category):
            eu_premium = _EU_PREMIUM.get(category.value, 0.12)
            eu_price = base_unit_price * (1.0 + eu_premium)
            results.append(
                DistributorResult(
                    distributor_name="farnell",
                    is_eu=True,
                    unit_price=eu_price,
                    in_stock=True,
                )
            )
            results.append(
                DistributorResult(
                    distributor_name="rs_components",
                    is_eu=True,
                    unit_price=eu_price * 1.01,  # slight variation
                    in_stock=True,
                )
            )

        return results

    def _build_provenance_score(
        self,
        item: BomItem,
        distributor_results: List[DistributorResult],
        sourcing_mode: SourcingMode,
        base_unit_price: float,
    ) -> ProvenanceScore:
        """Apply sourcing-mode logic and return a :class:`ProvenanceScore`."""
        eu_results = [r for r in distributor_results if r.is_eu]
        global_results = [r for r in distributor_results if not r.is_eu]

        eu_available = bool(eu_results)
        best_eu = min(eu_results, key=lambda r: r.unit_price) if eu_results else None
        best_global = (
            min(global_results, key=lambda r: r.unit_price) if global_results else None
        )

        eu_unit_price = best_eu.unit_price if best_eu else None
        global_unit_price = best_global.unit_price if best_global else base_unit_price

        # Compute delta percentage: how much more expensive EU is vs global.
        eu_price_delta_pct: Optional[float] = None
        if eu_unit_price is not None and global_unit_price and global_unit_price > 0:
            eu_price_delta_pct = (eu_unit_price - global_unit_price) / global_unit_price * 100.0

        # ------------------------------------------------------------------
        # Apply sourcing-mode rules
        # ------------------------------------------------------------------
        flagged = False
        flag_reason: Optional[str] = None
        provenance_risk = ProvenanceRisk.LOW

        if sourcing_mode == SourcingMode.GLOBAL:
            # No restrictions – use global best price.
            provenance_risk = ProvenanceRisk.LOW

        elif sourcing_mode == SourcingMode.EU_PREFERRED:
            if not eu_available:
                provenance_risk = ProvenanceRisk.MEDIUM
                flagged = True
                flag_reason = "EU sourcing unavailable for this component"
            elif eu_price_delta_pct is not None and eu_price_delta_pct > self.eu_premium_threshold * 100:
                # EU price exceeds threshold – fall back to global.
                flagged = True
                flag_reason = (
                    f"EU price premium ({eu_price_delta_pct:.1f}%) exceeds threshold "
                    f"({self.eu_premium_threshold * 100:.0f}%); using global price"
                )
                provenance_risk = ProvenanceRisk.MEDIUM
            # Otherwise EU sourcing is used and within budget.

        elif sourcing_mode == SourcingMode.EU_ONLY:
            if not eu_available:
                provenance_risk = ProvenanceRisk.HIGH
                flagged = True
                flag_reason = "No EU/UK source available – provenance gap"
            else:
                provenance_risk = ProvenanceRisk.LOW

        return ProvenanceScore(
            sourcing_mode=sourcing_mode,
            eu_available=eu_available,
            eu_distributor=best_eu.display_name if best_eu else None,
            global_distributor=best_global.display_name if best_global else None,
            eu_unit_price=eu_unit_price,
            global_unit_price=global_unit_price,
            eu_price_delta_pct=eu_price_delta_pct,
            provenance_risk=provenance_risk,
            flagged=flagged,
            flag_reason=flag_reason,
        )
