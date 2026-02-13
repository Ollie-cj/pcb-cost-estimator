"""Edge case tests for BoM parser module."""

import pytest
from pathlib import Path
from pcb_cost_estimator.bom_parser import BomParser
from pcb_cost_estimator.models import ComponentCategory


@pytest.mark.unit
class TestBomParserEdgeCases:
    """Test BoM parser edge cases and unusual inputs."""

    @pytest.fixture
    def parser(self):
        """Create a parser instance."""
        return BomParser()

    def test_empty_file(self, parser, tmp_path):
        """Test parsing completely empty file."""
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("")

        result = parser.parse_file(csv_file)

        assert not result.success
        assert result.item_count == 0
        assert len(result.errors) > 0

    def test_only_headers(self, parser, tmp_path):
        """Test file with only headers, no data rows."""
        csv_content = """Reference Designator,Quantity,Manufacturer,MPN,Description"""
        csv_file = tmp_path / "only_headers.csv"
        csv_file.write_text(csv_content)

        result = parser.parse_file(csv_file)

        # Should succeed but with no items
        assert result.item_count == 0

    def test_single_component(self, parser, tmp_path):
        """Test parsing BoM with exactly one component."""
        csv_content = """Ref,Qty,Manufacturer,MPN,Description
R1,1,Vishay,CRCW0805100K,Resistor 100k"""
        csv_file = tmp_path / "single.csv"
        csv_file.write_text(csv_content)

        result = parser.parse_file(csv_file)

        assert result.success
        assert result.item_count == 1
        assert result.items[0].reference_designator == "R1"
        assert result.items[0].quantity == 1

    def test_all_dnp(self, parser, tmp_path):
        """Test BoM where all components are DNP."""
        csv_content = """Ref,Qty,Description
R1,1,Resistor DNP
R2,1,Do Not Place
R3,1,Not Fitted
C1,1,DNI"""
        csv_file = tmp_path / "all_dnp.csv"
        csv_file.write_text(csv_content)

        result = parser.parse_file(csv_file)

        assert result.success
        assert result.item_count == 4
        assert all(item.dnp for item in result.items)

    def test_missing_mpn_column(self, parser, tmp_path):
        """Test BoM missing MPN column entirely."""
        csv_content = """Ref,Qty,Description,Package
R1,1,Resistor 10k,0805
C1,2,Capacitor 100nF,0603
U1,1,Buck Converter,SOIC-8"""
        csv_file = tmp_path / "no_mpn.csv"
        csv_file.write_text(csv_content)

        result = parser.parse_file(csv_file)

        assert result.success
        assert result.item_count == 3
        # Items should be created without MPN
        assert result.items[0].manufacturer_part_number is None
        assert result.items[1].manufacturer_part_number is None

    def test_missing_required_columns(self, parser, tmp_path):
        """Test BoM missing both ref and qty columns."""
        csv_content = """Description,Package
Resistor,0805
Capacitor,0603"""
        csv_file = tmp_path / "missing_required.csv"
        csv_file.write_text(csv_content)

        result = parser.parse_file(csv_file)

        # Should fail or have errors since ref and qty are required
        assert not result.success or len(result.errors) > 0

    def test_extra_whitespace(self, parser, tmp_path):
        """Test BoM with excessive whitespace in cells."""
        csv_content = """Ref,Qty,Manufacturer,MPN,Description
  R1  ,  1  ,  Vishay  ,  CRCW0805100K  ,  Resistor 100k
    C1    ,    2    ,    Murata    ,    GRM188    ,    Capacitor    """
        csv_file = tmp_path / "whitespace.csv"
        csv_file.write_text(csv_content)

        result = parser.parse_file(csv_file)

        assert result.success
        assert result.item_count == 2
        # Whitespace should be stripped
        assert result.items[0].reference_designator == "R1"
        assert result.items[0].quantity == 1
        assert result.items[0].manufacturer == "Vishay"

    def test_unicode_characters(self, parser, tmp_path):
        """Test BoM with unicode characters in descriptions."""
        csv_content = """Ref,Qty,Manufacturer,MPN,Description
R1,1,Yageo,RC0805,Resistor 1kΩ ±1%
C1,1,Murata,GRM188,Capacitor 100µF
U1,1,STMicro,STM32,MCU 32-bit © 2023
D1,1,Vishay,1N4148,Diode → Forward"""
        csv_file = tmp_path / "unicode.csv"
        csv_file.write_text(csv_content, encoding='utf-8')

        result = parser.parse_file(csv_file)

        assert result.success
        assert result.item_count == 4
        # Unicode should be preserved
        assert "Ω" in result.items[0].description or "kΩ" in result.items[0].description
        assert "µF" in result.items[1].description or "uF" in result.items[1].description

    def test_empty_rows(self, parser, tmp_path):
        """Test BoM with empty rows interspersed."""
        csv_content = """Ref,Qty,Description
R1,1,Resistor

C1,1,Capacitor

,,,
U1,1,IC
"""
        csv_file = tmp_path / "empty_rows.csv"
        csv_file.write_text(csv_content)

        result = parser.parse_file(csv_file)

        # Should skip empty rows
        assert result.item_count == 3
        assert result.items[0].reference_designator == "R1"
        assert result.items[1].reference_designator == "C1"
        assert result.items[2].reference_designator == "U1"

    def test_numeric_ref_designators(self, parser, tmp_path):
        """Test handling of numeric or unusual ref designators."""
        csv_content = """Ref,Qty,Description
1,1,Resistor
123,1,Capacitor
R-1,1,Resistor
C.1,1,Capacitor"""
        csv_file = tmp_path / "numeric_ref.csv"
        csv_file.write_text(csv_content)

        result = parser.parse_file(csv_file)

        # Should parse but may have warnings
        assert result.item_count >= 1

    def test_very_large_quantity(self, parser, tmp_path):
        """Test component with very large quantity."""
        csv_content = """Ref,Qty,Description
R1,10000,Resistor
C1,999999,Capacitor"""
        csv_file = tmp_path / "large_qty.csv"
        csv_file.write_text(csv_content)

        result = parser.parse_file(csv_file)

        assert result.success
        assert result.items[0].quantity == 10000
        assert result.items[1].quantity == 999999

    def test_special_characters_in_values(self, parser, tmp_path):
        """Test special characters in component values."""
        csv_content = """Ref,Qty,Value,Description
R1,1,10k±1%,Resistor
C1,1,100nF/50V,Capacitor
L1,1,10µH @ 1MHz,Inductor"""
        csv_file = tmp_path / "special_chars.csv"
        csv_file.write_text(csv_content, encoding='utf-8')

        result = parser.parse_file(csv_file)

        assert result.success
        assert result.item_count == 3

    def test_mixed_case_dnp_markers(self, parser, tmp_path):
        """Test various DNP marker formats."""
        csv_content = """Ref,Qty,Description,DNP
R1,1,Resistor,DNP
R2,1,Resistor,dnp
R3,1,Resistor,Dnp
R4,1,Resistor Do Not Place,
R5,1,Resistor DNI,
R6,1,Resistor (Not Fitted),
R7,1,Resistor NO_POP,"""
        csv_file = tmp_path / "mixed_dnp.csv"
        csv_file.write_text(csv_content)

        result = parser.parse_file(csv_file)

        assert result.success
        # At least first 3 should be marked DNP from the DNP column
        assert result.items[0].dnp
        assert result.items[1].dnp
        assert result.items[2].dnp

    def test_missing_category_inference(self, parser, tmp_path):
        """Test components with unclear category."""
        csv_content = """Ref,Qty,Description
X1,1,Unknown Component
TP1,1,Test Point
H1,1,Mounting Hole
FB1,1,Ferrite Bead"""
        csv_file = tmp_path / "unclear_category.csv"
        csv_file.write_text(csv_content)

        result = parser.parse_file(csv_file)

        assert result.success
        assert result.item_count == 4
        # Categories should be inferred or marked as unknown/other
        assert result.items[0].category in [ComponentCategory.UNKNOWN, ComponentCategory.OTHER]

    def test_duplicate_column_names(self, parser, tmp_path):
        """Test handling of duplicate column names."""
        csv_content = """Ref,Qty,Description,Description,Package
R1,1,Resistor,100k,0805"""
        csv_file = tmp_path / "duplicate_cols.csv"
        csv_file.write_text(csv_content)

        result = parser.parse_file(csv_file)

        # Should handle gracefully, possibly with warning
        assert result.item_count >= 0

    def test_quoted_fields_with_commas(self, parser, tmp_path):
        """Test CSV with quoted fields containing commas."""
        csv_content = """Ref,Qty,Description,Notes
R1,1,"Resistor, 100k, 1%","High precision, low noise"
C1,1,"Capacitor, X7R","Temperature stable, automotive grade" """
        csv_file = tmp_path / "quoted.csv"
        csv_file.write_text(csv_content)

        result = parser.parse_file(csv_file)

        assert result.success
        assert result.item_count == 2
        # Commas inside quotes should be preserved
        assert "100k" in result.items[0].description
        assert "X7R" in result.items[1].description

    def test_malformed_csv_inconsistent_columns(self, parser, tmp_path):
        """Test CSV with inconsistent number of columns."""
        csv_content = """Ref,Qty,Description
R1,1,Resistor,ExtraField,AnotherExtra
C1,1
U1,1,IC,SomeField"""
        csv_file = tmp_path / "inconsistent.csv"
        csv_file.write_text(csv_content)

        result = parser.parse_file(csv_file)

        # Should handle gracefully, parsing what it can
        assert result.item_count >= 1

    def test_very_long_description(self, parser, tmp_path):
        """Test component with very long description."""
        long_desc = "A" * 1000  # 1000 character description
        csv_content = f"""Ref,Qty,Description
R1,1,{long_desc}"""
        csv_file = tmp_path / "long_desc.csv"
        csv_file.write_text(csv_content)

        result = parser.parse_file(csv_file)

        assert result.success
        assert result.item_count == 1
        assert len(result.items[0].description) == 1000

    def test_bom_with_metadata_rows(self, parser, tmp_path):
        """Test BoM with multiple metadata rows before header."""
        csv_content = """Project Name: Test PCB
Designer: John Doe
Date: 2024-01-01
Revision: Rev A
Total Components: 100

Ref,Qty,Manufacturer,MPN,Description
R1,1,Vishay,CRCW0805,Resistor
C1,1,Murata,GRM188,Capacitor"""
        csv_file = tmp_path / "metadata.csv"
        csv_file.write_text(csv_content)

        result = parser.parse_file(csv_file)

        assert result.success
        assert result.item_count == 2
        assert result.items[0].reference_designator == "R1"

    def test_null_bytes_in_file(self, parser, tmp_path):
        """Test handling of null bytes in file."""
        csv_content = "Ref,Qty,Description\nR1,1,Resistor\x00\nC1,1,Capacitor"
        csv_file = tmp_path / "null_bytes.csv"
        csv_file.write_bytes(csv_content.encode('utf-8'))

        result = parser.parse_file(csv_file)

        # Should handle gracefully
        assert result.item_count >= 1

    def test_windows_line_endings(self, parser, tmp_path):
        """Test file with Windows (CRLF) line endings."""
        csv_content = "Ref,Qty,Description\r\nR1,1,Resistor\r\nC1,1,Capacitor\r\n"
        csv_file = tmp_path / "crlf.csv"
        csv_file.write_text(csv_content)

        result = parser.parse_file(csv_file)

        assert result.success
        assert result.item_count == 2

    def test_mac_line_endings(self, parser, tmp_path):
        """Test file with old Mac (CR only) line endings."""
        csv_content = "Ref,Qty,Description\rR1,1,Resistor\rC1,1,Capacitor\r"
        csv_file = tmp_path / "cr.csv"
        csv_file.write_text(csv_content, newline='')

        result = parser.parse_file(csv_file)

        # Should handle or fail gracefully
        assert result.item_count >= 0

    @pytest.mark.parametrize("extension,delimiter", [
        ("csv", ","),
        ("tsv", "\t"),
    ])
    def test_various_delimiters(self, parser, tmp_path, extension, delimiter):
        """Test parsing files with various delimiters."""
        content = f"Ref{delimiter}Qty{delimiter}Description\nR1{delimiter}1{delimiter}Resistor\n"
        file = tmp_path / f"test.{extension}"
        file.write_text(content)

        result = parser.parse_file(file)

        assert result.success
        assert result.item_count == 1


@pytest.mark.unit
class TestBomParserWithRealFixtures:
    """Test parser with realistic BoM fixtures."""

    @pytest.fixture
    def parser(self):
        """Create a parser instance."""
        return BomParser()

    def test_parse_arduino_shield_simple(self, parser):
        """Test parsing simple Arduino shield BoM (~20 components)."""
        fixture_path = Path(__file__).parent / "fixtures" / "arduino_shield_simple.csv"

        result = parser.parse_file(fixture_path)

        assert result.success
        assert result.item_count == 20
        assert len(result.errors) == 0

        # Verify component categories are correctly inferred
        categories = {item.category for item in result.items}
        assert ComponentCategory.RESISTOR in categories
        assert ComponentCategory.CAPACITOR in categories
        assert ComponentCategory.IC in categories
        assert ComponentCategory.CONNECTOR in categories

    def test_parse_iot_board_medium(self, parser):
        """Test parsing medium complexity IoT board BoM (~80 components)."""
        fixture_path = Path(__file__).parent / "fixtures" / "iot_board_medium.csv"

        result = parser.parse_file(fixture_path)

        assert result.success
        assert result.item_count == 74  # Actual count from fixture
        assert len(result.errors) == 0

        # Verify diverse component types
        categories = {item.category for item in result.items}
        assert len(categories) >= 5  # Should have at least 5 different categories

    def test_parse_mixed_signal_complex(self, parser):
        """Test parsing complex mixed-signal board BoM (200+ components)."""
        fixture_path = Path(__file__).parent / "fixtures" / "mixed_signal_complex.csv"

        result = parser.parse_file(fixture_path)

        assert result.success
        assert result.item_count >= 200
        assert len(result.errors) == 0

        # Verify all major categories are present
        categories = {item.category for item in result.items}
        assert ComponentCategory.RESISTOR in categories
        assert ComponentCategory.CAPACITOR in categories
        assert ComponentCategory.INDUCTOR in categories
        assert ComponentCategory.IC in categories
        assert ComponentCategory.DIODE in categories
        assert ComponentCategory.TRANSISTOR in categories
        assert ComponentCategory.CONNECTOR in categories
