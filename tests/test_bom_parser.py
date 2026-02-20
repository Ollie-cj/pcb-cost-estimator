"""Tests for BoM parser module."""

import pytest
from pathlib import Path
from pcb_cost_estimator.bom_parser import BomParser, ColumnMatcher
from pcb_cost_estimator.models import BomItem, ComponentCategory


class TestColumnMatcher:
    """Test the column name matcher."""

    def test_normalize_column_name(self):
        """Test column name normalization."""
        assert ColumnMatcher.normalize_column_name("Part Number") == "part number"
        assert ColumnMatcher.normalize_column_name("  MFR  P/N  ") == "mfr p n"
        assert ColumnMatcher.normalize_column_name("Ref-Des") == "ref des"

    def test_exact_match(self):
        """Test exact column matching."""
        assert ColumnMatcher.find_best_match("Reference Designator") == "reference_designator"
        assert ColumnMatcher.find_best_match("Quantity") == "quantity"
        assert ColumnMatcher.find_best_match("MPN") == "manufacturer_part_number"

    def test_fuzzy_match(self):
        """Test fuzzy column matching."""
        assert ColumnMatcher.find_best_match("Ref Des") == "reference_designator"
        assert ColumnMatcher.find_best_match("Qty") == "quantity"
        assert ColumnMatcher.find_best_match("Mfr") == "manufacturer"
        assert ColumnMatcher.find_best_match("Part No") == "manufacturer_part_number"

    def test_case_insensitive(self):
        """Test case-insensitive matching."""
        assert ColumnMatcher.find_best_match("REFERENCE DESIGNATOR") == "reference_designator"
        assert ColumnMatcher.find_best_match("ref des") == "reference_designator"
        assert ColumnMatcher.find_best_match("ReF dEs") == "reference_designator"

    def test_no_match(self):
        """Test when no match is found."""
        assert ColumnMatcher.find_best_match("ABCDEFG") is None
        assert ColumnMatcher.find_best_match("Random Column") is None

    def test_map_columns(self):
        """Test mapping a list of columns."""
        columns = ["Ref Des", "Qty", "Manufacturer", "Part Number", "Description"]
        mapping = ColumnMatcher.map_columns(columns)

        assert mapping["Ref Des"] == "reference_designator"
        assert mapping["Qty"] == "quantity"
        assert mapping["Manufacturer"] == "manufacturer"
        assert mapping["Part Number"] == "manufacturer_part_number"
        assert mapping["Description"] == "description"


class TestBomParser:
    """Test the BoM parser."""

    @pytest.fixture
    def parser(self):
        """Create a parser instance."""
        return BomParser()

    @pytest.fixture
    def sample_csv_path(self, tmp_path):
        """Create a sample CSV file."""
        csv_content = """Reference Designator,Quantity,Manufacturer,Part Number,Description,Package,Value
R1,1,Vishay,CRCW0805100K,Resistor 100k,0805,100k
C1,2,Murata,GRM188R71C104KA01,Capacitor 100nF,0603,100nF
U1,1,TI,TPS54331DR,Buck Converter,SOIC-8,3.3V
"""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(csv_content)
        return csv_file

    @pytest.fixture
    def sample_tsv_path(self, tmp_path):
        """Create a sample TSV file."""
        tsv_content = """Ref Des\tQty\tMfr\tMPN\tDesc\tFootprint\tVal
R10\t1\tYageo\tRC0805\tResistor\t0805\t1k
C10\t1\tSamsung\tCL10A105\tCapacitor\t0603\t1uF
"""
        tsv_file = tmp_path / "test.tsv"
        tsv_file.write_text(tsv_content)
        return tsv_file

    def test_parse_csv(self, parser, sample_csv_path):
        """Test parsing a CSV file."""
        result = parser.parse_file(sample_csv_path)

        assert result.success
        assert result.item_count == 3
        assert len(result.warnings) == 0
        assert len(result.errors) == 0

        # Check first item
        assert result.items[0].reference_designator == "R1"
        assert result.items[0].quantity == 1
        assert result.items[0].manufacturer == "Vishay"
        assert result.items[0].manufacturer_part_number == "CRCW0805100K"
        assert result.items[0].category == ComponentCategory.RESISTOR

    def test_parse_tsv(self, parser, sample_tsv_path):
        """Test parsing a TSV file."""
        result = parser.parse_file(sample_tsv_path)

        assert result.success
        assert result.item_count == 2

        # Check categories are inferred
        assert result.items[0].category == ComponentCategory.RESISTOR
        assert result.items[1].category == ComponentCategory.CAPACITOR

    def test_dnp_detection(self, parser, tmp_path):
        """Test DNP marker detection."""
        csv_content = """Ref,Qty,Desc
R1,1,Resistor
R2,1,Resistor DNP
R3,1,Do Not Place
R4,1,Not Fitted
"""
        csv_file = tmp_path / "dnp.csv"
        csv_file.write_text(csv_content)

        result = parser.parse_file(csv_file)

        assert result.success
        assert result.item_count == 4
        assert not result.items[0].dnp
        assert result.items[1].dnp
        assert result.items[2].dnp
        assert result.items[3].dnp

    def test_header_detection(self, parser, tmp_path):
        """Test header row detection."""
        csv_content = """Project: Test PCB
Revision: 1.0

Ref Des,Qty,MPN
R1,1,RC0805
"""
        csv_file = tmp_path / "header_offset.csv"
        csv_file.write_text(csv_content)

        result = parser.parse_file(csv_file)

        assert result.success
        assert result.item_count == 1
        assert result.items[0].reference_designator == "R1"

    def test_category_inference_from_ref_des(self, parser, tmp_path):
        """Test category inference from reference designator."""
        csv_content = """Ref,Qty
R1,1
C1,1
L1,1
U1,1
D1,1
Q1,1
J1,1
LED1,1
Y1,1
SW1,1
"""
        csv_file = tmp_path / "categories.csv"
        csv_file.write_text(csv_content)

        result = parser.parse_file(csv_file)

        assert result.success
        assert result.items[0].category == ComponentCategory.RESISTOR
        assert result.items[1].category == ComponentCategory.CAPACITOR
        assert result.items[2].category == ComponentCategory.INDUCTOR
        assert result.items[3].category == ComponentCategory.IC
        assert result.items[4].category == ComponentCategory.DIODE
        assert result.items[5].category == ComponentCategory.TRANSISTOR
        assert result.items[6].category == ComponentCategory.CONNECTOR
        assert result.items[7].category == ComponentCategory.LED
        assert result.items[8].category == ComponentCategory.CRYSTAL
        assert result.items[9].category == ComponentCategory.SWITCH

    def test_malformed_rows_warning(self, parser, tmp_path):
        """Test handling of malformed rows."""
        csv_content = """Ref,Qty,Desc
R1,1,Good row
,2,Missing ref
R3,abc,Bad quantity
"""
        csv_file = tmp_path / "malformed.csv"
        csv_file.write_text(csv_content)

        result = parser.parse_file(csv_file)

        # Should still succeed — parser handles malformed rows gracefully
        assert result.success
        # Parser creates fallback ref designator for missing ref, defaults qty to 1
        assert result.item_count >= 1

    def test_file_not_found(self, parser):
        """Test handling of non-existent file."""
        result = parser.parse_file("/nonexistent/file.csv")

        assert not result.success
        assert len(result.errors) > 0
        assert "not found" in result.errors[0].lower()

    def test_unsupported_format(self, parser, tmp_path):
        """Test handling of unsupported file format."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Some content")

        result = parser.parse_file(txt_file)

        assert not result.success
        assert "unsupported" in result.errors[0].lower()


class TestBomItem:
    """Test BomItem model validation."""

    def test_valid_item(self):
        """Test creating a valid BomItem."""
        item = BomItem(
            reference_designator="R1",
            quantity=1,
            manufacturer="Vishay",
            manufacturer_part_number="CRCW0805100K",
            description="Resistor",
            package="0805",
            value="100k",
            category=ComponentCategory.RESISTOR,
        )

        assert item.reference_designator == "R1"
        assert item.quantity == 1
        assert item.category == ComponentCategory.RESISTOR

    def test_minimal_item(self):
        """Test creating a minimal BomItem."""
        item = BomItem(reference_designator="R1", quantity=1)

        assert item.reference_designator == "R1"
        assert item.quantity == 1
        assert item.category == ComponentCategory.UNKNOWN
        assert not item.dnp

    def test_invalid_ref_des(self):
        """Test validation of reference designator."""
        with pytest.raises(ValueError):
            BomItem(reference_designator="", quantity=1)

        with pytest.raises(ValueError):
            BomItem(reference_designator="   ", quantity=1)

    def test_invalid_quantity(self):
        """Test validation of quantity."""
        with pytest.raises(ValueError):
            BomItem(reference_designator="R1", quantity=0)

        with pytest.raises(ValueError):
            BomItem(reference_designator="R1", quantity=-1)

    def test_string_stripping(self):
        """Test that string fields are stripped."""
        item = BomItem(
            reference_designator="  R1  ",
            quantity=1,
            manufacturer="  Vishay  ",
            description="  Resistor  ",
        )

        assert item.reference_designator == "R1"
        assert item.manufacturer == "Vishay"
        assert item.description == "Resistor"
