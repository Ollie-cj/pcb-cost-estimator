"""
Comprehensive cost reporting module with multiple output formats.

Generates cost reports in CLI table, JSON, CSV, and Markdown formats with
detailed cost breakdowns, volume tier comparisons, and risk analysis.
"""

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from .models import CostEstimate, ComponentCostEstimate, ComponentCategory

logger = logging.getLogger(__name__)


class CostReportGenerator:
    """
    Generates comprehensive cost reports with multiple output formats.

    Provides CLI tables, JSON reports, CSV exports, and Markdown documentation
    with volume tier comparisons, cost driver analysis, and risk assessment.
    """

    VOLUME_TIERS = [1, 100, 1000, 10000]

    def __init__(self, cost_estimate: CostEstimate):
        """
        Initialize the report generator.

        Args:
            cost_estimate: Complete cost estimate with itemized breakdown
        """
        self.cost_estimate = cost_estimate
        self.console = Console()

    def _calculate_volume_costs(self) -> Dict[int, Dict[str, float]]:
        """
        Calculate total costs at each volume tier.

        Returns:
            Dict mapping volume to cost breakdown (components, assembly, total)
        """
        volume_costs = {}

        for volume in self.VOLUME_TIERS:
            # Find component costs at this volume from price breaks
            component_cost = 0.0
            for comp in self.cost_estimate.component_costs:
                # Find the right price break for this volume
                applicable_price = None
                for pb in sorted(comp.price_breaks, key=lambda x: x.quantity):
                    if pb.quantity <= volume:
                        applicable_price = pb.unit_price
                    else:
                        break

                if applicable_price is not None:
                    component_cost += applicable_price * comp.quantity
                else:
                    # Fallback to typical cost
                    component_cost += comp.unit_cost_typical * comp.quantity

            # Assembly cost scales with volume
            assembly_setup = self.cost_estimate.assembly_cost.setup_cost
            assembly_per_board = self.cost_estimate.assembly_cost.placement_cost_per_board
            assembly_cost = (assembly_setup + assembly_per_board * volume) / volume

            # Overhead (simplified - typically would also scale)
            overhead = self.cost_estimate.overhead_costs.total_overhead

            total_per_board = component_cost + assembly_cost + overhead

            volume_costs[volume] = {
                'components': component_cost,
                'assembly': assembly_cost,
                'overhead': overhead,
                'total': total_per_board
            }

        return volume_costs

    def _calculate_cost_by_category(self) -> List[Dict[str, Any]]:
        """
        Calculate cost breakdown by component category.

        Returns:
            List of dicts with category, count, total_cost, percentage
        """
        category_costs: Dict[ComponentCategory, Dict[str, Any]] = {}
        total_cost = self.cost_estimate.total_component_cost_typical

        for comp in self.cost_estimate.component_costs:
            if comp.category not in category_costs:
                category_costs[comp.category] = {
                    'category': comp.category.value,
                    'count': 0,
                    'total_cost': 0.0
                }

            category_costs[comp.category]['count'] += comp.quantity
            category_costs[comp.category]['total_cost'] += comp.total_cost_typical

        # Calculate percentages and sort by cost
        result = []
        for cat_data in category_costs.values():
            cat_data['percentage'] = (cat_data['total_cost'] / total_cost * 100) if total_cost > 0 else 0
            result.append(cat_data)

        return sorted(result, key=lambda x: x['total_cost'], reverse=True)

    def _get_top_cost_drivers(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Identify top cost drivers (most expensive components).

        Args:
            limit: Maximum number of drivers to return

        Returns:
            List of dicts with component info and cost metrics
        """
        drivers = []
        total_cost = self.cost_estimate.total_component_cost_typical

        for comp in self.cost_estimate.component_costs:
            drivers.append({
                'reference': comp.reference_designator,
                'manufacturer': comp.manufacturer or 'Unknown',
                'mpn': comp.manufacturer_part_number or 'Unknown',
                'description': comp.description or '',
                'category': comp.category.value,
                'quantity': comp.quantity,
                'unit_cost': comp.unit_cost_typical,
                'total_cost': comp.total_cost_typical,
                'percentage': (comp.total_cost_typical / total_cost * 100) if total_cost > 0 else 0
            })

        return sorted(drivers, key=lambda x: x['total_cost'], reverse=True)[:limit]

    def _extract_risk_flags(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract risk flags from warnings and component notes.

        Returns:
            Dict with categories of risks (obsolescence, high_cost, single_source)
        """
        risks = {
            'obsolescence': [],
            'high_cost': [],
            'single_source': [],
            'price_warnings': [],
            'other': []
        }

        # Check warnings
        for warning in self.cost_estimate.warnings:
            warning_lower = warning.lower()

            if 'obsolete' in warning_lower or 'eol' in warning_lower or 'nrnd' in warning_lower:
                risks['obsolescence'].append({
                    'type': 'obsolescence',
                    'message': warning
                })
            elif 'price' in warning_lower or 'cost' in warning_lower:
                risks['price_warnings'].append({
                    'type': 'price',
                    'message': warning
                })
            elif 'single' in warning_lower or 'source' in warning_lower:
                risks['single_source'].append({
                    'type': 'single_source',
                    'message': warning
                })
            else:
                risks['other'].append({
                    'type': 'general',
                    'message': warning
                })

        # Check component notes for high-cost items
        for comp in self.cost_estimate.component_costs:
            if comp.total_cost_typical >= 10.0:  # Arbitrary threshold
                risks['high_cost'].append({
                    'type': 'high_cost',
                    'component': comp.reference_designator,
                    'mpn': comp.manufacturer_part_number or 'Unknown',
                    'cost': comp.total_cost_typical,
                    'message': f"High-cost component: ${comp.total_cost_typical:.2f}"
                })

        return risks

    def _get_assembly_breakdown(self) -> List[Dict[str, Any]]:
        """
        Get assembly cost breakdown by package type.

        Returns:
            List of dicts with package type, count, and cost contribution
        """
        asm = self.cost_estimate.assembly_cost
        breakdown = []

        package_data = [
            ('SMD Small (0201-0603)', asm.smd_small_count),
            ('SMD Medium (0805-1210)', asm.smd_medium_count),
            ('SMD Large (2010+)', asm.smd_large_count),
            ('SOIC', asm.soic_count),
            ('QFP', asm.qfp_count),
            ('QFN', asm.qfn_count),
            ('BGA', asm.bga_count),
            ('Through-Hole', asm.through_hole_count),
            ('Connector', asm.connector_count),
            ('Other', asm.other_count),
        ]

        for pkg_name, count in package_data:
            if count > 0:
                breakdown.append({
                    'package_type': pkg_name,
                    'count': count,
                    'percentage': (count / asm.total_components * 100) if asm.total_components > 0 else 0
                })

        return breakdown

    def generate_cli_table(self) -> None:
        """Generate and display formatted CLI table using rich."""

        # Title panel
        title = Panel(
            f"[bold cyan]PCB Cost Estimate Report[/bold cyan]\n"
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            expand=False
        )
        self.console.print(title)
        self.console.print()

        # Executive Summary
        self.console.print("[bold yellow]Executive Summary[/bold yellow]")
        summary_table = Table(show_header=True, header_style="bold magenta")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", justify="right")

        summary_table.add_row("Total Components", str(len(self.cost_estimate.component_costs)))
        summary_table.add_row("Unique Components", str(self.cost_estimate.assembly_cost.unique_components))
        summary_table.add_row("Currency", self.cost_estimate.currency)
        summary_table.add_row("", "")
        summary_table.add_row("[bold]Cost per Board (Typical)[/bold]",
                             f"[bold]${self.cost_estimate.total_cost_per_board_typical:.2f}[/bold]")
        summary_table.add_row("  Components", f"${self.cost_estimate.total_component_cost_typical:.2f}")
        summary_table.add_row("  Assembly", f"${self.cost_estimate.assembly_cost.total_assembly_cost_per_board:.2f}")
        summary_table.add_row("  Overhead", f"${self.cost_estimate.overhead_costs.total_overhead:.2f}")

        self.console.print(summary_table)
        self.console.print()

        # Volume Tier Comparison
        self.console.print("[bold yellow]Volume Tier Comparison[/bold yellow]")
        volume_costs = self._calculate_volume_costs()

        volume_table = Table(show_header=True, header_style="bold magenta")
        volume_table.add_column("Volume", justify="right", style="cyan")
        volume_table.add_column("Components", justify="right")
        volume_table.add_column("Assembly", justify="right")
        volume_table.add_column("Overhead", justify="right")
        volume_table.add_column("Total/Board", justify="right", style="bold green")

        for volume in self.VOLUME_TIERS:
            costs = volume_costs[volume]
            volume_table.add_row(
                f"{volume:,}",
                f"${costs['components']:.2f}",
                f"${costs['assembly']:.2f}",
                f"${costs['overhead']:.2f}",
                f"${costs['total']:.2f}"
            )

        self.console.print(volume_table)
        self.console.print()

        # Cost by Category
        self.console.print("[bold yellow]Cost Breakdown by Category[/bold yellow]")
        category_costs = self._calculate_cost_by_category()

        cat_table = Table(show_header=True, header_style="bold magenta")
        cat_table.add_column("Category", style="cyan")
        cat_table.add_column("Count", justify="right")
        cat_table.add_column("Total Cost", justify="right")
        cat_table.add_column("% of Total", justify="right")

        for cat in category_costs:
            cat_table.add_row(
                cat['category'].title(),
                str(cat['count']),
                f"${cat['total_cost']:.2f}",
                f"{cat['percentage']:.1f}%"
            )

        self.console.print(cat_table)
        self.console.print()

        # Top Cost Drivers
        self.console.print("[bold yellow]Top 10 Cost Drivers[/bold yellow]")
        drivers = self._get_top_cost_drivers(10)

        driver_table = Table(show_header=True, header_style="bold magenta")
        driver_table.add_column("Ref Des", style="cyan")
        driver_table.add_column("MPN")
        driver_table.add_column("Category")
        driver_table.add_column("Qty", justify="right")
        driver_table.add_column("Unit Cost", justify="right")
        driver_table.add_column("Total Cost", justify="right")
        driver_table.add_column("% of Total", justify="right")

        for driver in drivers:
            driver_table.add_row(
                driver['reference'],
                driver['mpn'][:20] if len(driver['mpn']) > 20 else driver['mpn'],
                driver['category'].title(),
                str(driver['quantity']),
                f"${driver['unit_cost']:.2f}",
                f"${driver['total_cost']:.2f}",
                f"{driver['percentage']:.1f}%"
            )

        self.console.print(driver_table)
        self.console.print()

        # Assembly Breakdown
        self.console.print("[bold yellow]Assembly Cost Breakdown[/bold yellow]")
        assembly_breakdown = self._get_assembly_breakdown()

        asm_table = Table(show_header=True, header_style="bold magenta")
        asm_table.add_column("Package Type", style="cyan")
        asm_table.add_column("Count", justify="right")
        asm_table.add_column("% of Total", justify="right")

        for item in assembly_breakdown:
            asm_table.add_row(
                item['package_type'],
                str(item['count']),
                f"{item['percentage']:.1f}%"
            )

        asm_table.add_row(
            "[bold]Total[/bold]",
            f"[bold]{self.cost_estimate.assembly_cost.total_components}[/bold]",
            "[bold]100.0%[/bold]"
        )
        asm_table.add_row("", "", "")
        asm_table.add_row(
            "Setup Cost (one-time)",
            f"${self.cost_estimate.assembly_cost.setup_cost:.2f}",
            ""
        )
        asm_table.add_row(
            "Placement Cost (per board)",
            f"${self.cost_estimate.assembly_cost.placement_cost_per_board:.2f}",
            ""
        )

        self.console.print(asm_table)
        self.console.print()

        # Risk Flags
        risks = self._extract_risk_flags()
        total_risks = sum(len(v) for v in risks.values())

        if total_risks > 0:
            self.console.print("[bold yellow]Risk Assessment[/bold yellow]")

            if risks['obsolescence']:
                self.console.print("[bold red]Obsolescence Risks:[/bold red]")
                for risk in risks['obsolescence']:
                    self.console.print(f"  ⚠ {risk['message']}")
                self.console.print()

            if risks['high_cost']:
                self.console.print("[bold orange1]High-Cost Components:[/bold orange1]")
                for risk in risks['high_cost'][:5]:  # Show top 5
                    self.console.print(
                        f"  💰 {risk['component']}: {risk['mpn']} - ${risk['cost']:.2f}"
                    )
                self.console.print()

            if risks['price_warnings']:
                self.console.print("[bold yellow]Price Warnings:[/bold yellow]")
                for risk in risks['price_warnings']:
                    self.console.print(f"  ⚠ {risk['message']}")
                self.console.print()

            if risks['single_source']:
                self.console.print("[bold orange1]Supply Chain Risks:[/bold orange1]")
                for risk in risks['single_source']:
                    self.console.print(f"  ⚠ {risk['message']}")
                self.console.print()

        # Warnings and Notes
        if self.cost_estimate.warnings:
            self.console.print(f"[bold yellow]Warnings ({len(self.cost_estimate.warnings)}):[/bold yellow]")
            for warning in self.cost_estimate.warnings:
                self.console.print(f"  ⚠ {warning}")
            self.console.print()

        if self.cost_estimate.notes:
            self.console.print(f"[bold cyan]Notes ({len(self.cost_estimate.notes)}):[/bold cyan]")
            for note in self.cost_estimate.notes[:5]:  # Show first 5
                self.console.print(f"  ℹ {note}")
            if len(self.cost_estimate.notes) > 5:
                self.console.print(f"  ... and {len(self.cost_estimate.notes) - 5} more")
            self.console.print()

    def generate_json_report(self, output_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Generate detailed JSON report with full breakdown.

        Args:
            output_path: Optional path to write JSON file

        Returns:
            Dict containing complete report data
        """
        volume_costs = self._calculate_volume_costs()
        category_costs = self._calculate_cost_by_category()
        cost_drivers = self._get_top_cost_drivers(10)
        risks = self._extract_risk_flags()
        assembly_breakdown = self._get_assembly_breakdown()

        report = {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'source_file': str(self.cost_estimate.file_path) if self.cost_estimate.file_path else None,
                'currency': self.cost_estimate.currency,
                'tool_version': '0.1.0'
            },
            'executive_summary': {
                'total_components': len(self.cost_estimate.component_costs),
                'unique_components': self.cost_estimate.assembly_cost.unique_components,
                'cost_per_board': {
                    'low': self.cost_estimate.total_cost_per_board_low,
                    'typical': self.cost_estimate.total_cost_per_board_typical,
                    'high': self.cost_estimate.total_cost_per_board_high
                },
                'confidence_interval': {
                    'low': self.cost_estimate.total_cost_per_board_low,
                    'high': self.cost_estimate.total_cost_per_board_high,
                    'range_percentage': (
                        (self.cost_estimate.total_cost_per_board_high -
                         self.cost_estimate.total_cost_per_board_low) /
                        self.cost_estimate.total_cost_per_board_typical * 100
                    ) if self.cost_estimate.total_cost_per_board_typical > 0 else 0
                }
            },
            'volume_tier_comparison': {
                'tiers': [
                    {
                        'volume': volume,
                        'cost_per_board': costs['total'],
                        'total_cost': costs['total'] * volume,
                        'breakdown': {
                            'components': costs['components'],
                            'assembly': costs['assembly'],
                            'overhead': costs['overhead']
                        }
                    }
                    for volume, costs in volume_costs.items()
                ]
            },
            'cost_breakdown_by_category': category_costs,
            'top_cost_drivers': cost_drivers,
            'assembly_breakdown': {
                'by_package_type': assembly_breakdown,
                'summary': {
                    'total_components': self.cost_estimate.assembly_cost.total_components,
                    'setup_cost': self.cost_estimate.assembly_cost.setup_cost,
                    'placement_cost_per_board': self.cost_estimate.assembly_cost.placement_cost_per_board,
                    'total_cost_per_board': self.cost_estimate.assembly_cost.total_assembly_cost_per_board
                }
            },
            'overhead_costs': {
                'nre_cost': self.cost_estimate.overhead_costs.nre_cost,
                'procurement_overhead': self.cost_estimate.overhead_costs.procurement_overhead,
                'supply_chain_risk_factor': self.cost_estimate.overhead_costs.supply_chain_risk_factor,
                'markup_percentage': self.cost_estimate.overhead_costs.markup_percentage,
                'total_overhead': self.cost_estimate.overhead_costs.total_overhead
            },
            'risk_assessment': risks,
            'itemized_components': [
                {
                    'reference_designator': comp.reference_designator,
                    'quantity': comp.quantity,
                    'category': comp.category.value,
                    'package_type': comp.package_type.value,
                    'manufacturer': comp.manufacturer,
                    'mpn': comp.manufacturer_part_number,
                    'description': comp.description,
                    'unit_cost': {
                        'low': comp.unit_cost_low,
                        'typical': comp.unit_cost_typical,
                        'high': comp.unit_cost_high
                    },
                    'total_cost': {
                        'low': comp.total_cost_low,
                        'typical': comp.total_cost_typical,
                        'high': comp.total_cost_high
                    },
                    'price_breaks': [
                        {
                            'quantity': pb.quantity,
                            'unit_price': pb.unit_price,
                            'total_price': pb.total_price
                        }
                        for pb in comp.price_breaks
                    ],
                    'notes': comp.notes
                }
                for comp in self.cost_estimate.component_costs
            ],
            'warnings': self.cost_estimate.warnings,
            'notes': self.cost_estimate.notes,
            'assumptions': [
                'Prices based on typical market rates and may vary',
                'Assembly costs assume standard PCB assembly processes',
                'Volume pricing based on standard quantity breaks (1, 100, 1000, 10000)',
                'Does not include PCB fabrication costs',
                'Does not include shipping or import duties'
            ]
        }

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                json.dump(report, f, indent=2)
            logger.info(f"JSON report written to {output_path}")

        return report

    def generate_csv_export(self, output_path: Path) -> None:
        """
        Generate CSV export for spreadsheet analysis.

        Args:
            output_path: Path to write CSV file
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)

            # Header
            writer.writerow([
                'Reference Designator',
                'Quantity',
                'Category',
                'Package Type',
                'Manufacturer',
                'MPN',
                'Description',
                'Unit Cost (Low)',
                'Unit Cost (Typical)',
                'Unit Cost (High)',
                'Total Cost (Low)',
                'Total Cost (Typical)',
                'Total Cost (High)',
                'Price @ 1',
                'Price @ 100',
                'Price @ 1000',
                'Price @ 10000',
                'Notes'
            ])

            # Component rows
            for comp in self.cost_estimate.component_costs:
                # Extract price breaks
                price_at_1 = ''
                price_at_100 = ''
                price_at_1000 = ''
                price_at_10000 = ''

                for pb in comp.price_breaks:
                    if pb.quantity == 1:
                        price_at_1 = f"{pb.unit_price:.4f}"
                    elif pb.quantity == 100:
                        price_at_100 = f"{pb.unit_price:.4f}"
                    elif pb.quantity == 1000:
                        price_at_1000 = f"{pb.unit_price:.4f}"
                    elif pb.quantity == 10000:
                        price_at_10000 = f"{pb.unit_price:.4f}"

                writer.writerow([
                    comp.reference_designator,
                    comp.quantity,
                    comp.category.value,
                    comp.package_type.value,
                    comp.manufacturer or '',
                    comp.manufacturer_part_number or '',
                    comp.description or '',
                    f"{comp.unit_cost_low:.4f}",
                    f"{comp.unit_cost_typical:.4f}",
                    f"{comp.unit_cost_high:.4f}",
                    f"{comp.total_cost_low:.2f}",
                    f"{comp.total_cost_typical:.2f}",
                    f"{comp.total_cost_high:.2f}",
                    price_at_1,
                    price_at_100,
                    price_at_1000,
                    price_at_10000,
                    comp.notes or ''
                ])

            # Summary rows
            writer.writerow([])
            writer.writerow(['SUMMARY'])
            writer.writerow(['Total Components', len(self.cost_estimate.component_costs)])
            writer.writerow(['Total Component Cost (Typical)', f"${self.cost_estimate.total_component_cost_typical:.2f}"])
            writer.writerow(['Assembly Cost', f"${self.cost_estimate.assembly_cost.total_assembly_cost_per_board:.2f}"])
            writer.writerow(['Overhead Cost', f"${self.cost_estimate.overhead_costs.total_overhead:.2f}"])
            writer.writerow(['Total Cost per Board (Typical)', f"${self.cost_estimate.total_cost_per_board_typical:.2f}"])

            # Volume tier summary
            writer.writerow([])
            writer.writerow(['VOLUME TIER PRICING'])
            writer.writerow(['Volume', 'Cost per Board', 'Total Cost'])

            volume_costs = self._calculate_volume_costs()
            for volume in self.VOLUME_TIERS:
                costs = volume_costs[volume]
                writer.writerow([
                    volume,
                    f"${costs['total']:.2f}",
                    f"${costs['total'] * volume:.2f}"
                ])

        logger.info(f"CSV export written to {output_path}")

    def generate_markdown_report(self, output_path: Path) -> None:
        """
        Generate Markdown report for documentation.

        Args:
            output_path: Path to write Markdown file
        """
        volume_costs = self._calculate_volume_costs()
        category_costs = self._calculate_cost_by_category()
        cost_drivers = self._get_top_cost_drivers(10)
        risks = self._extract_risk_flags()
        assembly_breakdown = self._get_assembly_breakdown()

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            # Header
            f.write("# PCB Cost Estimate Report\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n")
            if self.cost_estimate.file_path:
                f.write(f"**Source File:** {self.cost_estimate.file_path}  \n")
            f.write(f"**Currency:** {self.cost_estimate.currency}\n\n")

            f.write("---\n\n")

            # Executive Summary
            f.write("## Executive Summary\n\n")
            f.write(f"- **Total Components:** {len(self.cost_estimate.component_costs)}\n")
            f.write(f"- **Unique Components:** {self.cost_estimate.assembly_cost.unique_components}\n")
            f.write(f"- **Cost per Board (Typical):** ${self.cost_estimate.total_cost_per_board_typical:.2f}\n")
            f.write(f"  - Components: ${self.cost_estimate.total_component_cost_typical:.2f}\n")
            f.write(f"  - Assembly: ${self.cost_estimate.assembly_cost.total_assembly_cost_per_board:.2f}\n")
            f.write(f"  - Overhead: ${self.cost_estimate.overhead_costs.total_overhead:.2f}\n\n")

            # Volume Tier Comparison
            f.write("## Volume Tier Comparison\n\n")
            f.write("| Volume | Components | Assembly | Overhead | **Total/Board** |\n")
            f.write("|--------|------------|----------|----------|----------------|\n")

            for volume in self.VOLUME_TIERS:
                costs = volume_costs[volume]
                f.write(f"| {volume:,} | ${costs['components']:.2f} | ${costs['assembly']:.2f} | "
                       f"${costs['overhead']:.2f} | **${costs['total']:.2f}** |\n")

            f.write("\n")

            # Cost Breakdown by Category
            f.write("## Cost Breakdown by Category\n\n")
            f.write("| Category | Count | Total Cost | % of Total |\n")
            f.write("|----------|-------|------------|------------|\n")

            for cat in category_costs:
                f.write(f"| {cat['category'].title()} | {cat['count']} | "
                       f"${cat['total_cost']:.2f} | {cat['percentage']:.1f}% |\n")

            f.write("\n")

            # Top Cost Drivers
            f.write("## Top 10 Cost Drivers\n\n")
            f.write("These components dominate the BOM cost:\n\n")
            f.write("| Ref Des | MPN | Category | Qty | Unit Cost | Total Cost | % of Total |\n")
            f.write("|---------|-----|----------|-----|-----------|------------|------------|\n")

            for driver in cost_drivers:
                f.write(f"| {driver['reference']} | {driver['mpn'][:30]} | "
                       f"{driver['category'].title()} | {driver['quantity']} | "
                       f"${driver['unit_cost']:.2f} | ${driver['total_cost']:.2f} | "
                       f"{driver['percentage']:.1f}% |\n")

            f.write("\n")

            # Assembly Cost Breakdown
            f.write("## Assembly Cost Breakdown\n\n")
            f.write("| Package Type | Count | % of Total |\n")
            f.write("|--------------|-------|------------|\n")

            for item in assembly_breakdown:
                f.write(f"| {item['package_type']} | {item['count']} | {item['percentage']:.1f}% |\n")

            f.write(f"\n**Total Components:** {self.cost_estimate.assembly_cost.total_components}  \n")
            f.write(f"**Setup Cost (one-time):** ${self.cost_estimate.assembly_cost.setup_cost:.2f}  \n")
            f.write(f"**Placement Cost (per board):** ${self.cost_estimate.assembly_cost.placement_cost_per_board:.2f}  \n\n")

            # Risk Assessment
            total_risks = sum(len(v) for v in risks.values())
            if total_risks > 0:
                f.write("## Risk Assessment\n\n")

                if risks['obsolescence']:
                    f.write("### ⚠️ Obsolescence Risks\n\n")
                    for risk in risks['obsolescence']:
                        f.write(f"- {risk['message']}\n")
                    f.write("\n")

                if risks['high_cost']:
                    f.write("### 💰 High-Cost Components\n\n")
                    for risk in risks['high_cost'][:5]:
                        f.write(f"- **{risk['component']}** ({risk['mpn']}): ${risk['cost']:.2f}\n")
                    f.write("\n")

                if risks['price_warnings']:
                    f.write("### ⚠️ Price Warnings\n\n")
                    for risk in risks['price_warnings']:
                        f.write(f"- {risk['message']}\n")
                    f.write("\n")

                if risks['single_source']:
                    f.write("### ⚠️ Supply Chain Risks\n\n")
                    for risk in risks['single_source']:
                        f.write(f"- {risk['message']}\n")
                    f.write("\n")

            # Warnings and Notes
            if self.cost_estimate.warnings:
                f.write("## Warnings\n\n")
                for warning in self.cost_estimate.warnings:
                    f.write(f"- ⚠️ {warning}\n")
                f.write("\n")

            if self.cost_estimate.notes:
                f.write("## Notes\n\n")
                for note in self.cost_estimate.notes:
                    f.write(f"- ℹ️ {note}\n")
                f.write("\n")

            # Assumptions
            f.write("## Assumptions\n\n")
            f.write("- Prices based on typical market rates and may vary\n")
            f.write("- Assembly costs assume standard PCB assembly processes\n")
            f.write("- Volume pricing based on standard quantity breaks (1, 100, 1000, 10000)\n")
            f.write("- Does not include PCB fabrication costs\n")
            f.write("- Does not include shipping or import duties\n\n")

            # Footer
            f.write("---\n\n")
            f.write("*Generated by PCB Cost Estimator v0.1.0*\n")

        logger.info(f"Markdown report written to {output_path}")


def generate_report(
    cost_estimate: CostEstimate,
    format: str = 'table',
    output_path: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """
    Generate cost report in specified format.

    Args:
        cost_estimate: Complete cost estimate
        format: Output format ('table', 'json', 'csv', 'markdown')
        output_path: Optional output file path

    Returns:
        Dict for JSON format, None for others
    """
    generator = CostReportGenerator(cost_estimate)

    if format == 'table':
        generator.generate_cli_table()
        return None
    elif format == 'json':
        return generator.generate_json_report(output_path)
    elif format == 'csv':
        if not output_path:
            raise ValueError("output_path required for CSV format")
        generator.generate_csv_export(output_path)
        return None
    elif format == 'markdown':
        if not output_path:
            raise ValueError("output_path required for Markdown format")
        generator.generate_markdown_report(output_path)
        return None
    else:
        raise ValueError(f"Unknown format: {format}")
