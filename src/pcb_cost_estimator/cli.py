"""Command-line interface for PCB Cost Estimator."""

import logging
import os
import sys
from pathlib import Path
from typing import Optional

import click

from pcb_cost_estimator import __version__
from pcb_cost_estimator.config import load_config
from pcb_cost_estimator.logger import setup_logging
from pcb_cost_estimator.bom_parser import BomParser
from pcb_cost_estimator.cost_estimator import CostEstimator
from pcb_cost_estimator.llm_enrichment import create_enrichment_service
from pcb_cost_estimator.models import SourcingMode
from pcb_cost_estimator.reporting import generate_report


@click.group()
@click.version_option(version=__version__)
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    default="config/config.yaml",
    help="Path to configuration file",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging",
)
@click.pass_context
def main(ctx: click.Context, config: Path, verbose: bool) -> None:
    """PCB Cost Estimator - AI-powered PCB cost estimation tool.

    This tool helps estimate PCB manufacturing costs using AI models
    and manufacturer data.
    """
    # Ensure context object exists
    ctx.ensure_object(dict)

    # Set up logging
    log_level = logging.DEBUG if verbose else logging.INFO
    setup_logging(log_level)

    logger = logging.getLogger(__name__)
    logger.info(f"PCB Cost Estimator v{__version__}")

    # Load configuration
    try:
        ctx.obj["config"] = load_config(config)
        logger.debug(f"Loaded configuration from {config}")
    except FileNotFoundError:
        logger.warning(f"Configuration file not found: {config}")
        logger.warning("Using default configuration")
        ctx.obj["config"] = {}
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        sys.exit(1)


@main.command()
@click.argument("bom_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file for cost estimate (format auto-detected from extension or use --format)",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["table", "json", "csv", "markdown"]),
    default="table",
    help="Output format (default: table for CLI display)",
)
@click.option(
    "--board-quantity",
    "-q",
    type=int,
    default=1,
    help="Number of boards to manufacture",
)
@click.option(
    "--enable-llm",
    is_flag=True,
    help="Enable LLM enrichment features (requires API key)",
)
@click.option(
    "--llm-provider",
    type=click.Choice(["openai", "anthropic"]),
    help="LLM provider (overrides config)",
)
@click.option(
    "--llm-api-key",
    envvar="LLM_API_KEY",
    help="LLM API key (can also use OPENAI_API_KEY or ANTHROPIC_API_KEY env vars)",
)
@click.option(
    "--sourcing-mode",
    type=click.Choice(["global", "eu-preferred", "eu-only"], case_sensitive=False),
    default="global",
    show_default=True,
    help=(
        "Sourcing strategy for distributor selection. "
        "'global' uses the cheapest price from any distributor. "
        "'eu-preferred' prefers EU/UK distributors within a configurable premium threshold (default 30%). "
        "'eu-only' restricts to EU/UK distributors only and flags unavailable parts."
    ),
)
@click.pass_context
def estimate(
    ctx: click.Context,
    bom_file: Path,
    output: Optional[Path],
    format: str,
    board_quantity: int,
    enable_llm: bool,
    llm_provider: Optional[str],
    llm_api_key: Optional[str],
    sourcing_mode: str,
) -> None:
    """Estimate PCB cost from Bill of Materials (BOM) file.

    BOM_FILE: Path to the Bill of Materials file (CSV, Excel, etc.)
    """
    logger = logging.getLogger(__name__)
    config_dict = ctx.obj.get("config", {})

    # Map CLI sourcing-mode string to SourcingMode enum
    _sourcing_mode_map = {
        "global": SourcingMode.GLOBAL,
        "eu-preferred": SourcingMode.EU_PREFERRED,
        "eu-only": SourcingMode.EU_ONLY,
    }
    sourcing_mode_enum = _sourcing_mode_map[sourcing_mode.lower()]

    logger.info(f"Processing BOM file: {bom_file}")
    logger.info(f"Board quantity: {board_quantity}")
    logger.info(f"Sourcing mode: {sourcing_mode_enum.value}")

    try:
        # Parse BOM file
        parser = BomParser()
        bom_result = parser.parse_file(bom_file)

        if not bom_result.success:
            click.echo(f"Error parsing BOM file: {bom_result.errors}", err=True)
            sys.exit(1)

        click.echo(f"Parsed {len(bom_result.items)} components from BOM")

        # Get cost model configuration
        from pcb_cost_estimator.config import load_cost_model_config
        cost_config = load_cost_model_config()

        # Set up LLM enrichment if enabled
        llm_service = None
        if enable_llm or config_dict.get("llm_enrichment", {}).get("enabled", False):
            # Determine API key
            api_key = llm_api_key
            if not api_key:
                llm_config = config_dict.get("llm_enrichment", {})
                api_key = llm_config.get("api_key")

            # Try environment variables
            if not api_key:
                provider = llm_provider or config_dict.get("llm_enrichment", {}).get("provider", "openai")
                if provider == "openai":
                    api_key = os.environ.get("OPENAI_API_KEY")
                elif provider == "anthropic":
                    api_key = os.environ.get("ANTHROPIC_API_KEY")

            if api_key:
                llm_config = config_dict.get("llm_enrichment", {})
                provider = llm_provider or llm_config.get("provider", "openai")

                click.echo(f"Enabling LLM enrichment with {provider} provider")
                llm_service = create_enrichment_service(
                    provider_name=provider,
                    api_key=api_key,
                    model=llm_config.get("model"),
                    enabled=True,
                    temperature=llm_config.get("temperature", 0.0),
                    max_tokens=llm_config.get("max_tokens", 1000),
                    requests_per_minute=llm_config.get("requests_per_minute", 60),
                    max_retries=llm_config.get("max_retries", 3)
                )
            else:
                click.echo(
                    "Warning: LLM enrichment requested but no API key provided. "
                    "Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable.",
                    err=True
                )

        # Create cost estimator
        estimator = CostEstimator(cost_config, llm_enrichment=llm_service)

        # Estimate costs
        click.echo(f"Estimating costs (sourcing mode: {sourcing_mode_enum.value})...")
        cost_estimate = estimator.estimate_bom_cost(
            bom_result, board_quantity, sourcing_mode=sourcing_mode_enum
        )

        # Auto-detect format from output file extension if output specified
        report_format = format
        if output:
            ext = output.suffix.lower()
            if ext == '.json':
                report_format = 'json'
            elif ext == '.csv':
                report_format = 'csv'
            elif ext in ['.md', '.markdown']:
                report_format = 'markdown'
            # Otherwise use the specified format

        # Generate report in the specified format
        if report_format == 'table':
            # Display rich formatted table
            generate_report(cost_estimate, format='table')

            # Also save to file if output specified
            if output:
                if output.suffix.lower() == '.json':
                    generate_report(cost_estimate, format='json', output_path=output)
                    click.echo(f"\nReport also saved to: {output}")
        else:
            # Generate file-based report
            if not output:
                # If no output specified, use default filename
                output = Path(f"cost_estimate.{report_format}")

            generate_report(cost_estimate, format=report_format, output_path=output)
            click.echo(f"\n{report_format.upper()} report saved to: {output}")
            logger.info(f"Report written to {output}")

    except Exception as e:
        logger.exception(f"Error during cost estimation: {e}")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.pass_context
def validate_config(ctx: click.Context) -> None:
    """Validate the configuration file."""
    logger = logging.getLogger(__name__)
    config = ctx.obj.get("config", {})

    if not config:
        click.echo("No configuration loaded or configuration is empty.")
        sys.exit(1)

    click.echo("Configuration is valid!")
    click.echo()
    click.echo("API Configuration:")
    click.echo(f"  Provider: {config.get('api', {}).get('provider', 'not set')}")
    click.echo(f"  Model: {config.get('api', {}).get('model', 'not set')}")
    click.echo()
    click.echo("Pricing Configuration:")
    click.echo(f"  Markup Percentage: {config.get('pricing', {}).get('markup_percentage', 'not set')}%")
    click.echo()
    click.echo("LLM Enrichment:")
    llm_config = config.get('llm_enrichment', {})
    enabled = llm_config.get('enabled', False)
    click.echo(f"  Enabled: {enabled}")
    if enabled:
        click.echo(f"  Provider: {llm_config.get('provider', 'not set')}")
        click.echo(f"  Model: {llm_config.get('model', 'default')}")
        click.echo(f"  Classification: {llm_config.get('enable_classification', True)}")
        click.echo(f"  Price Checking: {llm_config.get('enable_price_checking', True)}")
        click.echo(f"  Obsolescence Detection: {llm_config.get('enable_obsolescence_detection', True)}")
        has_api_key = bool(llm_config.get('api_key')) or bool(
            os.environ.get('OPENAI_API_KEY') or os.environ.get('ANTHROPIC_API_KEY')
        )
        click.echo(f"  API Key Configured: {has_api_key}")
    logger.info("Configuration validation successful")


if __name__ == "__main__":
    main()
