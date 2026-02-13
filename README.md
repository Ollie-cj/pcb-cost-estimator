# PCB Cost Estimator

A Python CLI tool that estimates PCB manufacturing and assembly costs from a Bill of Materials (BoM). Uses a hybrid approach combining deterministic parametric models with LLM-powered component intelligence.

## Features

- **Multi-format BoM parsing** — CSV, Excel (.xlsx), and TSV with fuzzy column matching
- **Deterministic cost engine** — parametric pricing by component category, package type, and volume tier
- **LLM-powered enrichment** — AI classification for ambiguous parts, price reasonableness checks, and obsolescence risk flagging
- **Volume tier analysis** — cost breakdowns at 1, 10, 100, 1,000, and 10,000 units
- **Multiple output formats** — CLI table, JSON, CSV, and Markdown reports
- **Assembly cost estimation** — based on component mix, package complexity (SMD/TH/BGA), and unique part count

## Installation

### Prerequisites

- Python 3.8 or higher
- pip package manager

### Virtual Environment Setup

It is recommended to use a virtual environment to isolate dependencies:

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Linux/macOS:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install the package in development mode
pip install -e .
```

### Configuration

1. Copy the example configuration file:
```bash
cp config/config.example.yaml config/config.yaml
```

2. Edit `config/config.yaml` and add your API key:
   - For OpenAI: Set your API key or use environment variable `OPENAI_API_KEY`
   - For Anthropic: Set your API key or use environment variable `ANTHROPIC_API_KEY`

3. Validate your configuration:
```bash
pcb-cost validate-config
```

## Quick Start

```bash
# Install
pip install -e .

# Estimate costs from a BoM file
pcb-cost estimate bom.csv

# With volume tier and JSON output
pcb-cost estimate bom.xlsx --quantity 1000 --format json

# Without LLM (deterministic only)
pcb-cost estimate bom.csv --no-llm

# Get help
pcb-cost --help
```

## Configuration

Copy `config/default.yaml` and adjust model parameters, API keys, markup percentages, and volume discount curves. See [CONFIGURATION.md](CONFIGURATION.md) for details.

## Project Structure

```
src/pcb_cost_estimator/
├── cli.py                 # CLI entry point
├── parser/                # BoM ingestion and normalization
├── models/                # Pydantic data models
├── cost_engine/           # Deterministic pricing engine
├── llm/                   # LLM enrichment and classification
├── reporting/             # Report generation (JSON, CSV, Markdown, CLI)
└── config.py              # Configuration management
tests/                     # Test suite with realistic BoM fixtures
data/                      # Sample BoM files
config/                    # Model parameter configuration
```

## Architecture

The estimator runs a three-stage pipeline:

1. **Parse** — ingest BoM file, normalize columns, validate into `BomItem` objects
2. **Estimate** — classify components, apply parametric cost models, calculate volume breaks
3. **Enrich** *(optional)* — LLM reviews estimates for outliers, classifies ambiguous parts, flags obsolescence risks
4. **Report** — generate itemized cost breakdown with confidence intervals and risk flags

The deterministic engine works standalone; LLM enrichment is additive and gracefully degrades when unavailable.

## License

MIT
