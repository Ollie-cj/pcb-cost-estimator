# Sample BoM Files

This directory contains sample Bill of Materials (BoM) files for testing the parser module.

## Files

### example_bom.csv
Standard CSV format with common BoM columns. Includes:
- Various component types (resistors, capacitors, ICs, etc.)
- One DNP (Do Not Place) item (C3)
- Standard column headers

### alternative_headers.tsv
TSV format demonstrating:
- Tab-separated values
- Alternative column naming conventions (Ref Des, MFR, MPN, etc.)
- Metadata rows before the actual BoM data
- Wide variety of component types

### with_dnp_markers.csv
CSV file focusing on DNP/DNI handling:
- Multiple DNP marker variations (DNP, DNI, "DO NOT PLACE", "Not Fitted")
- Tests the parser's ability to detect and flag components that should not be placed

### complex_layout.xlsx (requires generation)
Excel file with edge cases:
- Metadata rows before headers
- Headers starting at row 6 (not row 1)
- Formatted cells with colors
- Standard BoM data

### merged_cells.xlsx (requires generation)
Excel file testing merged cell handling:
- Title row with merged cells
- Headers at row 3
- Demonstrates parser's ability to handle Excel formatting

## Generating Excel Files

To create the Excel sample files, run:

```bash
python3 scripts/create_sample_xlsx.py
```

This will generate `complex_layout.xlsx` and `merged_cells.xlsx` in this directory.

## Usage

You can test the parser with these files:

```python
from pcb_cost_estimator.bom_parser import BomParser

parser = BomParser()

# Parse CSV
result = parser.parse_file("data/sample_boms/example_bom.csv")
print(f"Parsed {result.item_count} items")

# Parse TSV
result = parser.parse_file("data/sample_boms/alternative_headers.tsv")

# Parse Excel
result = parser.parse_file("data/sample_boms/complex_layout.xlsx")
```

## Column Variations Supported

The parser automatically handles these column name variations:

- **Reference Designator**: Reference Designator, Ref Des, RefDes, Ref, Designator, Reference
- **Quantity**: Quantity, Qty, Qnty, Amount, Count, Number
- **Manufacturer**: Manufacturer, MFR, MFG, Maker, Vendor, Brand
- **Part Number**: Manufacturer Part Number, Part Number, MPN, P/N, Part No
- **Description**: Description, Desc, Component Description, Details
- **Package**: Package, Footprint, PCB Footprint, Mounting, Case
- **Value**: Value, Val, Component Value, Rating
- **Category**: Category, Type, Component Type, Part Type
