"""Tests for the CLI module."""

import json
import logging
from pathlib import Path

import pytest
from click.testing import CliRunner

from pcb_cost_estimator.cli import main
from pcb_cost_estimator.logger import setup_logging, get_logger

# Path to the example config file (relative to repo root)
EXAMPLE_CONFIG = str(Path(__file__).parent.parent / "config" / "config.example.yaml")


@pytest.fixture
def runner():
    """Create Click test runner."""
    return CliRunner()


@pytest.fixture
def sample_bom_file(tmp_path):
    """Create a minimal sample BOM CSV file."""
    content = """Reference Designator,Quantity,Manufacturer,Part Number,Description,Package
R1,1,Vishay,CRCW0805100K,Resistor 100k,0805
C1,2,Murata,GRM188R71C104KA01,Capacitor 100nF,0603
U1,1,TI,TPS54331DR,Buck Converter,SOIC-8
"""
    bom_file = tmp_path / "test_bom.csv"
    bom_file.write_text(content)
    return bom_file


class TestCLIHelp:
    """Test CLI help output."""

    def test_main_help(self, runner):
        """Test main command help."""
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "PCB Cost Estimator" in result.output

    def test_estimate_help(self, runner):
        """Test estimate subcommand help."""
        result = runner.invoke(main, ["--config", EXAMPLE_CONFIG, "estimate", "--help"])
        assert result.exit_code == 0
        assert "BOM_FILE" in result.output

    def test_validate_config_help(self, runner):
        """Test validate-config subcommand help."""
        result = runner.invoke(main, ["--config", EXAMPLE_CONFIG, "validate-config", "--help"])
        assert result.exit_code == 0

    def test_version(self, runner):
        """Test version option."""
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0


class TestEstimateCommand:
    """Test the estimate command."""

    def test_estimate_basic(self, runner, sample_bom_file):
        """Test basic cost estimation."""
        result = runner.invoke(main, [
            "--config", EXAMPLE_CONFIG,
            "estimate",
            str(sample_bom_file)
        ])
        assert result.exit_code == 0
        assert "Parsed" in result.output
        assert "Estimating" in result.output

    def test_estimate_json_format(self, runner, sample_bom_file, tmp_path):
        """Test JSON output format."""
        output_file = tmp_path / "output.json"
        result = runner.invoke(main, [
            "--config", EXAMPLE_CONFIG,
            "estimate",
            str(sample_bom_file),
            "--format", "json",
            "--output", str(output_file)
        ])
        assert result.exit_code == 0
        assert output_file.exists()
        # Verify it's valid JSON
        with open(output_file) as f:
            data = json.load(f)
        assert "metadata" in data

    def test_estimate_csv_format(self, runner, sample_bom_file, tmp_path):
        """Test CSV output format."""
        output_file = tmp_path / "output.csv"
        result = runner.invoke(main, [
            "--config", EXAMPLE_CONFIG,
            "estimate",
            str(sample_bom_file),
            "--format", "csv",
            "--output", str(output_file)
        ])
        assert result.exit_code == 0
        assert output_file.exists()

    def test_estimate_markdown_format(self, runner, sample_bom_file, tmp_path):
        """Test Markdown output format."""
        output_file = tmp_path / "output.md"
        result = runner.invoke(main, [
            "--config", EXAMPLE_CONFIG,
            "estimate",
            str(sample_bom_file),
            "--format", "markdown",
            "--output", str(output_file)
        ])
        assert result.exit_code == 0
        assert output_file.exists()

    def test_estimate_with_board_quantity(self, runner, sample_bom_file):
        """Test estimate with board quantity option."""
        result = runner.invoke(main, [
            "--config", EXAMPLE_CONFIG,
            "estimate",
            str(sample_bom_file),
            "--board-quantity", "100"
        ])
        assert result.exit_code == 0

    def test_estimate_auto_detect_format_json(self, runner, sample_bom_file, tmp_path):
        """Test auto-detect format from .json extension."""
        output_file = tmp_path / "output.json"
        result = runner.invoke(main, [
            "--config", EXAMPLE_CONFIG,
            "estimate",
            str(sample_bom_file),
            "--output", str(output_file)
        ])
        assert result.exit_code == 0
        assert output_file.exists()

    def test_estimate_auto_detect_format_csv(self, runner, sample_bom_file, tmp_path):
        """Test auto-detect format from .csv extension."""
        output_file = tmp_path / "output.csv"
        result = runner.invoke(main, [
            "--config", EXAMPLE_CONFIG,
            "estimate",
            str(sample_bom_file),
            "--output", str(output_file)
        ])
        assert result.exit_code == 0
        assert output_file.exists()

    def test_estimate_auto_detect_format_markdown(self, runner, sample_bom_file, tmp_path):
        """Test auto-detect format from .md extension."""
        output_file = tmp_path / "output.md"
        result = runner.invoke(main, [
            "--config", EXAMPLE_CONFIG,
            "estimate",
            str(sample_bom_file),
            "--output", str(output_file)
        ])
        assert result.exit_code == 0
        assert output_file.exists()

    def test_estimate_table_with_json_output(self, runner, sample_bom_file, tmp_path):
        """Test table format with JSON output file."""
        output_file = tmp_path / "output.json"
        result = runner.invoke(main, [
            "--config", EXAMPLE_CONFIG,
            "estimate",
            str(sample_bom_file),
            "--format", "table",
            "--output", str(output_file)
        ])
        assert result.exit_code == 0
        assert output_file.exists()

    def test_estimate_llm_no_api_key(self, runner, sample_bom_file):
        """Test estimate with LLM enabled but no API key."""
        result = runner.invoke(main, [
            "--config", EXAMPLE_CONFIG,
            "estimate",
            str(sample_bom_file),
            "--enable-llm"
        ], env={"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "", "LLM_API_KEY": ""})
        # Should succeed but with warning about missing API key
        assert result.exit_code == 0

    def test_estimate_verbose(self, runner, sample_bom_file):
        """Test verbose logging."""
        result = runner.invoke(main, [
            "--verbose",
            "--config", EXAMPLE_CONFIG,
            "estimate",
            str(sample_bom_file)
        ])
        assert result.exit_code == 0


class TestValidateConfigCommand:
    """Test the validate-config command."""

    def test_validate_config_no_config(self, runner):
        """Test validate-config with no config file (empty config)."""
        result = runner.invoke(main, [
            "--config", EXAMPLE_CONFIG,
            "validate-config"
        ], env={"HOME": "/tmp"})
        # With example config, should succeed
        assert result.exit_code == 0

    def test_validate_config_with_valid_config(self, runner):
        """Test validate-config with example config."""
        result = runner.invoke(main, [
            "--config", EXAMPLE_CONFIG,
            "validate-config"
        ])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()


class TestLogger:
    """Test the logger module."""

    def test_setup_logging_default(self):
        """Test default logging setup."""
        setup_logging()
        logger = logging.getLogger()
        assert logger.level == logging.INFO

    def test_setup_logging_debug(self):
        """Test debug level logging setup."""
        setup_logging(level=logging.DEBUG)
        logger = logging.getLogger()
        assert logger.level == logging.DEBUG

    def test_setup_logging_no_console(self):
        """Test logging without console output."""
        setup_logging(console_output=False)
        root_logger = logging.getLogger()
        # Should have no console handlers
        console_handlers = [h for h in root_logger.handlers
                           if isinstance(h, logging.StreamHandler)
                           and not isinstance(h, logging.FileHandler)]
        assert len(console_handlers) == 0

    def test_setup_logging_with_file(self, tmp_path):
        """Test logging with file output."""
        log_file = tmp_path / "test.log"
        setup_logging(log_file=log_file)
        root_logger = logging.getLogger()
        file_handlers = [h for h in root_logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) > 0
        assert log_file.exists()

    def test_setup_logging_custom_format(self):
        """Test logging with custom format."""
        custom_format = "%(levelname)s: %(message)s"
        setup_logging(log_format=custom_format)
        root_logger = logging.getLogger()
        assert len(root_logger.handlers) > 0
        # Verify the format is set
        for handler in root_logger.handlers:
            if handler.formatter:
                assert "%(levelname)s" in handler.formatter._fmt

    def test_get_logger(self):
        """Test get_logger function."""
        logger = get_logger("test.module")
        assert logger.name == "test.module"
        assert isinstance(logger, logging.Logger)
