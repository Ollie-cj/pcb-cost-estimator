"""Command-line interface for PCB Cost Estimator."""

import logging
import sys
from pathlib import Path
from typing import Optional

import click

from pcb_cost_estimator import __version__
from pcb_cost_estimator.config import load_config
from pcb_cost_estimator.logger import setup_logging


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
    help="Output file for cost estimate",
)
@click.pass_context
def estimate(ctx: click.Context, bom_file: Path, output: Optional[Path]) -> None:
    """Estimate PCB cost from Bill of Materials (BOM) file.

    BOM_FILE: Path to the Bill of Materials file (CSV, Excel, etc.)
    """
    logger = logging.getLogger(__name__)
    config = ctx.obj.get("config", {})

    logger.info(f"Processing BOM file: {bom_file}")

    # Placeholder for actual implementation
    click.echo(f"Estimating cost for BOM: {bom_file}")
    click.echo("This feature is not yet implemented.")

    if output:
        logger.info(f"Output will be written to: {output}")


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
    click.echo(f"API Provider: {config.get('api', {}).get('provider', 'not set')}")
    click.echo(f"Model: {config.get('api', {}).get('model', 'not set')}")
    click.echo(f"Markup Percentage: {config.get('pricing', {}).get('markup_percentage', 'not set')}%")
    logger.info("Configuration validation successful")


if __name__ == "__main__":
    main()
