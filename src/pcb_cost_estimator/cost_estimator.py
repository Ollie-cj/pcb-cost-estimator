"""Deterministic cost estimation engine for PCB components."""

import re
import logging
from typing import Optional, List, Dict, Tuple
from datetime import datetime

from .models import (
    BomItem,
    BomParseResult,
    ComponentCategory,
    PackageType,
    PriceBreak,
    ComponentCostEstimate,
    AssemblyCost,
    OverheadCosts,
    CostEstimate,
)
from .config import CostModelConfig, CategoryPricing, PackagePricing


logger = logging.getLogger(__name__)

# Optional LLM enrichment import
try:
    from .llm_enrichment import LLMEnrichmentService
    LLM_ENRICHMENT_AVAILABLE = True
except ImportError:
    LLM_ENRICHMENT_AVAILABLE = False
    logger.debug("LLM enrichment not available")


class ComponentClassifier:
    """Classifies components based on MPN patterns and descriptions."""

    # MPN patterns for component categories
    MPN_PATTERNS = {
        ComponentCategory.RESISTOR: [
            r"^RC\d+",  # RC0603, RC0805, etc.
            r"^ERJ-\d+",  # Panasonic ERJ series
            r"^CRCW\d+",  # Vishay CRCW series
            r"^RK73[HGB]",  # KOA Speer RK73 series
            r"^\d+[kKmM]?\d*R?$",  # Common value patterns: 10k, 100R, 1M
        ],
        ComponentCategory.CAPACITOR: [
            r"^C\d{4}",  # C0603, C0805, etc.
            r"^GRM\d+",  # Murata GRM series
            r"^CL\d+",  # Samsung CL series
            r"^CC\d+",  # Yageo CC series
            r"^GCM\d+",  # Murata GCM series
            r"^\d+[pnuμ]?F",  # Common capacitor values: 100nF, 10uF, 22pF
        ],
        ComponentCategory.INDUCTOR: [
            r"^LQH\d+",  # Murata LQH series
            r"^MLZ\d+",  # TDK MLZ series
            r"^CDRH\d+",  # Sumida CDRH series
            r"^\d+[unm]?H",  # Common inductor values: 10uH, 100nH
        ],
        ComponentCategory.IC: [
            r"^LM\d+",  # LM series (linear regulators, op-amps, etc.)
            r"^TPS\d+",  # TI TPS series (power)
            r"^STM32",  # STM32 microcontrollers
            r"^ATMEGA",  # Atmel/Microchip AVR
            r"^PIC\d+",  # Microchip PIC
            r"^74[A-Z]+\d+",  # Logic ICs (74HC, 74LS, etc.)
            r"^AD\d+",  # Analog Devices
            r"^MAX\d+",  # Maxim Integrated
        ],
        ComponentCategory.DIODE: [
            r"^1N\d+",  # Standard diode numbering (1N4148, 1N5819, etc.)
            r"^BAT\d+",  # Schottky diodes
            r"^BZX\d+",  # Zener diodes
            r"^SM[AB]\d+",  # Surface mount diodes
        ],
        ComponentCategory.TRANSISTOR: [
            r"^2N\d+",  # Standard transistor numbering (2N2222, 2N3904, etc.)
            r"^BC\d+",  # BC series
            r"^BSS\d+",  # Small signal MOSFETs
            r"^IRF\d+",  # Power MOSFETs
            r"^SI\d+",  # Vishay Si series
        ],
        ComponentCategory.LED: [
            r"^LED",  # LED prefix
            r"^APT\d+",  # LED part numbers
            r"^LTST",  # Lite-On LED series
        ],
        ComponentCategory.CRYSTAL: [
            r"^ABM[0-9]",  # Abracon crystals
            r"^ECS-\d+",  # ECS Inc. crystals
            r"^\d+\.?\d*MHZ",  # Frequency-based (16MHz, 8.000MHz, etc.)
        ],
        ComponentCategory.CONNECTOR: [
            r"^[0-9]{5,}-\d+",  # Common connector numbering (67996-410HLF, etc.)
            r"^USB\d*",  # USB connectors
            r"^HDMI",  # HDMI connectors
            r"^M20-\d+",  # Mill-Max connectors
        ],
        ComponentCategory.SWITCH: [
            r"^SW_",  # Switch prefix
            r"^EVQ",  # Panasonic switches
        ],
        ComponentCategory.RELAY: [
            r"^G[56]",  # Omron G5/G6 series
            r"^RELAY",  # Generic relay prefix
        ],
        ComponentCategory.FUSE: [
            r"^FUSE",  # Fuse prefix
            r"^0ZC[AFGJKM]",  # Littelfuse series
        ],
        ComponentCategory.TRANSFORMER: [
            r"^750\d+",  # Pulse transformers
            r"^XFMR",  # Transformer prefix
        ],
    }

    # Description keywords for component categories
    DESCRIPTION_KEYWORDS = {
        ComponentCategory.RESISTOR: ["resistor", "res", "ohm", "Ω"],
        ComponentCategory.CAPACITOR: ["capacitor", "cap", "farad", "ceramic", "electrolytic", "tantalum"],
        ComponentCategory.INDUCTOR: ["inductor", "choke", "coil", "henry"],
        ComponentCategory.IC: [
            "integrated circuit", "ic", "microcontroller", "mcu", "processor", "cpu",
            "regulator", "op-amp", "opamp", "amplifier", "driver", "controller",
            "logic", "memory", "eeprom", "flash", "dac", "adc", "converter"
        ],
        ComponentCategory.CONNECTOR: ["connector", "header", "socket", "plug", "receptacle", "usb", "hdmi"],
        ComponentCategory.DIODE: ["diode", "rectifier", "zener", "schottky", "tvs"],
        ComponentCategory.TRANSISTOR: ["transistor", "mosfet", "bjt", "fet", "jfet"],
        ComponentCategory.LED: ["led", "light emitting"],
        ComponentCategory.CRYSTAL: ["crystal", "oscillator", "resonator", "xtal"],
        ComponentCategory.SWITCH: ["switch", "button", "pushbutton"],
        ComponentCategory.RELAY: ["relay"],
        ComponentCategory.FUSE: ["fuse"],
        ComponentCategory.TRANSFORMER: ["transformer", "xfmr"],
    }

    def classify_component(
        self,
        item: BomItem,
        llm_enrichment: Optional['LLMEnrichmentService'] = None
    ) -> Tuple[ComponentCategory, Optional[Dict]]:
        """Classify a component based on MPN patterns and description.

        Args:
            item: BomItem to classify
            llm_enrichment: Optional LLM enrichment service for ambiguous components

        Returns:
            Tuple of (ComponentCategory classification, Optional LLM metadata)
        """
        # If category is already set and not UNKNOWN, return it
        if item.category != ComponentCategory.UNKNOWN:
            return item.category, None

        # Try MPN pattern matching
        if item.manufacturer_part_number:
            category = self._classify_by_mpn(item.manufacturer_part_number)
            if category != ComponentCategory.UNKNOWN:
                logger.debug(f"Classified {item.reference_designator} as {category} by MPN")
                return category, None

        # Try description keyword matching
        if item.description:
            category = self._classify_by_description(item.description)
            if category != ComponentCategory.UNKNOWN:
                logger.debug(f"Classified {item.reference_designator} as {category} by description")
                return category, None

        # Try reference designator prefix as fallback
        category = self._classify_by_ref_des(item.reference_designator)

        # If still UNKNOWN and LLM enrichment is available, try LLM classification
        if category == ComponentCategory.UNKNOWN and llm_enrichment:
            llm_result = llm_enrichment.classify_component(
                mpn=item.manufacturer_part_number or "",
                description=item.description or "",
                reference_designator=item.reference_designator
            )

            if llm_result and llm_result.confidence > 0.5:
                logger.info(
                    f"LLM classified {item.reference_designator} as {llm_result.category} "
                    f"(confidence: {llm_result.confidence:.2f}, cached: {llm_result.from_cache})"
                )
                return llm_result.category, {
                    "llm_classification": True,
                    "confidence": llm_result.confidence,
                    "reasoning": llm_result.reasoning,
                    "from_cache": llm_result.from_cache
                }

        logger.debug(f"Classified {item.reference_designator} as {category} by reference designator")
        return category, None

    def _classify_by_mpn(self, mpn: str) -> ComponentCategory:
        """Classify by manufacturer part number pattern matching.

        Args:
            mpn: Manufacturer part number

        Returns:
            ComponentCategory or UNKNOWN if no match
        """
        mpn_upper = mpn.upper().strip()

        for category, patterns in self.MPN_PATTERNS.items():
            for pattern in patterns:
                if re.match(pattern, mpn_upper, re.IGNORECASE):
                    return category

        return ComponentCategory.UNKNOWN

    def _classify_by_description(self, description: str) -> ComponentCategory:
        """Classify by description keyword matching.

        Args:
            description: Component description

        Returns:
            ComponentCategory or UNKNOWN if no match
        """
        desc_lower = description.lower().strip()

        for category, keywords in self.DESCRIPTION_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in desc_lower:
                    return category

        return ComponentCategory.UNKNOWN

    def _classify_by_ref_des(self, ref_des: str) -> ComponentCategory:
        """Classify by reference designator prefix.

        Args:
            ref_des: Reference designator

        Returns:
            ComponentCategory or UNKNOWN if no match
        """
        # Extract prefix letters from reference designator
        prefix_match = re.match(r"^([A-Z]+)", ref_des.upper())
        if not prefix_match:
            return ComponentCategory.UNKNOWN

        prefix = prefix_match.group(1)

        # Map common prefixes to categories
        prefix_map = {
            "R": ComponentCategory.RESISTOR,
            "C": ComponentCategory.CAPACITOR,
            "L": ComponentCategory.INDUCTOR,
            "U": ComponentCategory.IC,
            "IC": ComponentCategory.IC,
            "D": ComponentCategory.DIODE,
            "Q": ComponentCategory.TRANSISTOR,
            "LED": ComponentCategory.LED,
            "Y": ComponentCategory.CRYSTAL,
            "X": ComponentCategory.CRYSTAL,
            "XTAL": ComponentCategory.CRYSTAL,
            "J": ComponentCategory.CONNECTOR,
            "P": ComponentCategory.CONNECTOR,
            "CON": ComponentCategory.CONNECTOR,
            "SW": ComponentCategory.SWITCH,
            "S": ComponentCategory.SWITCH,
            "K": ComponentCategory.RELAY,
            "RLY": ComponentCategory.RELAY,
            "F": ComponentCategory.FUSE,
            "T": ComponentCategory.TRANSFORMER,
        }

        return prefix_map.get(prefix, ComponentCategory.UNKNOWN)


class PackageClassifier:
    """Classifies package types for assembly cost estimation."""

    # Package patterns by type
    PACKAGE_PATTERNS = {
        PackageType.SMD_SMALL: [
            r"^0201$", r"^0402$", r"^0603$",
        ],
        PackageType.SMD_MEDIUM: [
            r"^0805$", r"^1206$", r"^1210$",
        ],
        PackageType.SMD_LARGE: [
            r"^1812$", r"^2010$", r"^2512$", r"^2920$",
        ],
        PackageType.SOIC: [
            r"^SOIC", r"^SOP", r"^SO-\d+", r"^TSSOP", r"^SSOP",
        ],
        PackageType.QFP: [
            r"^QFP", r"^TQFP", r"^LQFP", r"^PQFP",
        ],
        PackageType.QFN: [
            r"^QFN", r"^DFN", r"^SON", r"^WSON", r"^VQFN",
        ],
        PackageType.BGA: [
            r"^BGA", r"^FBGA", r"^TFBGA", r"^LFBGA", r"^LGA",
        ],
        PackageType.THROUGH_HOLE: [
            r"^THT", r"^DIP", r"^TO-\d+", r"^PDIP", r"^AXIAL", r"^RADIAL",
        ],
        PackageType.CONNECTOR: [
            r"^CONN", r"^HEADER", r"^SOCKET",
        ],
    }

    def classify_package(self, item: BomItem) -> PackageType:
        """Classify package type for assembly cost estimation.

        Args:
            item: BomItem to classify

        Returns:
            PackageType classification
        """
        # Check if package field exists
        if not item.package:
            # Guess based on category
            return self._guess_package_by_category(item.category)

        package_upper = item.package.upper().strip()

        # Try pattern matching
        for pkg_type, patterns in self.PACKAGE_PATTERNS.items():
            for pattern in patterns:
                if re.match(pattern, package_upper):
                    return pkg_type

        # Check for connector category
        if item.category == ComponentCategory.CONNECTOR:
            return PackageType.CONNECTOR

        return PackageType.UNKNOWN

    def _guess_package_by_category(self, category: ComponentCategory) -> PackageType:
        """Guess package type based on component category.

        Args:
            category: Component category

        Returns:
            PackageType best guess
        """
        category_defaults = {
            ComponentCategory.RESISTOR: PackageType.SMD_MEDIUM,
            ComponentCategory.CAPACITOR: PackageType.SMD_MEDIUM,
            ComponentCategory.INDUCTOR: PackageType.SMD_MEDIUM,
            ComponentCategory.DIODE: PackageType.SMD_MEDIUM,
            ComponentCategory.LED: PackageType.SMD_MEDIUM,
            ComponentCategory.IC: PackageType.SOIC,
            ComponentCategory.CONNECTOR: PackageType.CONNECTOR,
            ComponentCategory.CRYSTAL: PackageType.SMD_MEDIUM,
            ComponentCategory.SWITCH: PackageType.THROUGH_HOLE,
            ComponentCategory.RELAY: PackageType.THROUGH_HOLE,
            ComponentCategory.FUSE: PackageType.SMD_MEDIUM,
            ComponentCategory.TRANSFORMER: PackageType.THROUGH_HOLE,
        }

        return category_defaults.get(category, PackageType.OTHER)


class CostEstimator:
    """Deterministic cost estimation engine."""

    def __init__(
        self,
        config: CostModelConfig,
        llm_enrichment: Optional['LLMEnrichmentService'] = None
    ):
        """Initialize cost estimator with configuration.

        Args:
            config: Cost model configuration
            llm_enrichment: Optional LLM enrichment service for enhanced analysis
        """
        self.config = config
        self.component_classifier = ComponentClassifier()
        self.package_classifier = PackageClassifier()
        self.llm_enrichment = llm_enrichment

    def estimate_bom_cost(
        self,
        bom_result: BomParseResult,
        board_quantity: int = 1,
    ) -> CostEstimate:
        """Estimate total cost for a BoM.

        Args:
            bom_result: Parsed BoM result
            board_quantity: Number of boards to manufacture

        Returns:
            Complete cost estimate with itemized breakdown
        """
        logger.info(f"Estimating cost for {len(bom_result.items)} components, {board_quantity} boards")

        # Filter out DNP items
        active_items = [item for item in bom_result.items if not item.dnp]
        logger.info(f"Active components (excluding DNP): {len(active_items)}")

        # Estimate individual component costs
        component_costs: List[ComponentCostEstimate] = []
        warnings: List[str] = []

        for item in active_items:
            try:
                cost_estimate, item_warnings = self._estimate_component_cost(item, board_quantity)
                component_costs.append(cost_estimate)
                warnings.extend(item_warnings)
            except Exception as e:
                logger.error(f"Error estimating cost for {item.reference_designator}: {e}")
                warnings.append(f"Could not estimate cost for {item.reference_designator}: {str(e)}")

        # Calculate total component costs
        total_component_cost_low = sum(c.total_cost_low for c in component_costs)
        total_component_cost_typical = sum(c.total_cost_typical for c in component_costs)
        total_component_cost_high = sum(c.total_cost_high for c in component_costs)

        # Calculate assembly costs
        assembly_cost = self._calculate_assembly_cost(component_costs)

        # Calculate overhead costs
        overhead_costs = self._calculate_overhead_costs(
            total_component_cost_typical,
            assembly_cost.total_assembly_cost_per_board,
        )

        # Calculate total costs per board
        total_cost_per_board_low = (
            total_component_cost_low +
            assembly_cost.total_assembly_cost_per_board +
            overhead_costs.total_overhead
        )
        total_cost_per_board_typical = (
            total_component_cost_typical +
            assembly_cost.total_assembly_cost_per_board +
            overhead_costs.total_overhead
        )
        total_cost_per_board_high = (
            total_component_cost_high +
            assembly_cost.total_assembly_cost_per_board +
            overhead_costs.total_overhead
        )

        # Check for obsolescence risks (if LLM enrichment enabled)
        obsolescence_notes = []
        if self.llm_enrichment:
            components_to_check = [
                {
                    "mpn": item.manufacturer_part_number or "",
                    "manufacturer": item.manufacturer or "",
                    "description": item.description or "",
                    "category": self.component_classifier.classify_component(item, None)[0].value,
                    "quantity": item.quantity
                }
                for item in active_items
                if item.manufacturer_part_number  # Only check components with MPN
            ]

            if components_to_check:
                logger.info(f"Checking obsolescence for {len(components_to_check)} components")
                obsolescence_results = self.llm_enrichment.batch_check_obsolescence(
                    components_to_check
                )

                for result in obsolescence_results:
                    if result.obsolescence_risk in ["high", "obsolete"]:
                        warning_msg = (
                            f"Obsolescence risk for {result.mpn}: {result.obsolescence_risk.upper()} "
                            f"(lifecycle: {result.lifecycle_status})"
                        )
                        warnings.append(warning_msg)

                        if result.alternatives:
                            alt_summary = ", ".join(
                                alt["mpn"] for alt in result.alternatives[:3]
                            )
                            obsolescence_notes.append(
                                f"{result.mpn}: Consider alternatives - {alt_summary}"
                            )
                    elif result.obsolescence_risk == "medium":
                        obsolescence_notes.append(
                            f"{result.mpn}: Medium obsolescence risk - monitor availability"
                        )

        # Combine warnings and notes
        all_warnings = list(bom_result.warnings) + warnings
        all_notes = obsolescence_notes

        return CostEstimate(
            file_path=bom_result.file_path,
            timestamp=datetime.now().isoformat(),
            currency="USD",
            component_costs=component_costs,
            assembly_cost=assembly_cost,
            overhead_costs=overhead_costs,
            total_component_cost_low=total_component_cost_low,
            total_component_cost_typical=total_component_cost_typical,
            total_component_cost_high=total_component_cost_high,
            total_cost_per_board_low=total_cost_per_board_low,
            total_cost_per_board_typical=total_cost_per_board_typical,
            total_cost_per_board_high=total_cost_per_board_high,
            warnings=all_warnings,
            notes=all_notes,
        )

    def _estimate_component_cost(
        self,
        item: BomItem,
        board_quantity: int,
    ) -> Tuple[ComponentCostEstimate, List[str]]:
        """Estimate cost for a single component.

        Args:
            item: BomItem to estimate
            board_quantity: Number of boards

        Returns:
            Tuple of (ComponentCostEstimate with price breaks, list of warnings)
        """
        warnings = []

        # Classify component (with optional LLM enrichment)
        category, llm_metadata = self.component_classifier.classify_component(
            item, self.llm_enrichment
        )
        package_type = self.package_classifier.classify_package(item)

        # Get base pricing for category
        base_pricing = self._get_category_pricing(category)

        # Get package multiplier
        package_multiplier = self._get_package_multiplier(package_type)

        # Calculate unit costs with package multiplier
        unit_cost_low = base_pricing.base_price_low * package_multiplier
        unit_cost_typical = base_pricing.base_price_typical * package_multiplier
        unit_cost_high = base_pricing.base_price_high * package_multiplier

        # Calculate total costs (per board)
        total_cost_low = unit_cost_low * item.quantity
        total_cost_typical = unit_cost_typical * item.quantity
        total_cost_high = unit_cost_high * item.quantity

        # Calculate quantity break pricing
        price_breaks = self._calculate_price_breaks(
            unit_cost_typical,
            item.quantity,
            board_quantity,
        )

        # Build notes list
        notes = list(item.notes) if item.notes else []
        if llm_metadata:
            notes.append(
                f"LLM classification (confidence: {llm_metadata['confidence']:.2f})"
            )

        # LLM price reasonableness check (if enabled)
        if self.llm_enrichment and item.manufacturer_part_number:
            price_check = self.llm_enrichment.check_price_reasonableness(
                mpn=item.manufacturer_part_number,
                description=item.description or "",
                category=category.value,
                package_type=package_type.value,
                unit_cost_low=unit_cost_low,
                unit_cost_typical=unit_cost_typical,
                unit_cost_high=unit_cost_high,
                quantity=item.quantity
            )

            if price_check and not price_check.is_reasonable:
                warning_msg = (
                    f"{item.reference_designator} ({item.manufacturer_part_number}): "
                    f"Price may be unreasonable - {price_check.reasoning}"
                )
                warnings.append(warning_msg)
                notes.append(f"Price check: {price_check.reasoning[:100]}")

                if price_check.expected_price_range:
                    notes.append(
                        f"Expected range: ${price_check.expected_price_range['low']:.4f} - "
                        f"${price_check.expected_price_range['high']:.4f}"
                    )

        estimate = ComponentCostEstimate(
            reference_designator=item.reference_designator,
            quantity=item.quantity,
            category=category,
            package_type=package_type,
            unit_cost_low=unit_cost_low,
            unit_cost_typical=unit_cost_typical,
            unit_cost_high=unit_cost_high,
            total_cost_low=total_cost_low,
            total_cost_typical=total_cost_typical,
            total_cost_high=total_cost_high,
            price_breaks=price_breaks,
            manufacturer=item.manufacturer,
            manufacturer_part_number=item.manufacturer_part_number,
            description=item.description,
            notes=notes,
        )

        return estimate, warnings

    def _get_category_pricing(self, category: ComponentCategory) -> CategoryPricing:
        """Get base pricing for a component category.

        Args:
            category: Component category

        Returns:
            CategoryPricing for the category
        """
        category_str = category.value if isinstance(category, ComponentCategory) else str(category)

        if category_str in self.config.category_pricing:
            return self.config.category_pricing[category_str]

        # Return default pricing for unknown categories
        logger.warning(f"No pricing found for category {category_str}, using defaults")
        return CategoryPricing(
            base_price_low=0.01,
            base_price_typical=0.10,
            base_price_high=1.00,
        )

    def _get_package_multiplier(self, package_type: PackageType) -> float:
        """Get pricing multiplier for package type.

        Args:
            package_type: Package type

        Returns:
            Pricing multiplier
        """
        package_str = package_type.value if isinstance(package_type, PackageType) else str(package_type)

        if package_str in self.config.package_pricing:
            return self.config.package_pricing[package_str].multiplier

        # Return default multiplier
        return 1.0

    def _calculate_price_breaks(
        self,
        unit_price: float,
        qty_per_board: int,
        board_quantity: int,
    ) -> List[PriceBreak]:
        """Calculate quantity break pricing for component.

        Args:
            unit_price: Base unit price
            qty_per_board: Quantity per board
            board_quantity: Number of boards

        Returns:
            List of price breaks for quantity tiers
        """
        price_breaks: List[PriceBreak] = []

        tiers = self.config.quantity_breaks.tiers
        discounts = self.config.quantity_breaks.discount_curve

        for tier_qty, discount in zip(tiers, discounts):
            # Calculate total quantity needed
            total_qty = qty_per_board * tier_qty

            # Apply volume discount
            tier_unit_price = unit_price * discount
            tier_total_price = tier_unit_price * total_qty

            price_breaks.append(
                PriceBreak(
                    quantity=tier_qty,
                    unit_price=tier_unit_price,
                    total_price=tier_total_price,
                )
            )

        return price_breaks

    def _calculate_assembly_cost(
        self,
        component_costs: List[ComponentCostEstimate],
    ) -> AssemblyCost:
        """Calculate assembly cost based on component mix.

        Args:
            component_costs: List of component cost estimates

        Returns:
            Assembly cost breakdown
        """
        # Count components by package type
        package_counts = {
            PackageType.SMD_SMALL: 0,
            PackageType.SMD_MEDIUM: 0,
            PackageType.SMD_LARGE: 0,
            PackageType.SOIC: 0,
            PackageType.QFP: 0,
            PackageType.QFN: 0,
            PackageType.BGA: 0,
            PackageType.THROUGH_HOLE: 0,
            PackageType.CONNECTOR: 0,
            PackageType.OTHER: 0,
        }

        total_components = 0
        unique_components = len(component_costs)

        for cost in component_costs:
            quantity = cost.quantity
            total_components += quantity

            if cost.package_type in package_counts:
                package_counts[cost.package_type] += quantity

        # Calculate placement costs
        placement_cost = 0.0
        placement_cost += package_counts[PackageType.SMD_SMALL] * self.config.assembly.cost_per_smd_small
        placement_cost += package_counts[PackageType.SMD_MEDIUM] * self.config.assembly.cost_per_smd_medium
        placement_cost += package_counts[PackageType.SMD_LARGE] * self.config.assembly.cost_per_smd_large
        placement_cost += package_counts[PackageType.SOIC] * self.config.assembly.cost_per_soic
        placement_cost += package_counts[PackageType.QFP] * self.config.assembly.cost_per_qfp
        placement_cost += package_counts[PackageType.QFN] * self.config.assembly.cost_per_qfn
        placement_cost += package_counts[PackageType.BGA] * self.config.assembly.cost_per_bga
        placement_cost += package_counts[PackageType.THROUGH_HOLE] * self.config.assembly.cost_per_through_hole
        placement_cost += package_counts[PackageType.CONNECTOR] * self.config.assembly.cost_per_connector
        placement_cost += package_counts[PackageType.OTHER] * self.config.assembly.cost_per_other

        # Setup cost is one-time
        setup_cost = self.config.assembly.setup_cost

        # Total assembly cost per board
        total_assembly_cost = setup_cost + placement_cost

        return AssemblyCost(
            total_components=total_components,
            unique_components=unique_components,
            smd_small_count=package_counts[PackageType.SMD_SMALL],
            smd_medium_count=package_counts[PackageType.SMD_MEDIUM],
            smd_large_count=package_counts[PackageType.SMD_LARGE],
            soic_count=package_counts[PackageType.SOIC],
            qfp_count=package_counts[PackageType.QFP],
            qfn_count=package_counts[PackageType.QFN],
            bga_count=package_counts[PackageType.BGA],
            through_hole_count=package_counts[PackageType.THROUGH_HOLE],
            connector_count=package_counts[PackageType.CONNECTOR],
            other_count=package_counts[PackageType.OTHER],
            setup_cost=setup_cost,
            placement_cost_per_board=placement_cost,
            total_assembly_cost_per_board=total_assembly_cost,
        )

    def _calculate_overhead_costs(
        self,
        component_cost: float,
        assembly_cost: float,
    ) -> OverheadCosts:
        """Calculate overhead and markup costs.

        Args:
            component_cost: Total component cost
            assembly_cost: Total assembly cost

        Returns:
            Overhead costs breakdown
        """
        # NRE cost (one-time)
        nre_cost = self.config.overhead.nre_cost

        # Procurement overhead (percentage of component cost)
        procurement_overhead = component_cost * (self.config.overhead.procurement_overhead_percentage / 100.0)

        # Supply chain risk factor (default to low risk)
        supply_chain_risk_factor = self.config.overhead.supply_chain_risk_low

        # Calculate total overhead
        total_overhead = nre_cost + procurement_overhead

        return OverheadCosts(
            nre_cost=nre_cost,
            procurement_overhead=procurement_overhead,
            supply_chain_risk_factor=supply_chain_risk_factor,
            markup_percentage=self.config.overhead.procurement_overhead_percentage,
            total_overhead=total_overhead,
        )
