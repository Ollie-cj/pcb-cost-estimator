"""LLM integration tests with mocked API response fixtures."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

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


def make_llm_response(data: dict) -> LLMResponse:
    """Helper to create a successful LLMResponse with the given data."""
    return LLMResponse(success=True, data=data, raw_response=json.dumps(data))


@pytest.mark.integration
class TestLLMProviderWithMockedResponses:
    """Test LLM provider with mocked API responses."""

    def test_openai_provider_classification(self, load_llm_fixtures):
        """Test OpenAI provider with mocked classification response."""
        fixture_data = load_llm_fixtures['classification_responses']['resistor_classification']
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(fixture_data)
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 50

        with patch('pcb_cost_estimator.llm_provider.openai.OpenAI') as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            provider = OpenAIProvider(api_key="test_key")
            response = provider.call_with_retry("Classify this component: R1")

            assert response.success
            assert response.data is not None
            assert response.data['category'] == 'resistor'
            assert response.data['confidence'] == 0.98

    def test_anthropic_provider_classification(self, load_llm_fixtures):
        """Test Anthropic provider with mocked classification response."""
        fixture_data = load_llm_fixtures['classification_responses']['capacitor_classification']
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps(fixture_data)
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 30
        mock_response.usage.output_tokens = 20

        with patch('pcb_cost_estimator.llm_provider.Anthropic') as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            provider = AnthropicProvider(api_key="test_key")
            response = provider.call_with_retry("Classify this component: C1")

            assert response.success
            assert response.data is not None
            assert response.data['category'] == 'capacitor'
            assert response.data['confidence'] == 0.97

    def test_provider_handles_json_in_markdown(self, load_llm_fixtures):
        """Test provider correctly extracts JSON from markdown code blocks."""
        fixture_data = load_llm_fixtures['classification_responses']['ic_classification']
        markdown_response = f"```json\n{json.dumps(fixture_data)}\n```"

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = markdown_response
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 60

        with patch('pcb_cost_estimator.llm_provider.openai.OpenAI') as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            provider = OpenAIProvider(api_key="test_key")
            response = provider.call_with_retry("Classify this component")

            assert response.success
            assert response.data is not None
            assert response.data['category'] == 'ic'
            assert response.data['confidence'] == 0.99


@pytest.mark.integration
class TestLLMEnrichmentWithFixtures:
    """Test LLM enrichment service with mocked fixtures."""

    @pytest.fixture
    def mock_provider(self):
        """Create a mock LLM provider."""
        mock = MagicMock(spec=LLMProvider)
        mock.call_with_retry.return_value = LLMResponse(success=False, error="not mocked")
        return mock

    @pytest.fixture
    def enrichment_service(self, mock_provider):
        """Create enrichment service with mock provider."""
        return LLMEnrichmentService(provider=mock_provider)

    def test_classify_resistor(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test resistor classification with mocked response."""
        fixture_data = load_llm_fixtures['classification_responses']['resistor_classification']
        mock_provider.call_with_retry.return_value = make_llm_response(fixture_data)

        result = enrichment_service.classify_component(
            mpn="RC0603FR-0710KL",
            description="Resistor 1K 1% 1/10W",
            reference_designator="R1"
        )

        assert result is not None
        assert result.category == ComponentCategory.RESISTOR
        assert result.confidence >= 0.9
        assert "resistor" in result.reasoning.lower()

    def test_classify_capacitor(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test capacitor classification with mocked response."""
        fixture_data = load_llm_fixtures['classification_responses']['capacitor_classification']
        mock_provider.call_with_retry.return_value = make_llm_response(fixture_data)

        result = enrichment_service.classify_component(
            mpn="GRM188R71C104KA01D",
            description="Cap Ceramic 0.1uF 16V X7R",
            reference_designator="C1"
        )

        assert result is not None
        assert result.category == ComponentCategory.CAPACITOR
        assert result.confidence >= 0.9

    def test_classify_ic(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test IC classification with mocked response."""
        fixture_data = load_llm_fixtures['classification_responses']['ic_classification']
        mock_provider.call_with_retry.return_value = make_llm_response(fixture_data)

        result = enrichment_service.classify_component(
            mpn="STM32F407VGT6",
            description="MCU ARM Cortex-M4 1MB Flash",
            reference_designator="U1"
        )

        assert result is not None
        assert result.category == ComponentCategory.IC
        assert result.confidence >= 0.9

    def test_classify_unknown_low_confidence(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test classification with low confidence."""
        fixture_data = load_llm_fixtures['classification_responses']['unknown_classification']
        mock_provider.call_with_retry.return_value = make_llm_response(fixture_data)

        result = enrichment_service.classify_component(
            mpn="",
            description="Unknown Component",
            reference_designator="X1"
        )

        assert result is not None
        assert result.confidence < 0.5

    def test_price_reasonableness_check_valid(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test price reasonableness check for valid price."""
        fixture_data = load_llm_fixtures['price_reasonableness_responses']['resistor_reasonable']
        mock_provider.call_with_retry.return_value = make_llm_response(fixture_data)

        result = enrichment_service.check_price_reasonableness(
            mpn="RC0603FR-0710KL",
            description="Resistor 1K 0603",
            category="resistor",
            package_type="smd_small",
            unit_cost_low=0.005,
            unit_cost_typical=0.01,
            unit_cost_high=0.02,
            quantity=1
        )

        assert result is not None
        assert result.is_reasonable is True
        assert result.confidence >= 0.9
        assert result.expected_price_range is not None
        assert result.expected_price_range["low"] > 0

    def test_price_reasonableness_check_too_high(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test price reasonableness check for price too high."""
        fixture_data = load_llm_fixtures['price_reasonableness_responses']['resistor_too_high']
        mock_provider.call_with_retry.return_value = make_llm_response(fixture_data)

        result = enrichment_service.check_price_reasonableness(
            mpn="RC0603FR-0710KL",
            description="Resistor 1K 0603",
            category="resistor",
            package_type="smd_small",
            unit_cost_low=0.80,
            unit_cost_typical=1.00,
            unit_cost_high=1.20,
            quantity=1
        )

        assert result is not None
        assert result.is_reasonable is False
        assert result.reasoning is not None

    def test_price_reasonableness_check_ic(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test price reasonableness check for IC."""
        fixture_data = load_llm_fixtures['price_reasonableness_responses']['ic_reasonable']
        mock_provider.call_with_retry.return_value = make_llm_response(fixture_data)

        result = enrichment_service.check_price_reasonableness(
            mpn="STM32F407VGT6",
            description="MCU ARM Cortex-M4",
            category="ic",
            package_type="qfp",
            unit_cost_low=7.00,
            unit_cost_typical=8.50,
            unit_cost_high=10.00,
            quantity=1
        )

        assert result is not None
        assert result.is_reasonable is True
        assert result.expected_price_range["low"] >= 1.0

    def test_obsolescence_check_active(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test obsolescence check for active component."""
        fixture_data = load_llm_fixtures['obsolescence_responses']['active_component']
        mock_provider.call_with_retry.return_value = make_llm_response(fixture_data)

        result = enrichment_service.check_obsolescence(
            mpn="STM32F407VGT6",
            manufacturer="STMicroelectronics",
            description="MCU ARM Cortex-M4",
            category="ic",
            quantity=1
        )

        assert result is not None
        assert result.obsolescence_risk == "low"
        assert result.lifecycle_status == "active"

    def test_obsolescence_check_nrnd(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test obsolescence check for NRND component."""
        fixture_data = load_llm_fixtures['obsolescence_responses']['nrnd_component']
        mock_provider.call_with_retry.return_value = make_llm_response(fixture_data)

        result = enrichment_service.check_obsolescence(
            mpn="OLD_PART_123",
            manufacturer="OldVendor",
            description="Legacy IC",
            category="ic",
            quantity=1
        )

        assert result is not None
        assert result.obsolescence_risk == "medium"
        assert result.lifecycle_status.upper() == "NRND"
        assert "not recommended" in result.reasoning.lower() or "nrnd" in result.reasoning.lower()

    def test_obsolescence_check_obsolete(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test obsolescence check for obsolete component."""
        fixture_data = load_llm_fixtures['obsolescence_responses']['obsolete_component']
        mock_provider.call_with_retry.return_value = make_llm_response(fixture_data)

        result = enrichment_service.check_obsolescence(
            mpn="DISCONTINUED_PART",
            manufacturer="OldVendor",
            description="Obsolete IC",
            category="ic",
            quantity=1
        )

        assert result is not None
        assert result.obsolescence_risk == "high"
        assert result.lifecycle_status == "obsolete"

    def test_batch_classification(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test classification of multiple components individually."""
        fixtures = load_llm_fixtures['classification_responses']
        mock_provider.call_with_retry.side_effect = [
            make_llm_response(fixtures['resistor_classification']),
            make_llm_response(fixtures['capacitor_classification']),
            make_llm_response(fixtures['ic_classification']),
        ]

        items = [
            ("RC0603FR-0710KL", "Resistor 1K", "R1"),
            ("GRM188R71C104KA01D", "Cap 100nF", "C1"),
            ("STM32F407VGT6", "MCU ARM", "U1"),
        ]

        results = [
            enrichment_service.classify_component(mpn, desc, ref)
            for mpn, desc, ref in items
        ]

        assert len(results) == 3
        assert all(r is not None for r in results)
        assert results[0].category == ComponentCategory.RESISTOR
        assert results[1].category == ComponentCategory.CAPACITOR
        assert results[2].category == ComponentCategory.IC

    def test_error_handling_invalid_json(self, enrichment_service, mock_provider):
        """Test error handling when LLM returns no data."""
        mock_provider.call_with_retry.return_value = LLMResponse(
            success=True,
            data=None,
            raw_response="This is not valid JSON"
        )

        result = enrichment_service.classify_component(
            mpn="UNIQUE_MPN_NO_DATA_TEST_ABC123",
            description="Test part for no-data handling",
            reference_designator="T1"
        )

        # Should return None gracefully when data is absent
        assert result is None

    def test_error_handling_missing_fields(self, enrichment_service, mock_provider):
        """Test error handling when response is missing optional fields."""
        mock_provider.call_with_retry.return_value = make_llm_response({
            "category": "resistor"
            # Missing confidence and reasoning - should use defaults (0.0, None)
        })

        result = enrichment_service.classify_component(
            mpn="R1",
            description="Resistor",
            reference_designator="R1"
        )

        # Should handle gracefully with defaults
        assert result is not None
        assert result.category == ComponentCategory.RESISTOR

    def test_error_handling_api_failure(self, enrichment_service, mock_provider):
        """Test error handling when API call fails."""
        mock_provider.call_with_retry.return_value = LLMResponse(
            success=False,
            error="API call failed"
        )

        result = enrichment_service.classify_component(
            mpn="UNIQUE_MPN_FOR_FAILURE_TEST_XYZ",
            description="Unknown part for failure test",
            reference_designator="X99"
        )

        # Should return None when API fails
        assert result is None


@pytest.mark.integration
class TestLLMCaching:
    """Test LLM response caching."""

    @pytest.fixture
    def mock_provider(self):
        """Create a mock LLM provider."""
        mock = MagicMock(spec=LLMProvider)
        mock.call_with_retry.return_value = LLMResponse(success=False, error="not mocked")
        return mock

    def test_cache_hit_reduces_api_calls(self, mock_provider, load_llm_fixtures, tmp_path):
        """Test that cached responses reduce API calls."""
        from pcb_cost_estimator.llm_cache import LLMCache
        cache = LLMCache(cache_file=tmp_path / "test_cache.db")

        fixture_data = load_llm_fixtures['classification_responses']['resistor_classification']
        mock_provider.call_with_retry.return_value = make_llm_response(fixture_data)

        # Create service with explicit temporary cache
        service = LLMEnrichmentService(provider=mock_provider, cache=cache)

        mpn = "RC0603FR-0710KL"

        # First call - should hit API
        result1 = service.classify_component(
            mpn=mpn,
            description="Resistor 1K",
            reference_designator="R1"
        )

        # Second call with same MPN - should use cache
        result2 = service.classify_component(
            mpn=mpn,
            description="Resistor 1K",
            reference_designator="R1"
        )

        # Should only call API once (second uses cache)
        assert mock_provider.call_with_retry.call_count == 1
        assert result1 is not None
        assert result2 is not None
        assert result1.category == result2.category

    def test_cache_miss_on_different_items(self, mock_provider, load_llm_fixtures, tmp_path):
        """Test that different items result in cache misses."""
        from pcb_cost_estimator.llm_cache import LLMCache
        cache = LLMCache(cache_file=tmp_path / "test_cache.db")

        fixtures = load_llm_fixtures['classification_responses']
        mock_provider.call_with_retry.side_effect = [
            make_llm_response(fixtures['resistor_classification']),
            make_llm_response(fixtures['capacitor_classification']),
        ]

        service = LLMEnrichmentService(provider=mock_provider, cache=cache)

        # Different MPNs should cause cache misses
        service.classify_component(mpn="RC0603FR-0710KL", description="Resistor", reference_designator="R1")
        service.classify_component(mpn="GRM188R71C104KA01D", description="Capacitor", reference_designator="C1")

        assert mock_provider.call_with_retry.call_count == 2
