"""BoM parser module with support for CSV, XLSX, and TSV formats."""

import csv
import re
from pathlib import Path
from typing import Any, Optional
import pandas as pd
from difflib import SequenceMatcher

from .models import BomItem, BomParseResult, ComponentCategory


class ColumnMatcher:
    """Fuzzy column name matcher for BoM files.

    Handles common variations in column naming conventions.
    """

    # Column mapping patterns: canonical_name -> list of variations
    COLUMN_PATTERNS = {
        "reference_designator": [
            "reference designator",
            "ref des",
            "refdes",
            "ref",
            "designator",
            "reference",
            "part reference",
        ],
        "quantity": [
            "quantity",
            "qty",
            "qnty",
            "amount",
            "count",
            "number",
        ],
        "manufacturer": [
            "manufacturer",
            "mfr",
            "mfg",
            "maker",
            "vendor",
            "brand",
        ],
        "manufacturer_part_number": [
            "manufacturer part number",
            "part number",
            "mpn",
            "mfr part number",
            "mfg part number",
            "part no",
            "partnumber",
            "mfr pn",
            "mfg pn",
            "p/n",
        ],
        "description": [
            "description",
            "desc",
            "component description",
            "part description",
            "details",
        ],
        "package": [
            "package",
            "footprint",
            "pcb footprint",
            "mounting",
            "case",
            "pkg",
        ],
        "value": [
            "value",
            "val",
            "component value",
            "rating",
        ],
        "category": [
            "category",
            "type",
            "component type",
            "part type",
            "class",
        ],
        "dnp": [
            "dnp",
            "dni",
            "do not place",
            "do not install",
            "no place",
            "not fitted",
        ],
    }

    @classmethod
    def normalize_column_name(cls, name: str) -> str:
        """Normalize a column name for comparison."""
        # Convert to lowercase, remove extra whitespace and special chars
        normalized = re.sub(r"[^\w\s]", " ", name.lower())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    @classmethod
    def find_best_match(cls, column_name: str, threshold: float = 0.6) -> Optional[str]:
        """Find the best matching canonical column name.

        Args:
            column_name: The column name to match
            threshold: Minimum similarity score (0-1) for a match

        Returns:
            Canonical column name or None if no good match found
        """
        normalized = cls.normalize_column_name(column_name)

        best_match = None
        best_score = 0.0

        for canonical, patterns in cls.COLUMN_PATTERNS.items():
            for pattern in patterns:
                # Exact match gets priority
                if normalized == pattern:
                    return canonical

                # Fuzzy match using sequence matcher
                score = SequenceMatcher(None, normalized, pattern).ratio()
                if score > best_score:
                    best_score = score
                    best_match = canonical

        # Only return match if it meets threshold
        if best_score >= threshold:
            return best_match

        return None

    @classmethod
    def map_columns(cls, columns: list[str]) -> dict[str, str]:
        """Map DataFrame columns to canonical field names.

        Args:
            columns: List of column names from the file

        Returns:
            Dictionary mapping original column names to canonical names
        """
        mapping = {}
        for col in columns:
            canonical = cls.find_best_match(col)
            if canonical:
                mapping[col] = canonical
        return mapping


class BomParser:
    """Parser for Bill of Materials files in various formats."""

    SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls"}

    def __init__(self, max_header_search_rows: int = 10):
        """Initialize the BoM parser.

        Args:
            max_header_search_rows: Maximum number of rows to search for headers
        """
        self.max_header_search_rows = max_header_search_rows

    def parse_file(self, file_path: str | Path) -> BomParseResult:
        """Parse a BoM file and return normalized items.

        Args:
            file_path: Path to the BoM file (CSV, TSV, or XLSX)

        Returns:
            BomParseResult containing parsed items and any errors/warnings
        """
        path = Path(file_path)
        result = BomParseResult(file_path=str(path))

        if not path.exists():
            result.errors.append(f"File not found: {path}")
            return result

        extension = path.suffix.lower()
        if extension not in self.SUPPORTED_EXTENSIONS:
            result.errors.append(
                f"Unsupported file format: {extension}. "
                f"Supported: {', '.join(self.SUPPORTED_EXTENSIONS)}"
            )
            return result

        try:
            # Load data based on file type
            if extension == ".csv":
                df = self._read_csv(path)
            elif extension == ".tsv":
                df = self._read_tsv(path)
            elif extension in {".xlsx", ".xls"}:
                df = self._read_excel(path)
            else:
                result.errors.append(f"Unexpected file extension: {extension}")
                return result

            if df is None or df.empty:
                result.errors.append("File is empty or could not be read")
                return result

            # Parse the DataFrame
            self._parse_dataframe(df, result)

        except Exception as e:
            result.errors.append(f"Error reading file: {str(e)}")

        return result

    def _read_csv(self, path: Path) -> Optional[pd.DataFrame]:
        """Read CSV file with header detection."""
        return self._read_delimited(path, delimiter=",")

    def _read_tsv(self, path: Path) -> Optional[pd.DataFrame]:
        """Read TSV file with header detection."""
        return self._read_delimited(path, delimiter="\t")

    def _read_delimited(self, path: Path, delimiter: str) -> Optional[pd.DataFrame]:
        """Read delimited file with automatic header detection.

        Args:
            path: Path to the file
            delimiter: Field delimiter

        Returns:
            DataFrame or None if read fails
        """
        # Try to detect header row
        header_row = self._detect_header_row(path, delimiter)

        # Read the file
        df = pd.read_csv(
            path,
            delimiter=delimiter,
            skiprows=header_row,
            dtype=str,
            keep_default_na=False,
        )

        return df

    def _read_excel(self, path: Path) -> Optional[pd.DataFrame]:
        """Read Excel file with header detection.

        Args:
            path: Path to the Excel file

        Returns:
            DataFrame or None if read fails
        """
        # Read a preview to detect header
        preview = pd.read_excel(path, nrows=self.max_header_search_rows, dtype=str)

        header_row = 0
        for idx in range(min(self.max_header_search_rows, len(preview))):
            row_values = preview.iloc[idx].astype(str).tolist()
            if self._looks_like_header(row_values):
                header_row = idx
                break

        # Read the full file with detected header
        df = pd.read_excel(path, skiprows=header_row, dtype=str, keep_default_na=False)

        return df

    def _detect_header_row(self, path: Path, delimiter: str) -> int:
        """Detect which row contains the column headers.

        Args:
            path: Path to the file
            delimiter: Field delimiter

        Returns:
            Row index of the header (0-based)
        """
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f, delimiter=delimiter)
            for idx, row in enumerate(reader):
                if idx >= self.max_header_search_rows:
                    break
                if self._looks_like_header(row):
                    return idx

        # Default to first row
        return 0

    def _looks_like_header(self, row: list[str]) -> bool:
        """Check if a row looks like a header row.

        Args:
            row: List of cell values

        Returns:
            True if row appears to be a header
        """
        if not row:
            return False

        # Filter out empty cells
        non_empty = [cell for cell in row if cell and str(cell).strip()]

        if len(non_empty) < 2:
            return False

        # Check if any column name matches known patterns
        matches = 0
        for cell in non_empty:
            if ColumnMatcher.find_best_match(str(cell), threshold=0.5):
                matches += 1

        # If at least 2 columns match known patterns, it's likely a header
        return matches >= 2

    def _parse_dataframe(self, df: pd.DataFrame, result: BomParseResult) -> None:
        """Parse a DataFrame into BomItem objects.

        Args:
            df: DataFrame to parse
            result: BomParseResult to populate
        """
        # Map columns to canonical names
        column_mapping = ColumnMatcher.map_columns(df.columns.tolist())

        if not column_mapping:
            result.errors.append(
                "Could not identify any BoM columns. Please check the file format."
            )
            return

        # Check for required fields
        if "reference_designator" not in column_mapping.values():
            result.warnings.append(
                "No reference designator column found. Using row index as reference."
            )

        if "quantity" not in column_mapping.values():
            result.warnings.append("No quantity column found. Defaulting to 1 for all items.")

        # Reverse mapping for easy lookup
        reverse_mapping = {v: k for k, v in column_mapping.items()}

        # Process each row
        for idx, row in df.iterrows():
            result.total_rows_processed += 1

            try:
                # Extract fields using mapped columns
                item_data = self._extract_item_data(
                    row, reverse_mapping, idx, result.total_rows_processed
                )

                # Check for DNP markers
                item_data["dnp"] = self._check_dnp(row, item_data)

                # Infer category from description/value
                if not item_data.get("category") or item_data["category"] == "unknown":
                    item_data["category"] = self._infer_category(item_data)

                # Create BomItem
                item = BomItem(**item_data)
                result.items.append(item)

            except ValueError as e:
                result.warnings.append(
                    f"Row {result.total_rows_processed}: Validation error - {str(e)}"
                )
            except Exception as e:
                result.warnings.append(
                    f"Row {result.total_rows_processed}: Failed to parse - {str(e)}"
                )

    def _extract_item_data(
        self,
        row: pd.Series,
        reverse_mapping: dict[str, str],
        idx: int,
        line_number: int,
    ) -> dict[str, Any]:
        """Extract item data from a DataFrame row.

        Args:
            row: DataFrame row
            reverse_mapping: Mapping from canonical names to column names
            idx: Row index
            line_number: Line number in source file

        Returns:
            Dictionary of item data
        """
        data: dict[str, Any] = {"line_number": line_number}

        # Reference designator
        if "reference_designator" in reverse_mapping:
            col = reverse_mapping["reference_designator"]
            data["reference_designator"] = str(row[col]).strip() or f"UNKNOWN_{idx}"
        else:
            data["reference_designator"] = f"ROW_{idx}"

        # Quantity
        if "quantity" in reverse_mapping:
            col = reverse_mapping["quantity"]
            qty_str = str(row[col]).strip()
            # Try to parse quantity, default to 1
            try:
                data["quantity"] = int(float(qty_str)) if qty_str else 1
            except (ValueError, TypeError):
                data["quantity"] = 1
        else:
            data["quantity"] = 1

        # Optional fields
        for field in [
            "manufacturer",
            "manufacturer_part_number",
            "description",
            "package",
            "value",
        ]:
            if field in reverse_mapping:
                col = reverse_mapping[field]
                value = str(row[col]).strip()
                data[field] = value if value else None

        # Category
        if "category" in reverse_mapping:
            col = reverse_mapping["category"]
            cat_str = str(row[col]).strip().lower()
            # Try to match to enum
            for cat in ComponentCategory:
                if cat.value in cat_str or cat_str in cat.value:
                    data["category"] = cat
                    break

        return data

    def _check_dnp(self, row: pd.Series, item_data: dict[str, Any]) -> bool:
        """Check if item is marked as DNP/DNI.

        Args:
            row: DataFrame row
            item_data: Extracted item data

        Returns:
            True if item is DNP/DNI
        """
        # Check all row values for DNP markers
        row_str = " ".join(str(v).lower() for v in row.values)
        dnp_markers = ["dnp", "dni", "do not place", "do not install", "not fitted", "no place"]

        for marker in dnp_markers:
            if marker in row_str:
                return True

        # Check description and notes specifically
        for field in ["description", "notes"]:
            if field in item_data and item_data[field]:
                value_lower = str(item_data[field]).lower()
                for marker in dnp_markers:
                    if marker in value_lower:
                        return True

        return False

    def _infer_category(self, item_data: dict[str, Any]) -> ComponentCategory:
        """Infer component category from available data.

        Args:
            item_data: Item data dictionary

        Returns:
            Inferred ComponentCategory
        """
        # Get reference designator prefix
        ref_des = item_data.get("reference_designator", "")
        prefix = re.match(r"^([A-Za-z]+)", ref_des)

        if prefix:
            prefix_str = prefix.group(1).upper()

            # Common prefix mappings
            prefix_map = {
                "R": ComponentCategory.RESISTOR,
                "C": ComponentCategory.CAPACITOR,
                "L": ComponentCategory.INDUCTOR,
                "U": ComponentCategory.IC,
                "IC": ComponentCategory.IC,
                "J": ComponentCategory.CONNECTOR,
                "P": ComponentCategory.CONNECTOR,
                "D": ComponentCategory.DIODE,
                "Q": ComponentCategory.TRANSISTOR,
                "LED": ComponentCategory.LED,
                "Y": ComponentCategory.CRYSTAL,
                "X": ComponentCategory.CRYSTAL,
                "SW": ComponentCategory.SWITCH,
                "S": ComponentCategory.SWITCH,
                "K": ComponentCategory.RELAY,
                "F": ComponentCategory.FUSE,
                "T": ComponentCategory.TRANSFORMER,
            }

            if prefix_str in prefix_map:
                return prefix_map[prefix_str]

        # Check description for keywords
        desc = str(item_data.get("description", "")).lower()
        value = str(item_data.get("value", "")).lower()
        combined = f"{desc} {value}"

        category_keywords = {
            ComponentCategory.RESISTOR: ["resistor", "ohm", "kohm", "mohm"],
            ComponentCategory.CAPACITOR: ["capacitor", "farad", "uf", "nf", "pf"],
            ComponentCategory.INDUCTOR: ["inductor", "henry", "uh", "mh"],
            ComponentCategory.IC: ["ic", "chip", "processor", "controller", "regulator"],
            ComponentCategory.CONNECTOR: ["connector", "header", "socket", "plug"],
            ComponentCategory.DIODE: ["diode", "rectifier"],
            ComponentCategory.TRANSISTOR: ["transistor", "mosfet", "bjt", "fet"],
            ComponentCategory.LED: ["led", "light emitting"],
            ComponentCategory.CRYSTAL: ["crystal", "oscillator", "resonator"],
            ComponentCategory.SWITCH: ["switch", "button"],
            ComponentCategory.RELAY: ["relay"],
            ComponentCategory.FUSE: ["fuse"],
            ComponentCategory.TRANSFORMER: ["transformer"],
        }

        for category, keywords in category_keywords.items():
            for keyword in keywords:
                if keyword in combined:
                    return category

        return ComponentCategory.UNKNOWN
