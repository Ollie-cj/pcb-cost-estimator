"""Pydantic models for BoM data structures."""

from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field, field_validator


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
