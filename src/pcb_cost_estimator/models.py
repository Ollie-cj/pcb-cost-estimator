"""Pydantic models for BoM data structures."""

from typing import Optional, Dict, List
from enum import Enum
from pydantic import BaseModel, Field, field_validator


class ManufacturerRegion(str, Enum):
    """Manufacturer headquarters region enumeration."""

    EU = "EU"
    UK = "UK"
    US = "US"
    CN = "CN"
    JP = "JP"
    KR = "KR"
    TW = "TW"
    OTHER = "OTHER"


class DistributorRegion(str, Enum):
    """Distributor operating region enumeration."""

    EU = "EU"
    UK = "UK"
    US = "US"
    APAC = "APAC"
    GLOBAL = "GLOBAL"


class SourcingMode(str, Enum):
    """Preferred sourcing mode for provenance scoring."""

    GLOBAL = "GLOBAL"
    EU_PREFERRED = "EU_PREFERRED"
    EU_ONLY = "EU_ONLY"


class ProvenanceRisk(str, Enum):
    """Supply chain risk level for EU-only sourcing."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class DistributorAvailability(BaseModel):
    """Availability information for a single distributor."""

    distributor_name: str = Field(..., description="Name of the distributor")
    distributor_region: DistributorRegion = Field(
        ..., description="Region where this distributor operates"
    )
    in_stock: bool = Field(..., description="Whether the part is currently in stock")
    stock_quantity: Optional[int] = Field(
        None, description="Available stock quantity", ge=0
    )
    unit_price: Optional[float] = Field(
        None, description="Unit price at this distributor", ge=0.0
    )
    currency: str = Field(default="EUR", description="Currency for unit_price")
    warehouse_location: Optional[str] = Field(
        None, description="Warehouse country code (e.g. UK, DE, NL)"
    )
    lead_time_days: Optional[int] = Field(
        None, description="Lead time in days when out of stock", ge=0
    )


class ProvenanceScore(BaseModel):
    """Provenance and supply-chain scoring for a component."""

    sourcing_mode: SourcingMode = Field(
        ..., description="Preferred sourcing mode applied when scoring"
    )
    eu_available: bool = Field(
        ..., description="Can this part be sourced from an EU distributor?"
    )
    eu_manufactured: bool = Field(
        ..., description="Is the manufacturer headquartered in Europe?"
    )
    eu_price_delta_pct: Optional[float] = Field(
        None,
        description="Percentage premium for EU sourcing vs cheapest global option",
    )
    provenance_risk: ProvenanceRisk = Field(
        ..., description="Supply chain risk for EU-only sourcing"
    )


class ComponentCategory(str, Enum):
    """Component category enumeration."""

    RESISTOR = "resistor"
    CAPACITOR = "capacitor"
    INDUCTOR = "inductor"
    IC = "ic"
    CONNECTOR = "connector"
    DIODE = "diode"
    TRANSISTOR = "transistor"
    LED = "led"
    CRYSTAL = "crystal"
    SWITCH = "switch"
    RELAY = "relay"
    FUSE = "fuse"
    TRANSFORMER = "transformer"
    OTHER = "other"
    UNKNOWN = "unknown"


class BomItem(BaseModel):
    """Canonical BoM item schema.

    Represents a single line item in a Bill of Materials with normalized fields.
    """

    reference_designator: str = Field(
        ...,
        description="Reference designator(s) for the component (e.g., R1, C1-C5, U1)",
        min_length=1,
    )
    quantity: int = Field(..., description="Quantity of this component", ge=1)
    manufacturer: Optional[str] = Field(
        None, description="Manufacturer name (e.g., Texas Instruments, Vishay)"
    )
    manufacturer_part_number: Optional[str] = Field(
        None, description="Manufacturer part number (MPN)", alias="mpn"
    )
    description: Optional[str] = Field(None, description="Component description")
    package: Optional[str] = Field(
        None, description="Package type or footprint (e.g., 0805, SOIC-8, QFN-32)"
    )
    value: Optional[str] = Field(
        None, description="Component value (e.g., 10k, 100nF, 3.3V)"
    )
    category: ComponentCategory = Field(
        default=ComponentCategory.UNKNOWN, description="Component category"
    )
    dnp: bool = Field(
        default=False,
        description="Do Not Place / Do Not Install flag",
    )
    line_number: Optional[int] = Field(
        None, description="Original line number from source file"
    )
    notes: Optional[str] = Field(None, description="Additional notes or warnings")

    # Provenance metadata (optional – does not affect existing functionality)
    manufacturer_country: Optional[str] = Field(
        None,
        description="ISO 3166-1 alpha-2 country code where the manufacturer is headquartered",
        min_length=2,
        max_length=2,
    )
    manufacturer_region: Optional[ManufacturerRegion] = Field(
        None, description="Manufacturer headquarters region derived from country"
    )
    available_distributors: List[DistributorAvailability] = Field(
        default_factory=list,
        description="Distributors that stock this part and their availability",
    )

    @field_validator("reference_designator")
    @classmethod
    def validate_ref_des(cls, v: str) -> str:
        """Validate and normalize reference designator."""
        if not v or not v.strip():
            raise ValueError("Reference designator cannot be empty")
        return v.strip()

    @field_validator("manufacturer", "manufacturer_part_number", "description", "package", "value")
    @classmethod
    def strip_strings(cls, v: Optional[str]) -> Optional[str]:
        """Strip whitespace from string fields."""
        if v is not None:
            stripped = v.strip()
            return stripped if stripped else None
        return None

    class Config:
        """Pydantic model configuration."""

        populate_by_name = True
        use_enum_values = True


class BomParseResult(BaseModel):
    """Result of parsing a BoM file.

    Contains both successfully parsed items and any errors/warnings encountered.
    """

    items: list[BomItem] = Field(default_factory=list, description="Successfully parsed BoM items")
    warnings: list[str] = Field(
        default_factory=list, description="Non-fatal warnings during parsing"
    )
    errors: list[str] = Field(default_factory=list, description="Fatal errors during parsing")
    file_path: Optional[str] = Field(None, description="Path to the source file")
    total_rows_processed: int = Field(0, description="Total number of rows processed")

    @property
    def success(self) -> bool:
        """Check if parsing was successful (no fatal errors)."""
        return len(self.errors) == 0

    @property
    def item_count(self) -> int:
        """Get the number of successfully parsed items."""
        return len(self.items)


class PackageType(str, Enum):
    """Package type enumeration for assembly cost calculation."""

    SMD_SMALL = "smd_small"  # 0201, 0402, 0603
    SMD_MEDIUM = "smd_medium"  # 0805, 1206, 1210
    SMD_LARGE = "smd_large"  # 2010, 2512, etc.
    SOIC = "soic"  # SOIC, SOP packages
    QFP = "qfp"  # QFP, TQFP packages
    QFN = "qfn"  # QFN, DFN packages
    BGA = "bga"  # BGA, LGA packages
    THROUGH_HOLE = "through_hole"  # THT components
    CONNECTOR = "connector"  # Connectors
    OTHER = "other"  # Other package types
    UNKNOWN = "unknown"


class PriceBreak(BaseModel):
    """Price break for a specific quantity tier."""

    quantity: int = Field(..., description="Minimum quantity for this price tier", ge=1)
    unit_price: float = Field(..., description="Unit price at this quantity", ge=0.0)
    total_price: float = Field(..., description="Total price for this quantity", ge=0.0)


class ComponentCostEstimate(BaseModel):
    """Cost estimate for a single component with confidence intervals."""

    reference_designator: str = Field(..., description="Component reference designator")
    quantity: int = Field(..., description="Quantity of this component", ge=1)
    category: ComponentCategory = Field(..., description="Component category")
    package_type: PackageType = Field(..., description="Package type for assembly cost")

    # Cost estimates with confidence intervals
    unit_cost_low: float = Field(..., description="Low estimate of unit cost", ge=0.0)
    unit_cost_typical: float = Field(..., description="Typical/expected unit cost", ge=0.0)
    unit_cost_high: float = Field(..., description="High estimate of unit cost", ge=0.0)

    # Total costs
    total_cost_low: float = Field(..., description="Low estimate of total cost", ge=0.0)
    total_cost_typical: float = Field(..., description="Typical/expected total cost", ge=0.0)
    total_cost_high: float = Field(..., description="High estimate of total cost", ge=0.0)

    # Quantity break pricing (5 tiers: 1, 10, 100, 1000, 10000)
    price_breaks: List[PriceBreak] = Field(
        default_factory=list,
        description="Quantity break pricing tiers"
    )

    # Metadata
    manufacturer: Optional[str] = Field(None, description="Manufacturer name")
    manufacturer_part_number: Optional[str] = Field(None, description="MPN")
    description: Optional[str] = Field(None, description="Component description")
    notes: Optional[str] = Field(None, description="Additional notes or warnings")


class AssemblyCost(BaseModel):
    """Assembly cost breakdown for the entire board."""

    total_components: int = Field(..., description="Total number of components", ge=0)
    unique_components: int = Field(..., description="Number of unique components", ge=0)

    # Component counts by package complexity
    smd_small_count: int = Field(default=0, description="Count of small SMD components", ge=0)
    smd_medium_count: int = Field(default=0, description="Count of medium SMD components", ge=0)
    smd_large_count: int = Field(default=0, description="Count of large SMD components", ge=0)
    soic_count: int = Field(default=0, description="Count of SOIC packages", ge=0)
    qfp_count: int = Field(default=0, description="Count of QFP packages", ge=0)
    qfn_count: int = Field(default=0, description="Count of QFN packages", ge=0)
    bga_count: int = Field(default=0, description="Count of BGA packages", ge=0)
    through_hole_count: int = Field(default=0, description="Count of through-hole components", ge=0)
    connector_count: int = Field(default=0, description="Count of connectors", ge=0)
    other_count: int = Field(default=0, description="Count of other packages", ge=0)

    # Assembly costs
    setup_cost: float = Field(..., description="One-time assembly setup cost", ge=0.0)
    placement_cost_per_board: float = Field(..., description="Component placement cost per board", ge=0.0)
    total_assembly_cost_per_board: float = Field(..., description="Total assembly cost per board", ge=0.0)


class OverheadCosts(BaseModel):
    """Overhead and markup costs."""

    nre_cost: float = Field(default=0.0, description="Non-recurring engineering cost", ge=0.0)
    procurement_overhead: float = Field(default=0.0, description="Procurement overhead cost", ge=0.0)
    supply_chain_risk_factor: float = Field(
        default=1.0,
        description="Supply chain risk multiplier (1.0 = no risk)",
        ge=1.0,
        le=3.0
    )
    markup_percentage: float = Field(
        default=20.0,
        description="Markup percentage",
        ge=0.0,
        le=100.0
    )
    total_overhead: float = Field(..., description="Total overhead cost", ge=0.0)


class CostEstimate(BaseModel):
    """Complete cost estimate for a BoM with itemized breakdown."""

    # Metadata
    file_path: Optional[str] = Field(None, description="Source BoM file path")
    timestamp: Optional[str] = Field(None, description="Timestamp of estimate")
    currency: str = Field(default="USD", description="Currency for all prices")

    # Component costs
    component_costs: List[ComponentCostEstimate] = Field(
        default_factory=list,
        description="Individual component cost estimates"
    )

    # Assembly costs
    assembly_cost: AssemblyCost = Field(..., description="Assembly cost breakdown")

    # Overhead costs
    overhead_costs: OverheadCosts = Field(..., description="Overhead and markup costs")

    # Total costs (with confidence intervals)
    total_component_cost_low: float = Field(..., description="Low estimate of total component cost", ge=0.0)
    total_component_cost_typical: float = Field(..., description="Typical total component cost", ge=0.0)
    total_component_cost_high: float = Field(..., description="High estimate of total component cost", ge=0.0)

    total_cost_per_board_low: float = Field(..., description="Low estimate of cost per board", ge=0.0)
    total_cost_per_board_typical: float = Field(..., description="Typical cost per board", ge=0.0)
    total_cost_per_board_high: float = Field(..., description="High estimate of cost per board", ge=0.0)

    # Warnings and notes
    warnings: List[str] = Field(default_factory=list, description="Warnings about the estimate")
    notes: List[str] = Field(default_factory=list, description="Additional notes")
