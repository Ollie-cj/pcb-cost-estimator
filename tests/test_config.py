"""Tests for configuration management."""

import pytest
from pathlib import Path
from pcb_cost_estimator.config import Config, APIConfig, PricingConfig, LoggingConfig


def test_api_config_defaults():
    """Test APIConfig default values."""
    config = APIConfig()
    assert config.provider == "openai"
    assert config.temperature == 0.7
    assert config.max_tokens == 2000


def test_pricing_config_defaults():
    """Test PricingConfig default values."""
    config = PricingConfig()
    assert config.markup_percentage == 20.0
    assert config.currency == "USD"
    assert config.base_setup_cost == 50.0


def test_logging_config_defaults():
    """Test LoggingConfig default values."""
    config = LoggingConfig()
    assert config.level == "INFO"
    assert config.console_output is True


def test_config_validation():
    """Test configuration validation."""
    config = Config()
    assert config.api.provider == "openai"
    assert config.pricing.markup_percentage == 20.0
    assert config.logging.level == "INFO"


def test_invalid_provider():
    """Test invalid API provider raises ValueError."""
    with pytest.raises(ValueError):
        APIConfig(provider="invalid")


def test_invalid_log_level():
    """Test invalid log level raises ValueError."""
    with pytest.raises(ValueError):
        LoggingConfig(level="INVALID")
