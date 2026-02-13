# Task: Create cost report generator with multiple output formats

## Instructions
Build a reporting module that combines deterministic and LLM-enriched estimates into comprehensive cost reports. Output formats should include: (1) CLI summary table (using rich or tabulate) showing per-line-item costs, subtotals by category, and total board cost, (2) Detailed JSON report with full itemized breakdown, confidence intervals, assumptions, and metadata, (3) CSV export for spreadsheet analysis, (4) Markdown report suitable for documentation/sharing. The report should include: executive summary (total cost per board at various volumes), cost breakdown by category (pie chart data), top 10 most expensive components, risk flags (single-source parts, high-cost items, obsolescence warnings from LLM), assembly cost breakdown, and comparison across volume tiers. Include a 'cost drivers' section highlighting which components dominate the BoM cost.

## Acceptance Criteria

* CLI output displays formatted cost summary table
* JSON report contains complete itemized breakdown with all fields
* CSV export is importable into Excel/Google Sheets
* Markdown report is well-formatted and human-readable
* Report includes volume tier comparison (1, 100, 1000, 10000 units)
* Top cost drivers are identified and highlighted
* Risk flags from LLM analysis are included when available

**Complexity:** medium
**Dependencies:** Implement LLM-powered component enrichment and pricing intelligence

## Acceptance Criteria
- 

## Rules
- Work autonomously — make all necessary changes
- Commit your work with descriptive messages
- Write output summary to /workspace/.aegis/output.json when done
