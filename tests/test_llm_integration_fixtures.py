"""LLM integration tests with mocked API response fixtures."""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from pcb_cost_estimator.models import BomItem, ComponentCategory
from pcb_cost_estimator.llm_enrichment import LLMEnrichmentService
from pcb_cost_estimator.llm_provider import LLMProvider, LLMResponse, OpenAIProvider, AnthropicProvider


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

        with patch('pcb_cost_estimator.llm_provider.Anthropic') as mock_anthropic:
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

    def _mock_response(self, mock_provider, fixture_data):
        """Helper to mock call_with_retry with a fixture response."""
        mock_provider.call_with_retry.return_value = LLMResponse(
            success=True, data=fixture_data, raw_response=json.dumps(fixture_data)
        )

    def test_classify_resistor(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test resistor classification with mocked response."""
        fixture_data = load_llm_fixtures['classification_responses']['resistor_classification']
        self._mock_response(mock_provider, fixture_data)

        result = enrichment_service.classify_component(
            mpn="RC0603FR-0710KL",
            description="Resistor 1K 1% 1/10W",
            reference_designator="R1",
        )

        assert result is not None
        assert result.category == ComponentCategory.RESISTOR
        assert result.confidence >= 0.9
        assert "resistor" in result.reasoning.lower()

    def test_classify_capacitor(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test capacitor classification with mocked response."""
        fixture_data = load_llm_fixtures['classification_responses']['capacitor_classification']
        self._mock_response(mock_provider, fixture_data)

        result = enrichment_service.classify_component(
            mpn="GRM188R71C104KA01D",
            description="Cap Ceramic 0.1uF 16V X7R",
            reference_designator="C1",
        )

        assert result is not None
        assert result.category == ComponentCategory.CAPACITOR
        assert result.confidence >= 0.9

    def test_classify_ic(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test IC classification with mocked response."""
        fixture_data = load_llm_fixtures['classification_responses']['ic_classification']
        self._mock_response(mock_provider, fixture_data)

        result = enrichment_service.classify_component(
            mpn="STM32F407VGT6",
            description="MCU ARM Cortex-M4 1MB Flash",
            reference_designator="U1",
        )

        assert result is not None
        assert result.category == ComponentCategory.IC
        assert result.confidence >= 0.9

    def test_classify_unknown_low_confidence(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test classification with low confidence."""
        fixture_data = load_llm_fixtures['classification_responses']['unknown_classification']
        self._mock_response(mock_provider, fixture_data)

        result = enrichment_service.classify_component(
            mpn="",
            description="Unknown Component",
            reference_designator="X1",
        )

        assert result is not None
        assert result.confidence < 0.5

    def test_price_reasonableness_check_valid(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test price reasonableness check for valid price."""
        fixture_data = load_llm_fixtures['price_reasonableness_responses']['resistor_reasonable']
        self._mock_response(mock_provider, fixture_data)

        result = enrichment_service.check_price_reasonableness(
            mpn="RC0603FR-0710KL",
            description="Resistor 0603",
            category="resistor",
            package_type="0603",
            unit_cost_low=0.008,
            unit_cost_typical=0.01,
            unit_cost_high=0.015,
            quantity=1,
        )

        assert result is not None
        assert result.is_reasonable is True
        assert result.confidence >= 0.9
        assert result.typical_price_range_low is not None
        assert result.typical_price_range_high is not None

    def test_price_reasonableness_check_too_high(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test price reasonableness check for price too high."""
        fixture_data = load_llm_fixtures['price_reasonableness_responses']['resistor_too_high']
        self._mock_response(mock_provider, fixture_data)

        result = enrichment_service.check_price_reasonableness(
            mpn="RC0603FR-0710KL",
            description="Resistor 0603",
            category="resistor",
            package_type="0603",
            unit_cost_low=0.9,
            unit_cost_typical=1.0,
            unit_cost_high=1.1,
            quantity=1,
        )

        assert result is not None
        assert result.is_reasonable is False
        assert "higher" in result.reasoning.lower() or "error" in result.reasoning.lower()

    def test_price_reasonableness_check_ic(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test price reasonableness check for IC."""
        fixture_data = load_llm_fixtures['price_reasonableness_responses']['ic_reasonable']
        self._mock_response(mock_provider, fixture_data)

        result = enrichment_service.check_price_reasonableness(
            mpn="STM32F407VGT6",
            description="MCU ARM Cortex-M4",
            category="ic",
            package_type="LQFP-100",
            unit_cost_low=7.0,
            unit_cost_typical=8.50,
            unit_cost_high=10.0,
            quantity=1,
        )

        assert result is not None
        assert result.is_reasonable is True
        assert result.typical_price_range_low >= 1.0

    def test_obsolescence_check_active(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test obsolescence check for active component."""
        fixture_data = load_llm_fixtures['obsolescence_responses']['active_component']
        self._mock_response(mock_provider, fixture_data)

        result = enrichment_service.check_obsolescence(
            mpn="STM32F407VGT6",
            manufacturer="STMicroelectronics",
        )

        assert result is not None
        assert result.risk_level == "low"
        assert result.lifecycle_status == "active"
        assert result.estimated_years_available >= 5

    def test_obsolescence_check_nrnd(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test obsolescence check for NRND component."""
        fixture_data = load_llm_fixtures['obsolescence_responses']['nrnd_component']
        self._mock_response(mock_provider, fixture_data)

        result = enrichment_service.check_obsolescence(
            mpn="OLD_PART_123",
            manufacturer="OldVendor",
        )

        assert result is not None
        assert result.risk_level == "medium"
        assert result.lifecycle_status.upper() == "NRND"
        assert "not recommended" in result.reasoning.lower() or "nrnd" in result.reasoning.lower()

    def test_obsolescence_check_obsolete(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test obsolescence check for obsolete component."""
        fixture_data = load_llm_fixtures['obsolescence_responses']['obsolete_component']
        self._mock_response(mock_provider, fixture_data)

        result = enrichment_service.check_obsolescence(
            mpn="DISCONTINUED_PART",
            manufacturer="OldVendor",
        )

        assert result is not None
        assert result.risk_level == "high"
        assert result.lifecycle_status == "obsolete"
        assert result.estimated_years_available == 0

    def test_batch_classification(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test batch classification of multiple components."""
        fixture_data_list = [
            load_llm_fixtures['classification_responses']['resistor_classification'],
            load_llm_fixtures['classification_responses']['capacitor_classification'],
            load_llm_fixtures['classification_responses']['ic_classification'],
        ]
        mock_provider.call_with_retry.side_effect = [
            LLMResponse(success=True, data=d, raw_response=json.dumps(d))
            for d in fixture_data_list
        ]

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
        """Test error handling when LLM returns error response."""
        mock_provider.call_with_retry.return_value = LLMResponse(
            success=False,
            error="Invalid JSON response",
            raw_response="This is not valid JSON",
        )

        # Service returns None when API call fails
        result = enrichment_service.classify_component(
            mpn="UNKNOWN_PART", reference_designator="R1"
        )

        assert result is None

    def test_error_handling_missing_fields(self, enrichment_service, mock_provider):
        """Test error handling when response is missing optional fields."""
        partial_data = {"category": "resistor"}
        mock_provider.call_with_retry.return_value = LLMResponse(
            success=True,
            data=partial_data,
            raw_response=json.dumps(partial_data),
        )

        result = enrichment_service.classify_component(
            mpn="RC0603FR-0710KL", reference_designator="R1"
        )

        assert result is not None
        assert result.category == ComponentCategory.RESISTOR

    def test_error_handling_api_failure(self, enrichment_service, mock_provider):
        """Test error handling when API call fails."""
        mock_provider.call_with_retry.return_value = LLMResponse(
            success=False, error="API call failed"
        )

        # Use a unique MPN to avoid cache hits from other tests
        result = enrichment_service.classify_component(
            mpn="NONEXISTENT-PART-API-FAILURE-TEST", reference_designator="Z99"
        )

        # Returns None when the API call fails
        assert result is None


@pytest.mark.integration
class TestLLMCaching:
    """Test LLM response caching."""

    @pytest.fixture
    def mock_provider(self):
        """Create a mock LLM provider."""
        return MagicMock(spec=LLMProvider)

    def test_cache_hit_reduces_api_calls(self, mock_provider, load_llm_fixtures, tmp_path):
        """Test that cached responses reduce API calls."""
        from pcb_cost_estimator.llm_cache import LLMCache

        fixture_data = load_llm_fixtures['classification_responses']['resistor_classification']
        mock_provider.call_with_retry.return_value = LLMResponse(
            success=True, data=fixture_data, raw_response=json.dumps(fixture_data)
        )

        # Create service with a fresh temporary cache to avoid cross-test contamination
        temp_cache = LLMCache(cache_file=tmp_path / "test_cache.db")
        service = LLMEnrichmentService(provider=mock_provider, cache=temp_cache)

        # First call - should hit API
        result1 = service.classify_component(
            mpn="RC0603FR-0710KL",
            description="Resistor 1K 1% 1/10W",
            reference_designator="R1",
        )

        # Second call with same params - should use cache
        result2 = service.classify_component(
            mpn="RC0603FR-0710KL",
            description="Resistor 1K 1% 1/10W",
            reference_designator="R1",
        )

        # Should only call API once
        assert mock_provider.call_with_retry.call_count == 1

        # Results should be identical
        assert result1 is not None
        assert result2 is not None
        assert result1.category == result2.category
        assert result1.confidence == result2.confidence

    def test_cache_miss_on_different_items(self, mock_provider, load_llm_fixtures, tmp_path):
        """Test that different items result in cache misses."""
        from pcb_cost_estimator.llm_cache import LLMCache

        fixture_data_list = [
            load_llm_fixtures['classification_responses']['resistor_classification'],
            load_llm_fixtures['classification_responses']['capacitor_classification'],
        ]
        mock_provider.call_with_retry.side_effect = [
            LLMResponse(success=True, data=d, raw_response=json.dumps(d))
            for d in fixture_data_list
        ]

        # Use a fresh temporary cache for isolation
        temp_cache = LLMCache(cache_file=tmp_path / "test_cache2.db")
        service = LLMEnrichmentService(provider=mock_provider, cache=temp_cache)

        # Both calls should hit API since MPNs are different
        service.classify_component(mpn="RC0603FR-0710KL", reference_designator="R1")
        service.classify_component(mpn="GRM188R71C104KA01D", reference_designator="C1")

        assert mock_provider.call_with_retry.call_count == 2
