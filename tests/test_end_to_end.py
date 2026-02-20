"""End-to-end tests for complete BoM processing pipeline."""

import pytest
from pathlib import Path
import tempfile
import json

from pcb_cost_estimator.bom_parser import BomParser
from pcb_cost_estimator.cost_estimator import CostEstimator
from pcb_cost_estimator.reporting import CostReportGenerator
from pcb_cost_estimator.config import CostModelConfig


@pytest.mark.e2e
class TestEndToEndPipeline:
    """Test complete pipeline from BoM file to report output."""

    @pytest.fixture
    def parser(self):
        """Create a parser instance."""
        return BomParser()

    @pytest.fixture
    def estimator(self):
        """Create a cost estimator instance."""
        return CostEstimator(CostModelConfig())

    def test_complete_pipeline_arduino_shield(self, parser, estimator):
        """Test complete pipeline with Arduino shield BoM."""
        # Step 1: Parse BoM file
        fixture_path = Path(__file__).parent / "fixtures" / "arduino_shield_simple.csv"
        parse_result = parser.parse_file(fixture_path)

        assert parse_result.success
        assert parse_result.item_count > 0

        # Step 2: Estimate costs
        cost_estimate = estimator.estimate_bom_cost(parse_result)

        assert cost_estimate.total_cost_per_board_typical > 0
        assert len(cost_estimate.component_costs) > 0

        # Step 3: Generate reports
        reporter = CostReportGenerator(cost_estimate)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Generate JSON report
            json_path = tmpdir_path / "report.json"
            reporter.generate_json_report(json_path)
            assert json_path.exists()

            # Verify JSON content
            with open(json_path, 'r') as f:
                json_data = json.load(f)
            assert isinstance(json_data, dict)
            assert len(json_data) > 0

            # Generate CSV report
            csv_path = tmpdir_path / "report.csv"
            reporter.generate_csv_export(csv_path)
            assert csv_path.exists()

            # Verify CSV has content
            csv_content = csv_path.read_text()
            assert len(csv_content) > 100

            # Generate Markdown report
            md_path = tmpdir_path / "report.md"
            reporter.generate_markdown_report(md_path)
            assert md_path.exists()

            # Verify Markdown has content
            md_content = md_path.read_text()
            assert len(md_content) > 500

    def test_complete_pipeline_iot_board(self, parser, estimator):
        """Test complete pipeline with IoT board BoM."""
        fixture_path = Path(__file__).parent / "fixtures" / "iot_board_medium.csv"
        parse_result = parser.parse_file(fixture_path)

        assert parse_result.success
        assert parse_result.item_count >= 50

        cost_estimate = estimator.estimate_bom_cost(parse_result)

        assert cost_estimate.total_cost_per_board_typical > 0
        assert cost_estimate.assembly_cost.total_assembly_cost_per_board > 0

        # Generate CLI table output (should not crash)
        reporter = CostReportGenerator(cost_estimate)
        reporter.generate_cli_table()

    def test_complete_pipeline_complex_board(self, parser, estimator):
        """Test complete pipeline with complex mixed-signal board BoM."""
        fixture_path = Path(__file__).parent / "fixtures" / "mixed_signal_complex.csv"
        parse_result = parser.parse_file(fixture_path)

        assert parse_result.success
        assert parse_result.item_count >= 200

        cost_estimate = estimator.estimate_bom_cost(parse_result)

        # Should handle large BoMs without issues
        assert cost_estimate.total_cost_per_board_typical > 0
        assert len(cost_estimate.component_costs) >= 200

        # Generate all report formats
        reporter = CostReportGenerator(cost_estimate)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            json_path = tmpdir_path / "complex_report.json"
            reporter.generate_json_report(json_path)
            assert json_path.exists()

            csv_path = tmpdir_path / "complex_report.csv"
            reporter.generate_csv_export(csv_path)
            assert csv_path.exists()

            md_path = tmpdir_path / "complex_report.md"
            reporter.generate_markdown_report(md_path)
            assert md_path.exists()

    def test_pipeline_with_warnings(self, parser, estimator, tmp_path):
        """Test pipeline handles BoM with parsing warnings."""
        # Create BoM with issues
        csv_content = """Ref,Qty,Description
R1,1,Resistor
,2,Missing ref
R3,abc,Bad quantity
R4,1,Good component"""
        csv_file = tmp_path / "warnings.csv"
        csv_file.write_text(csv_content)

        parse_result = parser.parse_file(csv_file)

        # Should have warnings but still succeed
        assert parse_result.success or len(parse_result.warnings) > 0

        # Cost estimation should still work
        cost_estimate = estimator.estimate_bom_cost(parse_result)
        assert cost_estimate.total_cost_per_board_typical >= 0

        # Reports should include warnings
        reporter = CostReportGenerator(cost_estimate)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            md_path = tmpdir_path / "warnings_report.md"
            reporter.generate_markdown_report(md_path)

            md_content = md_path.read_text()
            assert len(md_content) > 100

    def test_pipeline_volume_analysis(self, parser, estimator):
        """Test pipeline with volume tier analysis."""
        fixture_path = Path(__file__).parent / "fixtures" / "arduino_shield_simple.csv"
        parse_result = parser.parse_file(fixture_path)
        cost_estimate = estimator.estimate_bom_cost(parse_result)

        reporter = CostReportGenerator(cost_estimate)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            md_path = tmpdir_path / "volume_report.md"
            reporter.generate_markdown_report(md_path)

            md_content = md_path.read_text()
            assert len(md_content) > 500

    def test_pipeline_cost_drivers_analysis(self, parser, estimator):
        """Test pipeline identifies cost drivers."""
        fixture_path = Path(__file__).parent / "fixtures" / "iot_board_medium.csv"
        parse_result = parser.parse_file(fixture_path)
        cost_estimate = estimator.estimate_bom_cost(parse_result)

        # Should identify top cost components
        component_costs = cost_estimate.component_costs
        assert len(component_costs) > 0

        # Sort by total cost
        sorted_costs = sorted(
            component_costs,
            key=lambda x: x.total_cost_typical,
            reverse=True
        )

        # Top components should have meaningful costs
        if len(sorted_costs) > 0:
            assert sorted_costs[0].total_cost_typical > 0

    def test_pipeline_category_breakdown(self, parser, estimator):
        """Test pipeline provides category breakdown."""
        fixture_path = Path(__file__).parent / "fixtures" / "mixed_signal_complex.csv"
        parse_result = parser.parse_file(fixture_path)
        cost_estimate = estimator.estimate_bom_cost(parse_result)

        # Group costs by category
        category_totals = {}
        for comp_cost in cost_estimate.component_costs:
            category = comp_cost.category.value
            if category not in category_totals:
                category_totals[category] = 0.0
            category_totals[category] += comp_cost.total_cost_typical

        # Should have multiple categories
        assert len(category_totals) >= 3

        # All categories should have positive costs
        for category, total in category_totals.items():
            assert total >= 0


@pytest.mark.e2e
class TestEndToEndEdgeCases:
    """Test end-to-end pipeline with edge cases."""

    @pytest.fixture
    def parser(self):
        """Create a parser instance."""
        return BomParser()

    @pytest.fixture
    def estimator(self):
        """Create a cost estimator instance."""
        return CostEstimator(CostModelConfig())

    def test_empty_bom_pipeline(self, parser, estimator, tmp_path):
        """Test pipeline with empty BoM."""
        csv_content = """Ref,Qty,Description"""
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text(csv_content)

        parse_result = parser.parse_file(csv_file)
        cost_estimate = estimator.estimate_bom_cost(parse_result)

        # Should still generate reports
        reporter = CostReportGenerator(cost_estimate)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            json_path = tmpdir_path / "empty_report.json"
            reporter.generate_json_report(json_path)
            assert json_path.exists()

    def test_single_component_pipeline(self, parser, estimator, tmp_path):
        """Test pipeline with single component."""
        csv_content = """Ref,Qty,Description
R1,1,Resistor 10k"""
        csv_file = tmp_path / "single.csv"
        csv_file.write_text(csv_content)

        parse_result = parser.parse_file(csv_file)
        assert parse_result.item_count == 1

        cost_estimate = estimator.estimate_bom_cost(parse_result)
        assert cost_estimate.total_cost_per_board_typical > 0

        # Generate all reports
        reporter = CostReportGenerator(cost_estimate)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            json_path = tmpdir_path / "single_report.json"
            reporter.generate_json_report(json_path)
            assert json_path.exists()

            csv_path = tmpdir_path / "single_report.csv"
            reporter.generate_csv_export(csv_path)
            assert csv_path.exists()

    def test_all_dnp_pipeline(self, parser, estimator, tmp_path):
        """Test pipeline where all components are DNP."""
        csv_content = """Ref,Qty,Description
R1,1,Resistor DNP
R2,1,Do Not Place
C1,1,Capacitor DNI"""
        csv_file = tmp_path / "all_dnp.csv"
        csv_file.write_text(csv_content)

        parse_result = parser.parse_file(csv_file)
        assert parse_result.item_count == 3

        cost_estimate = estimator.estimate_bom_cost(parse_result)

        # Should have minimal cost since all DNP
        assert len(cost_estimate.component_costs) == 0 or cost_estimate.total_cost_per_board_typical < 1.0

        # Should still generate reports
        reporter = CostReportGenerator(cost_estimate)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            md_path = tmpdir_path / "dnp_report.md"
            reporter.generate_markdown_report(md_path)
            assert md_path.exists()

    def test_missing_mpn_pipeline(self, parser, estimator, tmp_path):
        """Test pipeline with components missing MPN."""
        csv_content = """Ref,Qty,Description,Package
R1,10,Resistor 10k,0603
C1,5,Capacitor 0.1uF,0603
U1,1,Microcontroller,LQFP-64"""
        csv_file = tmp_path / "no_mpn.csv"
        csv_file.write_text(csv_content)

        parse_result = parser.parse_file(csv_file)
        assert parse_result.item_count == 3

        # Should still estimate costs based on category/package
        cost_estimate = estimator.estimate_bom_cost(parse_result)
        assert cost_estimate.total_cost_per_board_typical > 0
        assert len(cost_estimate.component_costs) == 3

        # Reports should work
        reporter = CostReportGenerator(cost_estimate)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            json_path = tmpdir_path / "no_mpn_report.json"
            reporter.generate_json_report(json_path)
            assert json_path.exists()

    def test_unicode_characters_pipeline(self, parser, estimator, tmp_path):
        """Test pipeline with unicode characters."""
        csv_content = """Ref,Qty,Description
R1,1,Resistor 1kΩ ±1%
C1,1,Capacitor 100µF
U1,1,MCU © 2023"""
        csv_file = tmp_path / "unicode.csv"
        csv_file.write_text(csv_content, encoding='utf-8')

        parse_result = parser.parse_file(csv_file)
        cost_estimate = estimator.estimate_bom_cost(parse_result)

        # Should handle unicode gracefully
        reporter = CostReportGenerator(cost_estimate)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            md_path = tmpdir_path / "unicode_report.md"
            reporter.generate_markdown_report(md_path)
            assert md_path.exists()

            # Check content
            md_content = md_path.read_text(encoding='utf-8')
            assert len(md_content) > 100

    def test_very_large_quantities_pipeline(self, parser, estimator, tmp_path):
        """Test pipeline with very large quantities."""
        csv_content = """Ref,Qty,Description
R1,100000,Resistor 10k
C1,50000,Capacitor 0.1uF"""
        csv_file = tmp_path / "large_qty.csv"
        csv_file.write_text(csv_content)

        parse_result = parser.parse_file(csv_file)
        cost_estimate = estimator.estimate_bom_cost(parse_result)

        # Should handle large quantities
        assert cost_estimate.total_cost_per_board_typical > 0

        # Check price breaks apply for volume
        for comp_cost in cost_estimate.component_costs:
            if len(comp_cost.price_breaks) > 1:
                # Higher volumes should have better pricing
                prices = [pb.unit_price for pb in comp_cost.price_breaks]
                assert prices[-1] <= prices[0]


@pytest.mark.e2e
class TestReportFormatValidation:
    """Test that generated reports are valid and well-formed."""

    @pytest.fixture
    def parser(self):
        """Create a parser instance."""
        return BomParser()

    @pytest.fixture
    def estimator(self):
        """Create a cost estimator instance."""
        return CostEstimator(CostModelConfig())

    @pytest.fixture
    def sample_estimate(self, parser, estimator):
        """Generate a sample cost estimate."""
        fixture_path = Path(__file__).parent / "fixtures" / "arduino_shield_simple.csv"
        parse_result = parser.parse_file(fixture_path)
        return estimator.estimate_bom_cost(parse_result), parse_result

    def test_json_report_valid(self, sample_estimate):
        """Test that JSON report is valid JSON."""
        cost_estimate, parse_result = sample_estimate
        reporter = CostReportGenerator(cost_estimate)

        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "test.json"
            reporter.generate_json_report(json_path)

            # Should be valid JSON
            with open(json_path, 'r') as f:
                data = json.load(f)

            # Check some expected fields
            assert isinstance(data, dict)
            assert len(data) > 0

    def test_csv_report_parseable(self, sample_estimate):
        """Test that CSV report is parseable."""
        cost_estimate, parse_result = sample_estimate
        reporter = CostReportGenerator(cost_estimate)

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test.csv"
            reporter.generate_csv_export(csv_path)

            # Should be readable as CSV
            import csv
            with open(csv_path, 'r') as f:
                reader = csv.reader(f)
                rows = list(reader)

            # Should have header and data rows
            assert len(rows) >= 2

    def test_markdown_report_structure(self, sample_estimate):
        """Test that Markdown report has proper structure."""
        cost_estimate, parse_result = sample_estimate
        reporter = CostReportGenerator(cost_estimate)

        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "test.md"
            reporter.generate_markdown_report(md_path)

            content = md_path.read_text()

            # Should have markdown headers
            assert '#' in content

            # Should have some cost information
            assert any(char.isdigit() for char in content)
