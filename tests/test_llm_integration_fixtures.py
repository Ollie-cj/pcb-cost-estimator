"""LLM integration tests with mocked API response fixtures."""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from pcb_cost_estimator.models import BomItem, ComponentCategory
from pcb_cost_estimator.llm_enrichment import LLMEnrichmentService
from pcb_cost_estimator.llm_provider import LLMProvider, OpenAIProvider, AnthropicProvider


@pytest.fixture
def load_llm_fixtures():
    """Load LLM response fixtures from JSON files."""
    fixtures_dir = Path(__file__).parent / "fixtures" / "llm_responses"

    fixtures = {}
    for fixture_file in fixtures_dir.glob("*.json"):
        with open(fixture_file, 'r') as f:
            fixtures[fixture_file.stem] = json.load(f)

    return fixtures


@pytest.mark.integration
class TestLLMProviderWithMockedResponses:
    """Test LLM provider with mocked API responses."""

    def test_openai_provider_classification(self, load_llm_fixtures):
        """Test OpenAI provider with mocked classification response."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(
            load_llm_fixtures['classification_responses']['resistor_classification']
        )

        with patch('pcb_cost_estimator.llm_provider.openai.OpenAI') as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            provider = OpenAIProvider(api_key="test_key")
            result = provider.complete("Classify this component: R1")

            assert result is not None
            parsed = json.loads(result)
            assert parsed['category'] == 'resistor'
            assert parsed['confidence'] == 0.98

    def test_anthropic_provider_classification(self, load_llm_fixtures):
        """Test Anthropic provider with mocked classification response."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps(
            load_llm_fixtures['classification_responses']['capacitor_classification']
        )

        with patch('pcb_cost_estimator.llm_provider.anthropic.Anthropic') as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            provider = AnthropicProvider(api_key="test_key")
            result = provider.complete("Classify this component: C1")

            assert result is not None
            parsed = json.loads(result)
            assert parsed['category'] == 'capacitor'
            assert parsed['confidence'] == 0.97

    def test_provider_handles_json_in_markdown(self, load_llm_fixtures):
        """Test provider correctly extracts JSON from markdown code blocks."""
        fixture_data = load_llm_fixtures['classification_responses']['ic_classification']
        markdown_response = f"```json\n{json.dumps(fixture_data)}\n```"

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = markdown_response

        with patch('pcb_cost_estimator.llm_provider.openai.OpenAI') as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            provider = OpenAIProvider(api_key="test_key")
            result = provider.complete("Classify this component")

            parsed = json.loads(result)
            assert parsed['category'] == 'ic'
            assert parsed['confidence'] == 0.99


@pytest.mark.integration
class TestLLMEnrichmentWithFixtures:
    """Test LLM enrichment service with mocked fixtures."""

    @pytest.fixture
    def mock_provider(self):
        """Create a mock LLM provider."""
        return MagicMock(spec=LLMProvider)

    @pytest.fixture
    def enrichment_service(self, mock_provider):
        """Create enrichment service with mock provider."""
        return LLMEnrichmentService(provider=mock_provider, use_cache=False)

    def test_classify_resistor(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test resistor classification with mocked response."""
        mock_provider.complete.return_value = json.dumps(
            load_llm_fixtures['classification_responses']['resistor_classification']
        )

        item = BomItem(
            reference_designator="R1",
            quantity=1,
            manufacturer="Yageo",
            manufacturer_part_number="RC0603FR-0710KL",
            description="Resistor 1K 1% 1/10W",
            package="0603",
        )

        result = enrichment_service.classify_component(item)

        assert result.category == ComponentCategory.RESISTOR
        assert result.confidence >= 0.9
        assert "resistor" in result.reasoning.lower()

    def test_classify_capacitor(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test capacitor classification with mocked response."""
        mock_provider.complete.return_value = json.dumps(
            load_llm_fixtures['classification_responses']['capacitor_classification']
        )

        item = BomItem(
            reference_designator="C1",
            quantity=1,
            manufacturer="Murata",
            manufacturer_part_number="GRM188R71C104KA01D",
            description="Cap Ceramic 0.1uF 16V X7R",
            package="0603",
        )

        result = enrichment_service.classify_component(item)

        assert result.category == ComponentCategory.CAPACITOR
        assert result.confidence >= 0.9

    def test_classify_ic(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test IC classification with mocked response."""
        mock_provider.complete.return_value = json.dumps(
            load_llm_fixtures['classification_responses']['ic_classification']
        )

        item = BomItem(
            reference_designator="U1",
            quantity=1,
            manufacturer="STMicroelectronics",
            manufacturer_part_number="STM32F407VGT6",
            description="MCU ARM Cortex-M4 1MB Flash",
            package="LQFP-100",
        )

        result = enrichment_service.classify_component(item)

        assert result.category == ComponentCategory.IC
        assert result.confidence >= 0.9

    def test_classify_unknown_low_confidence(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test classification with low confidence."""
        mock_provider.complete.return_value = json.dumps(
            load_llm_fixtures['classification_responses']['unknown_classification']
        )

        item = BomItem(
            reference_designator="X1",
            quantity=1,
            description="Unknown Component",
        )

        result = enrichment_service.classify_component(item)

        assert result.confidence < 0.5

    def test_price_reasonableness_check_valid(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test price reasonableness check for valid price."""
        mock_provider.complete.return_value = json.dumps(
            load_llm_fixtures['price_reasonableness_responses']['resistor_reasonable']
        )

        item = BomItem(
            reference_designator="R1",
            quantity=1,
            category=ComponentCategory.RESISTOR,
            package="0603",
        )

        result = enrichment_service.check_price_reasonableness(item, 0.01)

        assert result.is_reasonable is True
        assert result.confidence >= 0.9
        assert result.typical_price_range_low is not None
        assert result.typical_price_range_high is not None

    def test_price_reasonableness_check_too_high(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test price reasonableness check for price too high."""
        mock_provider.complete.return_value = json.dumps(
            load_llm_fixtures['price_reasonableness_responses']['resistor_too_high']
        )

        item = BomItem(
            reference_designator="R1",
            quantity=1,
            category=ComponentCategory.RESISTOR,
            package="0603",
        )

        result = enrichment_service.check_price_reasonableness(item, 1.00)

        assert result.is_reasonable is False
        assert "higher" in result.reasoning.lower() or "error" in result.reasoning.lower()

    def test_price_reasonableness_check_ic(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test price reasonableness check for IC."""
        mock_provider.complete.return_value = json.dumps(
            load_llm_fixtures['price_reasonableness_responses']['ic_reasonable']
        )

        item = BomItem(
            reference_designator="U1",
            quantity=1,
            manufacturer="STMicroelectronics",
            manufacturer_part_number="STM32F407VGT6",
            category=ComponentCategory.IC,
        )

        result = enrichment_service.check_price_reasonableness(item, 8.50)

        assert result.is_reasonable is True
        assert result.typical_price_range_low >= 1.0

    def test_obsolescence_check_active(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test obsolescence check for active component."""
        mock_provider.complete.return_value = json.dumps(
            load_llm_fixtures['obsolescence_responses']['active_component']
        )

        item = BomItem(
            reference_designator="U1",
            quantity=1,
            manufacturer="STMicroelectronics",
            manufacturer_part_number="STM32F407VGT6",
            category=ComponentCategory.IC,
        )

        result = enrichment_service.check_obsolescence(item)

        assert result.risk_level == "low"
        assert result.lifecycle_status == "active"
        assert result.estimated_years_available >= 5

    def test_obsolescence_check_nrnd(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test obsolescence check for NRND component."""
        mock_provider.complete.return_value = json.dumps(
            load_llm_fixtures['obsolescence_responses']['nrnd_component']
        )

        item = BomItem(
            reference_designator="U2",
            quantity=1,
            manufacturer="OldVendor",
            manufacturer_part_number="OLD_PART_123",
            category=ComponentCategory.IC,
        )

        result = enrichment_service.check_obsolescence(item)

        assert result.risk_level == "medium"
        assert result.lifecycle_status.upper() == "NRND"
        assert "not recommended" in result.reasoning.lower() or "nrnd" in result.reasoning.lower()

    def test_obsolescence_check_obsolete(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test obsolescence check for obsolete component."""
        mock_provider.complete.return_value = json.dumps(
            load_llm_fixtures['obsolescence_responses']['obsolete_component']
        )

        item = BomItem(
            reference_designator="U3",
            quantity=1,
            manufacturer="OldVendor",
            manufacturer_part_number="DISCONTINUED_PART",
            category=ComponentCategory.IC,
        )

        result = enrichment_service.check_obsolescence(item)

        assert result.risk_level == "high"
        assert result.lifecycle_status == "obsolete"
        assert result.estimated_years_available == 0

    def test_batch_classification(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test batch classification of multiple components."""
        responses = [
            json.dumps(load_llm_fixtures['classification_responses']['resistor_classification']),
            json.dumps(load_llm_fixtures['classification_responses']['capacitor_classification']),
            json.dumps(load_llm_fixtures['classification_responses']['ic_classification']),
        ]
        mock_provider.complete.side_effect = responses

        items = [
            BomItem(reference_designator="R1", quantity=1),
            BomItem(reference_designator="C1", quantity=1),
            BomItem(reference_designator="U1", quantity=1),
        ]

        results = enrichment_service.classify_components_batch(items)

        assert len(results) == 3
        assert results[0].category == ComponentCategory.RESISTOR
        assert results[1].category == ComponentCategory.CAPACITOR
        assert results[2].category == ComponentCategory.IC

    def test_error_handling_invalid_json(self, enrichment_service, mock_provider):
        """Test error handling when LLM returns invalid JSON."""
        mock_provider.complete.return_value = "This is not valid JSON"

        item = BomItem(reference_designator="R1", quantity=1)

        # Should handle gracefully without crashing
        result = enrichment_service.classify_component(item)

        # Should return a result even if parsing fails
        assert result is not None

    def test_error_handling_missing_fields(self, enrichment_service, mock_provider):
        """Test error handling when response is missing required fields."""
        mock_provider.complete.return_value = json.dumps({
            "category": "resistor"
            # Missing confidence and reasoning
        })

        item = BomItem(reference_designator="R1", quantity=1)

        # Should handle gracefully
        result = enrichment_service.classify_component(item)

        assert result is not None
        assert result.category == ComponentCategory.RESISTOR

    def test_error_handling_api_failure(self, enrichment_service, mock_provider):
        """Test error handling when API call fails."""
        mock_provider.complete.side_effect = Exception("API call failed")

        item = BomItem(reference_designator="R1", quantity=1)

        # Should handle gracefully without crashing
        result = enrichment_service.classify_component(item)

        # Should return a result with low confidence or error indicator
        assert result is not None


@pytest.mark.integration
class TestLLMCaching:
    """Test LLM response caching."""

    @pytest.fixture
    def mock_provider(self):
        """Create a mock LLM provider."""
        return MagicMock(spec=LLMProvider)

    def test_cache_hit_reduces_api_calls(self, mock_provider, load_llm_fixtures):
        """Test that cached responses reduce API calls."""
        mock_provider.complete.return_value = json.dumps(
            load_llm_fixtures['classification_responses']['resistor_classification']
        )

        # Create service with caching enabled
        service = LLMEnrichmentService(provider=mock_provider, use_cache=True)

        item = BomItem(
            reference_designator="R1",
            quantity=1,
            manufacturer="Yageo",
            manufacturer_part_number="RC0603FR-0710KL",
        )

        # First call - should hit API
        result1 = service.classify_component(item)

        # Second call with same item - should use cache
        result2 = service.classify_component(item)

        # Should only call API once
        assert mock_provider.complete.call_count == 1

        # Results should be identical
        assert result1.category == result2.category
        assert result1.confidence == result2.confidence

    def test_cache_miss_on_different_items(self, mock_provider, load_llm_fixtures):
        """Test that different items result in cache misses."""
        responses = [
            json.dumps(load_llm_fixtures['classification_responses']['resistor_classification']),
            json.dumps(load_llm_fixtures['classification_responses']['capacitor_classification']),
        ]
        mock_provider.complete.side_effect = responses

        service = LLMEnrichmentService(provider=mock_provider, use_cache=True)

        item1 = BomItem(reference_designator="R1", quantity=1)
        item2 = BomItem(reference_designator="C1", quantity=1)

        # Both calls should hit API since items are different
        service.classify_component(item1)
        service.classify_component(item2)

        assert mock_provider.complete.call_count == 2
