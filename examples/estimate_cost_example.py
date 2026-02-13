"""Example script demonstrating cost estimation."""

from pathlib import Path
import json

from pcb_cost_estimator import BomParser, CostEstimator
from pcb_cost_estimator.config import load_config, CostModelConfig


def main():
    """Run cost estimation example."""
    # Parse a sample BoM file
    bom_parser = BomParser()
    sample_bom = Path("data/sample_boms/example_bom.csv")

    print(f"Parsing BoM file: {sample_bom}")
    bom_result = bom_parser.parse_file(sample_bom)

    print(f"Parsed {bom_result.item_count} components")
    print(f"Warnings: {len(bom_result.warnings)}")
    print(f"Errors: {len(bom_result.errors)}")
    print()

    # Load configuration (or use defaults)
    try:
        config_path = Path("config/cost_model.yaml")
        if config_path.exists():
            import yaml
            with open(config_path) as f:
                config_data = yaml.safe_load(f)
            cost_model_config = CostModelConfig(**config_data)
        else:
            # Use default configuration
            print("Using default cost model configuration")
            cost_model_config = CostModelConfig()
    except Exception as e:
        print(f"Error loading config: {e}")
        print("Using default cost model configuration")
        cost_model_config = CostModelConfig()

    # Create cost estimator
    estimator = CostEstimator(cost_model_config)

    # Estimate costs for different board quantities
    board_quantities = [1, 10, 100, 1000]

    print("=" * 80)
    print("COST ESTIMATION RESULTS")
    print("=" * 80)
    print()

    for qty in board_quantities:
        print(f"Board Quantity: {qty}")
        print("-" * 80)

        cost_estimate = estimator.estimate_bom_cost(bom_result, board_quantity=qty)

        # Print summary
        print(f"Total Components: {cost_estimate.assembly_cost.total_components}")
        print(f"Unique Components: {cost_estimate.assembly_cost.unique_components}")
        print()

        print("Component Costs:")
        print(f"  Low:     ${cost_estimate.total_component_cost_low:.2f}")
        print(f"  Typical: ${cost_estimate.total_component_cost_typical:.2f}")
        print(f"  High:    ${cost_estimate.total_component_cost_high:.2f}")
        print()

        print("Assembly Costs:")
        print(f"  Setup:     ${cost_estimate.assembly_cost.setup_cost:.2f}")
        print(f"  Placement: ${cost_estimate.assembly_cost.placement_cost_per_board:.2f}")
        print(f"  Total:     ${cost_estimate.assembly_cost.total_assembly_cost_per_board:.2f}")
        print()

        print("Overhead Costs:")
        print(f"  NRE:        ${cost_estimate.overhead_costs.nre_cost:.2f}")
        print(f"  Procurement: ${cost_estimate.overhead_costs.procurement_overhead:.2f}")
        print(f"  Total:      ${cost_estimate.overhead_costs.total_overhead:.2f}")
        print()

        print("Total Cost Per Board:")
        print(f"  Low:     ${cost_estimate.total_cost_per_board_low:.2f}")
        print(f"  Typical: ${cost_estimate.total_cost_per_board_typical:.2f}")
        print(f"  High:    ${cost_estimate.total_cost_per_board_high:.2f}")
        print()

        print("Total Project Cost:")
        print(f"  Low:     ${cost_estimate.total_cost_per_board_low * qty:.2f}")
        print(f"  Typical: ${cost_estimate.total_cost_per_board_typical * qty:.2f}")
        print(f"  High:    ${cost_estimate.total_cost_per_board_high * qty:.2f}")
        print()
        print()

    # Show detailed component breakdown for qty=1
    print("=" * 80)
    print("DETAILED COMPONENT BREAKDOWN (for 1 board)")
    print("=" * 80)
    print()

    cost_estimate = estimator.estimate_bom_cost(bom_result, board_quantity=1)

    for comp_cost in cost_estimate.component_costs:
        print(f"Component: {comp_cost.reference_designator}")
        print(f"  Category: {comp_cost.category}")
        print(f"  Package:  {comp_cost.package_type}")
        print(f"  Quantity: {comp_cost.quantity}")
        print(f"  Unit Cost (typical): ${comp_cost.unit_cost_typical:.4f}")
        print(f"  Total Cost (typical): ${comp_cost.total_cost_typical:.4f}")

        if comp_cost.manufacturer:
            print(f"  Manufacturer: {comp_cost.manufacturer}")
        if comp_cost.manufacturer_part_number:
            print(f"  MPN: {comp_cost.manufacturer_part_number}")

        # Show quantity breaks
        print(f"  Quantity Breaks:")
        for pb in comp_cost.price_breaks:
            print(f"    {pb.quantity:>6} units: ${pb.unit_price:.4f}/unit, ${pb.total_price:.2f} total")

        print()

    # Export to JSON
    output_file = Path("cost_estimate.json")
    with open(output_file, "w") as f:
        json.dump(cost_estimate.model_dump(), f, indent=2, default=str)
    print(f"Full cost estimate exported to: {output_file}")


if __name__ == "__main__":
    main()
