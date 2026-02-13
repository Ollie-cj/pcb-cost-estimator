"""Configuration management for PCB Cost Estimator."""

import logging
from pathlib import Path
from typing import Any, Dict

import yaml
from pydantic import BaseModel, Field, validator


logger = logging.getLogger(__name__)


class APIConfig(BaseModel):
    """API configuration settings."""

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


class Config(BaseModel):
    """Main configuration model."""

    api: APIConfig = Field(default_factory=APIConfig)
    pricing: PricingConfig = Field(default_factory=PricingConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


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
