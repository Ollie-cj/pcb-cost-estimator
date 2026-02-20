"""LLM integration tests with mocked API response fixtures."""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from pcb_cost_estimator.models import BomItem, ComponentCategory
from pcb_cost_estimator.llm_enrichment import LLMEnrichmentService
from pcb_cost_estimator.llm_provider import LLMProvider, LLMResponse, OpenAIProvider, AnthropicProvider
from pcb_cost_estimator.llm_cache import LLMCache


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
    """Create a successful LLMResponse with the given data."""
    return LLMResponse(
        success=True,
        data=data,
        raw_response=json.dumps(data),
        tokens_used=100
    )


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
        mock_response.usage = MagicMock(prompt_tokens=50, completion_tokens=50)

        with patch('pcb_cost_estimator.llm_provider.openai.OpenAI') as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            provider = OpenAIProvider(api_key="test_key")
            result = provider.call("Classify this component: R1")

            assert result is not None
            assert result.success is True
            parsed = result.data
            assert parsed['category'] == 'resistor'
            assert parsed['confidence'] == 0.98

    def test_anthropic_provider_classification(self, load_llm_fixtures):
        """Test Anthropic provider with mocked classification response."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps(
            load_llm_fixtures['classification_responses']['ic_classification']
        )
        mock_response.usage = MagicMock(input_tokens=50, output_tokens=50)

        with patch('pcb_cost_estimator.llm_provider.Anthropic') as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            provider = AnthropicProvider(api_key="test_key")
            result = provider.call("Classify this component")

            assert result is not None
            assert result.success is True
            assert result.data['category'] == 'ic'
            assert result.data['confidence'] == 0.99


@pytest.mark.integration
class TestLLMEnrichmentWithFixtures:
    """Test LLM enrichment service with mocked fixtures."""

    @pytest.fixture
    def mock_provider(self):
        """Create a mock LLM provider."""
        return MagicMock(spec=LLMProvider)

    @pytest.fixture
    def enrichment_service(self, mock_provider, tmp_path):
        """Create enrichment service with mock provider and temp cache."""
        cache = LLMCache(cache_file=tmp_path / "test_cache.db")
        return LLMEnrichmentService(provider=mock_provider, cache=cache)

    def test_classify_resistor(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test resistor classification with mocked response."""
        mock_provider.call_with_retry.return_value = make_llm_response(
            load_llm_fixtures['classification_responses']['resistor_classification']
        )

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
        mock_provider.call_with_retry.return_value = make_llm_response(
            load_llm_fixtures['classification_responses']['capacitor_classification']
        )

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
        mock_provider.call_with_retry.return_value = make_llm_response(
            load_llm_fixtures['classification_responses']['ic_classification']
        )

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
        mock_provider.call_with_retry.return_value = make_llm_response(
            load_llm_fixtures['classification_responses']['unknown_classification']
        )

        result = enrichment_service.classify_component(
            mpn="",
            description="Unknown Component",
            reference_designator="X1",
        )

        assert result is not None
        assert result.confidence < 0.5

    def test_price_reasonableness_check_valid(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test price reasonableness check for valid price."""
        mock_provider.call_with_retry.return_value = make_llm_response(
            load_llm_fixtures['price_reasonableness_responses']['resistor_reasonable']
        )

        result = enrichment_service.check_price_reasonableness(
            mpn="RC0603FR-0710KL",
            description="Resistor 10k 0603",
            category="resistor",
            package_type="smd_small",
            unit_cost_low=0.005,
            unit_cost_typical=0.01,
            unit_cost_high=0.02,
            quantity=100,
        )

        assert result is not None
        assert result.is_reasonable is True
        assert result.confidence >= 0.9

    def test_price_reasonableness_check_too_high(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test price reasonableness check for price too high."""
        mock_provider.call_with_retry.return_value = make_llm_response(
            load_llm_fixtures['price_reasonableness_responses']['resistor_too_high']
        )

        result = enrichment_service.check_price_reasonableness(
            mpn="RC0603FR-0710KL",
            description="Resistor 10k 0603",
            category="resistor",
            package_type="smd_small",
            unit_cost_low=0.80,
            unit_cost_typical=1.00,
            unit_cost_high=1.20,
            quantity=100,
        )

        assert result is not None
        assert result.is_reasonable is False
        assert result.reasoning is not None

    def test_price_reasonableness_check_ic(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test price reasonableness check for IC."""
        mock_provider.call_with_retry.return_value = make_llm_response(
            load_llm_fixtures['price_reasonableness_responses']['ic_reasonable']
        )

        result = enrichment_service.check_price_reasonableness(
            mpn="STM32F407VGT6",
            description="MCU ARM Cortex-M4",
            category="ic",
            package_type="qfp",
            unit_cost_low=5.0,
            unit_cost_typical=8.50,
            unit_cost_high=12.0,
            quantity=1,
        )

        assert result is not None
        assert result.is_reasonable is True
        assert result.expected_price_range is not None
        assert result.expected_price_range.get('low', 0) >= 1.0

    def test_obsolescence_check_active(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test obsolescence check for active component."""
        mock_provider.call_with_retry.return_value = make_llm_response(
            load_llm_fixtures['obsolescence_responses']['active_component']
        )

        result = enrichment_service.check_obsolescence(
            mpn="STM32F407VGT6",
            manufacturer="STMicroelectronics",
            description="MCU ARM Cortex-M4 1MB Flash",
            category="ic",
        )

        assert result is not None
        assert result.obsolescence_risk in ["none", "low"]
        assert result.lifecycle_status == "active"

    def test_obsolescence_check_nrnd(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test obsolescence check for NRND component."""
        mock_provider.call_with_retry.return_value = make_llm_response(
            load_llm_fixtures['obsolescence_responses']['nrnd_component']
        )

        result = enrichment_service.check_obsolescence(
            mpn="OLD_PART_123",
            manufacturer="OldVendor",
        )

        assert result is not None
        assert result.obsolescence_risk == "medium"
        assert result.lifecycle_status.lower() == "nrnd"
        assert "not recommended" in result.reasoning.lower() or "nrnd" in result.reasoning.lower()

    def test_obsolescence_check_obsolete(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test obsolescence check for obsolete component."""
        mock_provider.call_with_retry.return_value = make_llm_response(
            load_llm_fixtures['obsolescence_responses']['obsolete_component']
        )

        result = enrichment_service.check_obsolescence(
            mpn="DISCONTINUED_PART",
            manufacturer="OldVendor",
        )

        assert result is not None
        assert result.obsolescence_risk == "high"
        assert result.lifecycle_status == "obsolete"

    def test_batch_obsolescence_check(self, enrichment_service, mock_provider, load_llm_fixtures):
        """Test batch obsolescence check of multiple components."""
        responses = [
            make_llm_response(load_llm_fixtures['obsolescence_responses']['active_component']),
            make_llm_response(load_llm_fixtures['obsolescence_responses']['nrnd_component']),
            make_llm_response(load_llm_fixtures['obsolescence_responses']['obsolete_component']),
        ]
        mock_provider.call_with_retry.side_effect = responses

        components = [
            {"mpn": "STM32F407VGT6", "manufacturer": "STMicro", "category": "ic"},
            {"mpn": "OLD_PART_123", "manufacturer": "OldVendor", "category": "ic"},
            {"mpn": "DISCONTINUED", "manufacturer": "OldVendor", "category": "ic"},
        ]

        results = enrichment_service.batch_check_obsolescence(components)

        assert len(results) == 3
        assert results[0].obsolescence_risk in ["none", "low"]
        assert results[1].obsolescence_risk == "medium"
        assert results[2].obsolescence_risk == "high"

    def test_error_handling_api_failure(self, enrichment_service, mock_provider):
        """Test error handling when API call fails."""
        mock_provider.call_with_retry.return_value = LLMResponse(
            success=False,
            data=None,
            error="API call failed"
        )

        # Should handle gracefully without crashing
        result = enrichment_service.classify_component(
            mpn="RC0603FR-0710KL",
            description="Resistor",
            reference_designator="R1",
        )

        # Service returns None when LLM fails
        assert result is None

    def test_error_handling_missing_fields(self, enrichment_service, mock_provider):
        """Test error handling when response is missing optional fields."""
        mock_provider.call_with_retry.return_value = make_llm_response({
            "category": "resistor",
            "confidence": 0.85,
            # Missing reasoning - should use default
        })

        result = enrichment_service.classify_component(
            mpn="RC0603FR-0710KL",
            description="Resistor",
            reference_designator="R1",
        )

        assert result is not None
        assert result.category == ComponentCategory.RESISTOR


@pytest.mark.integration
class TestLLMCaching:
    """Test LLM response caching."""

    @pytest.fixture
    def mock_provider(self):
        """Create a mock LLM provider."""
        return MagicMock(spec=LLMProvider)

    def test_cache_hit_reduces_api_calls(self, mock_provider, load_llm_fixtures, tmp_path):
        """Test that cached responses reduce API calls."""
        mock_provider.call_with_retry.return_value = make_llm_response(
            load_llm_fixtures['classification_responses']['resistor_classification']
        )

        # Create service with caching enabled
        cache = LLMCache(cache_file=tmp_path / "test_cache.db")
        service = LLMEnrichmentService(provider=mock_provider, cache=cache)

        mpn = "RC0603FR-0710KL"

        # First call - should hit API
        result1 = service.classify_component(mpn=mpn, description="Resistor 1K", reference_designator="R1")

        # Second call with same MPN - should use cache
        result2 = service.classify_component(mpn=mpn, description="Resistor 1K", reference_designator="R1")

        # Should only call API once
        assert mock_provider.call_with_retry.call_count == 1

        # Results should be equivalent
        assert result1 is not None
        assert result2 is not None
        assert result1.category == result2.category

    def test_cache_miss_on_different_items(self, mock_provider, load_llm_fixtures, tmp_path):
        """Test that different MPNs result in cache misses."""
        responses = [
            make_llm_response(load_llm_fixtures['classification_responses']['resistor_classification']),
            make_llm_response(load_llm_fixtures['classification_responses']['capacitor_classification']),
        ]
        mock_provider.call_with_retry.side_effect = responses

        cache = LLMCache(cache_file=tmp_path / "test_cache.db")
        service = LLMEnrichmentService(provider=mock_provider, cache=cache)

        # Both calls should hit API since MPNs are different
        service.classify_component(mpn="RC0603FR-0710KL", description="Resistor")
        service.classify_component(mpn="GRM188R71C104KA01D", description="Capacitor")

        assert mock_provider.call_with_retry.call_count == 2
