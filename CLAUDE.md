# Task: Implement BoM parser and data normalization layer

## Instructions
Build a robust BoM ingestion module that accepts multiple input formats: CSV, Excel (.xlsx), and TSV. The parser should handle common BoM column variations (e.g., 'Part Number' vs 'MPN' vs 'Manufacturer Part Number', 'Qty' vs 'Quantity', 'Ref Des' vs 'Reference Designator'). Use Pydantic models to define a canonical BomItem schema with fields: reference_designator, quantity, manufacturer, manufacturer_part_number, description, package/footprint, value, category (resistor, capacitor, IC, connector, etc.). Implement fuzzy column matching and provide clear error messages for unparseable rows. Handle edge cases like merged cells, header rows not on line 1, and DNP (Do Not Place) markers.

## Acceptance Criteria

* Parses CSV, XLSX, and TSV BoM files correctly
* Handles at least 5 common column naming variations automatically
* Outputs a list of validated Pydantic BomItem objects
* Gracefully handles malformed rows with warnings (not crashes)
* DNP/DNI items are flagged but retained in output
* Includes sample BoM files in data/ for testing

**Complexity:** medium
**Dependencies:** Scaffold PCB cost estimation project structure

## Acceptance Criteria
- 

## Rules
- Work autonomously — make all necessary changes
- Commit your work with descriptive messages
- Write output summary to /workspace/.aegis/output.json when done
