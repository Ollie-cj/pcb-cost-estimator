# Cost Reporting Module

The PCB Cost Estimator includes a comprehensive reporting module that generates cost reports in multiple formats, suitable for different use cases.

## Features

- **Multiple Output Formats**: CLI table, JSON, CSV, and Markdown
- **Volume Tier Comparison**: Costs at 1, 100, 1000, and 10000 units
- **Cost Breakdown by Category**: Pie chart ready data showing cost distribution
- **Top Cost Drivers**: Identifies components that dominate BOM cost
- **Risk Assessment**: Highlights obsolescence, high-cost items, and supply chain risks
- **Assembly Analysis**: Detailed breakdown by package complexity
- **Confidence Intervals**: Low/typical/high cost estimates for all values

## Output Formats

### 1. CLI Table (Rich Formatted)

Beautiful terminal output with color-coded tables, perfect for quick reviews.

```bash
pcb-cost estimate my_bom.csv --format table
```

Features:
- Executive summary with total costs
- Volume tier comparison table
- Cost breakdown by category
- Top 10 most expensive components
- Assembly cost breakdown by package type
- Risk flags and warnings

### 2. JSON Report

Complete machine-readable breakdown with all metadata and analysis.

```bash
pcb-cost estimate my_bom.csv --format json --output report.json
```

JSON structure includes:
- `metadata`: Generation timestamp, source file, currency
- `executive_summary`: Total costs, confidence intervals
- `volume_tier_comparison`: Costs at each volume tier
- `cost_breakdown_by_category`: Aggregated costs by component type
- `top_cost_drivers`: Most expensive components
- `assembly_breakdown`: Package type counts and costs
- `overhead_costs`: NRE, procurement, risk factors
- `risk_assessment`: Obsolescence, high-cost, supply chain risks
- `itemized_components`: Full per-component breakdown with price breaks
- `warnings` and `notes`: Analysis findings
- `assumptions`: Cost model assumptions

### 3. CSV Export

Spreadsheet-importable format for further analysis in Excel or Google Sheets.

```bash
pcb-cost estimate my_bom.csv --format csv --output report.csv
```

CSV includes:
- Per-component line items with all cost data
- Price breaks at standard volumes (1, 100, 1000, 10000)
- Summary section with totals
- Volume tier pricing table

Perfect for:
- Custom analysis and pivoting
- Integration with procurement systems
- Budget tracking
- Cost trend analysis

### 4. Markdown Report

Human-readable documentation suitable for sharing and version control.

```bash
pcb-cost estimate my_bom.csv --format markdown --output report.md
```

Markdown includes:
- Formatted tables for easy reading
- Section headers for navigation
- Risk assessment with emoji indicators
- Complete cost breakdown
- Assumptions and methodology

Perfect for:
- Technical documentation
- Sharing with stakeholders
- Including in project READMEs
- Version control tracking

## Usage Examples

### Basic Usage

```bash
# Display CLI table
pcb-cost estimate bom.csv

# Generate JSON report
pcb-cost estimate bom.csv --format json --output report.json

# Generate CSV export
pcb-cost estimate bom.csv --format csv --output report.csv

# Generate Markdown report
pcb-cost estimate bom.csv --format markdown --output report.md
```

### Auto-detect Format from Extension

The CLI will automatically detect the format from the output file extension:

```bash
pcb-cost estimate bom.csv --output report.json  # Generates JSON
pcb-cost estimate bom.csv --output report.csv   # Generates CSV
pcb-cost estimate bom.csv --output report.md    # Generates Markdown
```

### With LLM Enrichment

Enable LLM-powered analysis for better risk assessment:

```bash
pcb-cost estimate bom.csv --enable-llm --format markdown --output report.md
```

This adds:
- Obsolescence risk detection
- Price reasonableness checks
- Enhanced component classification
- Alternative component suggestions

### Programmatic Usage

```python
from pcb_cost_estimator.reporting import generate_report, CostReportGenerator
from pcb_cost_estimator.cost_estimator import CostEstimator
from pcb_cost_estimator.bom_parser import BomParser
from pathlib import Path

# Parse BOM and estimate costs
parser = BomParser()
bom_result = parser.parse_file("my_bom.csv")
estimator = CostEstimator(cost_config)
cost_estimate = estimator.estimate_bom_cost(bom_result, board_quantity=1)

# Generate reports in different formats
generate_report(cost_estimate, format='table')  # Display CLI table
generate_report(cost_estimate, format='json', output_path=Path('report.json'))
generate_report(cost_estimate, format='csv', output_path=Path('report.csv'))
generate_report(cost_estimate, format='markdown', output_path=Path('report.md'))

# Or use the generator directly for more control
generator = CostReportGenerator(cost_estimate)
json_data = generator.generate_json_report(Path('report.json'))
generator.generate_csv_export(Path('report.csv'))
generator.generate_markdown_report(Path('report.md'))
generator.generate_cli_table()
```

## Report Contents

### Executive Summary

- Total number of components (unique and total)
- Cost per board with confidence intervals (low/typical/high)
- Currency
- Breakdown by major cost categories

### Volume Tier Comparison

Costs calculated at standard manufacturing volumes:
- 1 unit (prototype)
- 100 units (low volume)
- 1,000 units (medium volume)
- 10,000 units (high volume)

For each volume:
- Component cost per board
- Assembly cost per board
- Overhead cost per board
- Total cost per board
- Total cost for entire order

### Cost Breakdown by Category

Aggregated costs grouped by component type:
- Resistors
- Capacitors
- ICs
- Connectors
- Other categories

For each category:
- Total count
- Total cost
- Percentage of overall BOM cost

### Top Cost Drivers

The 10 most expensive components, showing:
- Reference designator
- Manufacturer and part number
- Category and package type
- Quantity
- Unit cost
- Total cost
- Percentage of total BOM cost

Helps identify:
- Where to focus cost reduction efforts
- Single-source dependencies
- Expensive specialty components

### Assembly Cost Breakdown

Detailed analysis of assembly costs by package complexity:
- Small SMD (0201-0603)
- Medium SMD (0805-1210)
- Large SMD (2010+)
- SOIC packages
- QFP packages
- QFN packages
- BGA packages
- Through-hole components
- Connectors

Shows component counts and percentage distribution.

### Risk Assessment

Identifies potential issues:

**Obsolescence Risks**:
- Components marked as NRND (Not Recommended for New Design)
- End of life (EOL) components
- Obsolete parts
- Suggested alternatives

**High-Cost Components**:
- Components exceeding cost thresholds
- Potential for cost optimization

**Price Warnings**:
- Unusual pricing detected by LLM analysis
- Potential data entry errors
- Market availability concerns

**Supply Chain Risks**:
- Single-source components
- Long lead time parts
- Allocation concerns

### Assumptions

Documents the cost model assumptions:
- Pricing based on typical market rates
- Assembly costs assume standard PCB assembly
- Volume pricing at standard break points
- Does not include PCB fabrication
- Does not include shipping or duties

## API Reference

### `generate_report(cost_estimate, format, output_path=None)`

Generate a cost report in the specified format.

**Parameters:**
- `cost_estimate` (CostEstimate): Complete cost estimate with breakdown
- `format` (str): Output format - 'table', 'json', 'csv', or 'markdown'
- `output_path` (Path, optional): Output file path (required for json/csv/markdown)

**Returns:**
- Dict for JSON format (also writes to file if output_path provided)
- None for other formats

### `CostReportGenerator`

Class for generating reports with fine-grained control.

**Methods:**
- `generate_cli_table()`: Display rich formatted table in terminal
- `generate_json_report(output_path)`: Generate JSON report
- `generate_csv_export(output_path)`: Generate CSV export
- `generate_markdown_report(output_path)`: Generate Markdown report

**Internal Methods:**
- `_calculate_volume_costs()`: Calculate costs at each volume tier
- `_calculate_cost_by_category()`: Aggregate costs by category
- `_get_top_cost_drivers(limit)`: Identify most expensive components
- `_extract_risk_flags()`: Extract and categorize risk warnings
- `_get_assembly_breakdown()`: Breakdown assembly by package type

## Examples

See `examples/generate_reports_example.py` for a complete working example that demonstrates all report formats.

## Testing

The reporting module includes comprehensive tests in `tests/test_reporting.py`:

```bash
pytest tests/test_reporting.py -v
```

Tests cover:
- All report formats
- Volume cost calculations
- Cost driver identification
- Risk flag extraction
- Edge cases and error handling

## Dependencies

The reporting module requires:
- `rich>=13.0.0` - For beautiful CLI table formatting
- `pydantic>=2.0.0` - For data models
- Standard library: `csv`, `json`, `pathlib`, `datetime`

## Future Enhancements

Potential improvements for future versions:
- PDF report generation
- Interactive HTML reports
- Charts and graphs (matplotlib/plotly)
- Comparison reports (multiple BOMs)
- Cost trend analysis over time
- Custom report templates
- Export to procurement systems (ERP integration)
