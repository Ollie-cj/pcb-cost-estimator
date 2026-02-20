"""Configuration management for PCB Cost Estimator."""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel, Field, validator, field_validator


logger = logging.getLogger(__name__)


class APIConfig(BaseModel):
    """API configuration settings (legacy - kept for backward compatibility)."""

    provider: str = Field(
        default="openai",
        description="AI provider: 'openai' or 'anthropic'",
    )
    api_key: str = Field(
        default="",
        description="API key for the selected provider",
    )
    model: str = Field(
        default="gpt-4",
        description="Model name to use for estimation",
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Temperature for AI model responses",
    )
    max_tokens: int = Field(
        default=2000,
        ge=1,
        description="Maximum tokens for AI model responses",
    )

    @validator("provider")
    def validate_provider(cls, v: str) -> str:
        """Validate API provider."""
        if v.lower() not in ["openai", "anthropic"]:
            raise ValueError("Provider must be 'openai' or 'anthropic'")
        return v.lower()


class LLMEnrichmentConfig(BaseModel):
    """LLM enrichment configuration for component analysis."""

    enabled: bool = Field(
        default=False,
        description="Enable LLM-powered enrichment features"
    )
    provider: str = Field(
        default="openai",
        description="LLM provider: 'openai' or 'anthropic'"
    )
    api_key: Optional[str] = Field(
        default=None,
        description="API key for the LLM provider (can also be set via environment variable)"
    )
    model: Optional[str] = Field(
        default=None,
        description="Model name (uses provider default if not specified)"
    )
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Temperature for LLM responses (0.0 for deterministic)"
    )
    max_tokens: int = Field(
        default=1000,
        ge=100,
        le=4000,
        description="Maximum tokens per LLM request"
    )
    requests_per_minute: int = Field(
        default=60,
        ge=1,
        le=1000,
        description="Rate limit for API requests"
    )
    max_retries: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum retry attempts for failed requests"
    )
    cache_ttl_days: int = Field(
        default=30,
        ge=1,
        le=365,
        description="Cache time-to-live in days"
    )
    enable_classification: bool = Field(
        default=True,
        description="Enable LLM classification for ambiguous components"
    )
    enable_price_checking: bool = Field(
        default=True,
        description="Enable LLM price reasonableness checking"
    )
    enable_obsolescence_detection: bool = Field(
        default=True,
        description="Enable LLM obsolescence risk detection"
    )

    @validator("provider")
    def validate_provider(cls, v: str) -> str:
        """Validate LLM provider."""
        if v.lower() not in ["openai", "anthropic"]:
            raise ValueError("Provider must be 'openai' or 'anthropic'")
        return v.lower()


class PricingConfig(BaseModel):
    """Pricing configuration settings."""

    markup_percentage: float = Field(
        default=20.0,
        ge=0.0,
        le=100.0,
        description="Markup percentage for cost estimation",
    )
    currency: str = Field(
        default="USD",
        description="Currency for pricing",
    )
    base_setup_cost: float = Field(
        default=50.0,
        ge=0.0,
        description="Base setup cost for PCB manufacturing",
    )


class LoggingConfig(BaseModel):
    """Logging configuration settings."""

    level: str = Field(
        default="INFO",
        description="Logging level",
    )
    file: str = Field(
        default="logs/pcb_cost_estimator.log",
        description="Log file path",
    )
    format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log message format",
    )
    console_output: bool = Field(
        default=True,
        description="Enable console output",
    )

    @validator("level")
    def validate_level(cls, v: str) -> str:
        """Validate logging level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Level must be one of {valid_levels}")
        return v.upper()


class CategoryPricing(BaseModel):
    """Pricing configuration for a component category."""

    base_price_low: float = Field(..., description="Low estimate of base price", ge=0.0)
    base_price_typical: float = Field(..., description="Typical base price", ge=0.0)
    base_price_high: float = Field(..., description="High estimate of base price", ge=0.0)


class PackagePricing(BaseModel):
    """Pricing adjustments for package types."""

    multiplier: float = Field(
        default=1.0,
        description="Price multiplier for this package type",
        ge=0.1,
        le=10.0
    )


class AssemblyPricing(BaseModel):
    """Assembly cost configuration."""

    setup_cost: float = Field(
        default=100.0,
        description="One-time assembly setup cost",
        ge=0.0
    )
    cost_per_smd_small: float = Field(
        default=0.01,
        description="Cost per small SMD component placement",
        ge=0.0
    )
    cost_per_smd_medium: float = Field(
        default=0.015,
        description="Cost per medium SMD component placement",
        ge=0.0
    )
    cost_per_smd_large: float = Field(
        default=0.02,
        description="Cost per large SMD component placement",
        ge=0.0
    )
    cost_per_soic: float = Field(
        default=0.025,
        description="Cost per SOIC package placement",
        ge=0.0
    )
    cost_per_qfp: float = Field(
        default=0.05,
        description="Cost per QFP package placement",
        ge=0.0
    )
    cost_per_qfn: float = Field(
        default=0.06,
        description="Cost per QFN package placement",
        ge=0.0
    )
    cost_per_bga: float = Field(
        default=0.15,
        description="Cost per BGA package placement",
        ge=0.0
    )
    cost_per_through_hole: float = Field(
        default=0.05,
        description="Cost per through-hole component placement",
        ge=0.0
    )
    cost_per_connector: float = Field(
        default=0.08,
        description="Cost per connector placement",
        ge=0.0
    )
    cost_per_other: float = Field(
        default=0.03,
        description="Cost per other package type placement",
        ge=0.0
    )


class QuantityBreakConfig(BaseModel):
    """Quantity break pricing configuration."""

    tiers: list[int] = Field(
        default=[1, 10, 100, 1000, 10000],
        description="Quantity tiers for price breaks"
    )
    discount_curve: list[float] = Field(
        default=[1.0, 0.85, 0.70, 0.55, 0.45],
        description="Discount multipliers for each tier (1.0 = no discount)"
    )

    @field_validator("discount_curve")
    @classmethod
    def validate_discount_curve(cls, v: list[float]) -> list[float]:
        """Validate discount curve is monotonically decreasing."""
        for i in range(len(v) - 1):
            if v[i] < v[i + 1]:
                raise ValueError("Discount curve must be monotonically decreasing")
        return v


class OverheadConfig(BaseModel):
    """Overhead and markup configuration."""

    nre_cost: float = Field(
        default=500.0,
        description="Non-recurring engineering cost",
        ge=0.0
    )
    procurement_overhead_percentage: float = Field(
        default=5.0,
        description="Procurement overhead as percentage of component cost",
        ge=0.0,
        le=50.0
    )
    supply_chain_risk_low: float = Field(
        default=1.0,
        description="Supply chain risk multiplier for low risk",
        ge=1.0,
        le=3.0
    )
    supply_chain_risk_medium: float = Field(
        default=1.2,
        description="Supply chain risk multiplier for medium risk",
        ge=1.0,
        le=3.0
    )
    supply_chain_risk_high: float = Field(
        default=1.5,
        description="Supply chain risk multiplier for high risk",
        ge=1.0,
        le=3.0
    )


class CostModelConfig(BaseModel):
    """Cost model configuration."""

    # Category-based pricing
    category_pricing: Dict[str, CategoryPricing] = Field(
        default_factory=dict,
        description="Base pricing for each component category"
    )

    # Package-based pricing multipliers
    package_pricing: Dict[str, PackagePricing] = Field(
        default_factory=dict,
        description="Pricing multipliers for package types"
    )

    # Assembly costs
    assembly: AssemblyPricing = Field(
        default_factory=AssemblyPricing,
        description="Assembly cost configuration"
    )

    # Quantity break pricing
    quantity_breaks: QuantityBreakConfig = Field(
        default_factory=QuantityBreakConfig,
        description="Quantity break pricing configuration"
    )

    # Overhead and markup
    overhead: OverheadConfig = Field(
        default_factory=OverheadConfig,
        description="Overhead and markup configuration"
    )


class Config(BaseModel):
    """Main configuration model."""

    api: APIConfig = Field(default_factory=APIConfig)
    pricing: PricingConfig = Field(default_factory=PricingConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    cost_model: CostModelConfig = Field(default_factory=CostModelConfig)
    llm_enrichment: LLMEnrichmentConfig = Field(
        default_factory=LLMEnrichmentConfig,
        description="LLM enrichment configuration"
    )


def load_config(config_path: Path) -> Dict[str, Any]:
    """Load configuration from YAML file.

    Args:
        config_path: Path to configuration file

    Returns:
        Dictionary containing configuration

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is invalid YAML
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    logger.debug(f"Loading configuration from {config_path}")

    with open(config_path, "r") as f:
        config_data = yaml.safe_load(f)

    # Validate configuration using Pydantic model
    config = Config(**config_data)

    return config.model_dump()


def save_config(config_data: Dict[str, Any], config_path: Path) -> None:
    """Save configuration to YAML file.

    Args:
        config_data: Configuration dictionary
        config_path: Path to save configuration file
    """
    # Validate configuration using Pydantic model
    config = Config(**config_data)

    # Ensure directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    logger.debug(f"Saving configuration to {config_path}")

    with open(config_path, "w") as f:
        yaml.dump(config.model_dump(), f, default_flow_style=False, sort_keys=False)

    logger.info(f"Configuration saved to {config_path}")


def load_cost_model_config(
    config_path: Optional[Path] = None,
) -> "CostModelConfig":
    """Load cost model configuration from YAML file.

    Falls back to searching for ``config/cost_model.yaml`` relative to the
    current working directory or the package root.  If no file is found, a
    ``CostModelConfig`` with sensible hard-coded defaults is returned so that
    the estimator is usable without any configuration files.

    Args:
        config_path: Optional explicit path to the cost model YAML file.

    Returns:
        CostModelConfig populated from the YAML file (or defaults).
    """
    search_paths = []
    if config_path:
        search_paths.append(config_path)

    # Relative to CWD
    search_paths.append(Path("config/cost_model.yaml"))
    # Relative to this file (src/pcb_cost_estimator -> repo root -> config/)
    _pkg_root = Path(__file__).parent.parent.parent
    search_paths.append(_pkg_root / "config" / "cost_model.yaml")

    for path in search_paths:
        if path.exists():
            logger.debug(f"Loading cost model config from {path}")
            try:
                with open(path, "r") as f:
                    data = yaml.safe_load(f)
                return CostModelConfig(**data)
            except Exception as exc:
                logger.warning(f"Failed to load cost model config from {path}: {exc}")

    logger.warning("No cost_model.yaml found; using built-in pricing defaults")
    # Build a reasonable default config matching the bundled cost_model.yaml
    return CostModelConfig(
        category_pricing={
            "resistor": CategoryPricing(base_price_low=0.001, base_price_typical=0.005, base_price_high=0.02),
            "capacitor": CategoryPricing(base_price_low=0.002, base_price_typical=0.01, base_price_high=0.05),
            "inductor": CategoryPricing(base_price_low=0.01, base_price_typical=0.05, base_price_high=0.20),
            "ic": CategoryPricing(base_price_low=0.50, base_price_typical=2.00, base_price_high=10.00),
            "connector": CategoryPricing(base_price_low=0.10, base_price_typical=0.50, base_price_high=2.00),
            "diode": CategoryPricing(base_price_low=0.01, base_price_typical=0.05, base_price_high=0.20),
            "transistor": CategoryPricing(base_price_low=0.02, base_price_typical=0.10, base_price_high=0.50),
            "led": CategoryPricing(base_price_low=0.02, base_price_typical=0.10, base_price_high=0.50),
            "crystal": CategoryPricing(base_price_low=0.10, base_price_typical=0.30, base_price_high=1.00),
            "switch": CategoryPricing(base_price_low=0.05, base_price_typical=0.20, base_price_high=1.00),
            "relay": CategoryPricing(base_price_low=0.50, base_price_typical=1.50, base_price_high=5.00),
            "fuse": CategoryPricing(base_price_low=0.05, base_price_typical=0.20, base_price_high=1.00),
            "transformer": CategoryPricing(base_price_low=0.50, base_price_typical=2.00, base_price_high=10.00),
            "other": CategoryPricing(base_price_low=0.05, base_price_typical=0.50, base_price_high=2.00),
            "unknown": CategoryPricing(base_price_low=0.10, base_price_typical=1.00, base_price_high=5.00),
        },
        package_pricing={
            "smd_small": PackagePricing(multiplier=1.0),
            "smd_medium": PackagePricing(multiplier=1.0),
            "smd_large": PackagePricing(multiplier=1.2),
            "soic": PackagePricing(multiplier=1.1),
            "qfp": PackagePricing(multiplier=1.3),
            "qfn": PackagePricing(multiplier=1.4),
            "bga": PackagePricing(multiplier=2.0),
            "through_hole": PackagePricing(multiplier=1.2),
            "connector": PackagePricing(multiplier=1.5),
            "other": PackagePricing(multiplier=1.0),
            "unknown": PackagePricing(multiplier=1.0),
        },
    )
