"""Tests for LLM enrichment functionality."""

import json
from unittest.mock import Mock, MagicMock, patch
import pytest

from pcb_cost_estimator.llm_provider import (
    LLMProvider,
    LLMResponse,
    OpenAIProvider,
    AnthropicProvider,
    create_llm_provider,
)
from pcb_cost_estimator.llm_cache import LLMCache
from pcb_cost_estimator.llm_enrichment import (
    LLMEnrichmentService,
    ComponentClassificationResult,
    PriceReasonablenessResult,
    ObsolescenceRisk,
    create_enrichment_service,
)
from pcb_cost_estimator.models import ComponentCategory


class TestLLMProvider:
    """Tests for LLM provider abstraction."""

    def test_parse_json_response_valid(self):
        """Test parsing valid JSON response."""
        json_str = '{"category": "resistor", "confidence": 0.95}'
        success, data, error = LLMProvider.parse_json_response(json_str)

        assert success is True
        assert data == {"category": "resistor", "confidence": 0.95}
        assert error is None

    def test_parse_json_response_markdown_block(self):
        """Test parsing JSON from markdown code block."""
        json_str = '```json\n{"category": "capacitor", "confidence": 0.9}\n```'
        success, data, error = LLMProvider.parse_json_response(json_str)

        assert success is True
        assert data == {"category": "capacitor", "confidence": 0.9}
        assert error is None

    def test_parse_json_response_invalid(self):
        """Test parsing invalid JSON."""
        json_str = 'This is not JSON'
        success, data, error = LLMProvider.parse_json_response(json_str)

        assert success is False
        assert data is None
        assert error is not None

    def test_create_llm_provider_openai(self):
        """Test creating OpenAI provider."""
        provider = create_llm_provider(
            provider="openai",
            api_key="test-key",
            model="gpt-4o-mini"
        )

        assert isinstance(provider, OpenAIProvider)
        assert provider.model == "gpt-4o-mini"

    def test_create_llm_provider_anthropic(self):
        """Test creating Anthropic provider."""
        provider = create_llm_provider(
            provider="anthropic",
            api_key="test-key",
            model="claude-3-5-sonnet-20241022"
        )

        assert isinstance(provider, AnthropicProvider)
        assert provider.model == "claude-3-5-sonnet-20241022"

    def test_create_llm_provider_invalid(self):
        """Test creating provider with invalid name."""
        with pytest.raises(ValueError):
            create_llm_provider(
                provider="invalid",
                api_key="test-key"
            )

    @patch('openai.OpenAI')
    def test_openai_provider_call_success(self, mock_openai):
        """Test successful OpenAI API call."""
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content='{"result": "success"}'))]
        mock_response.usage = Mock(total_tokens=100)

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        provider = OpenAIProvider(api_key="test-key")
        response = provider.call("Test prompt", json_mode=True)

        assert response.success is True
        assert response.data == {"result": "success"}
        assert response.tokens_used == 100

    @patch('anthropic.Anthropic')
    def test_anthropic_provider_call_success(self, mock_anthropic):
        """Test successful Anthropic API call."""
        # Mock Anthropic response
        mock_content = Mock(text='{"result": "success"}')
        mock_response = Mock()
        mock_response.content = [mock_content]
        mock_response.usage = Mock(input_tokens=50, output_tokens=50)

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        provider = AnthropicProvider(api_key="test-key")
        response = provider.call("Test prompt", json_mode=True)

        assert response.success is True
        assert response.data == {"result": "success"}
        assert response.tokens_used == 100


class TestLLMCache:
    """Tests for LLM cache."""

    def test_cache_set_and_get(self, tmp_path):
        """Test setting and getting cache entries."""
        cache = LLMCache(cache_file=tmp_path / "test_cache.db")

        # Set cache entry
        response_data = {"category": "resistor", "confidence": 0.95}
        success = cache.set(
            prompt_type="classification",
            mpn="RC0603FR-0710KL",
            response_data=response_data,
            tokens_used=100
        )

        assert success is True

        # Get cache entry
        cached_data = cache.get(
            prompt_type="classification",
            mpn="RC0603FR-0710KL"
        )

        assert cached_data == response_data

    def test_cache_miss(self, tmp_path):
        """Test cache miss."""
        cache = LLMCache(cache_file=tmp_path / "test_cache.db")

        cached_data = cache.get(
            prompt_type="classification",
            mpn="NONEXISTENT"
        )

        assert cached_data is None

    def test_cache_clear(self, tmp_path):
        """Test clearing cache."""
        cache = LLMCache(cache_file=tmp_path / "test_cache.db")

        # Add entry
        cache.set(
            prompt_type="classification",
            mpn="TEST123",
            response_data={"test": "data"},
            tokens_used=50
        )

        # Clear cache
        deleted = cache.clear()
        assert deleted == 1

        # Verify entry is gone
        cached_data = cache.get("classification", "TEST123")
        assert cached_data is None

    def test_cache_stats(self, tmp_path):
        """Test getting cache statistics."""
        cache = LLMCache(cache_file=tmp_path / "test_cache.db")

        # Add some entries
        cache.set("classification", "MPN1", {"data": 1}, tokens_used=100)
        cache.set("price_check", "MPN2", {"data": 2}, tokens_used=150)

        stats = cache.get_stats()

        assert stats["total_entries"] == 2
        assert stats["total_tokens_saved"] == 250
        assert "classification" in stats["by_prompt_type"]
        assert "price_check" in stats["by_prompt_type"]


class TestLLMEnrichmentService:
    """Tests for LLM enrichment service."""

    def test_service_disabled_mode(self):
        """Test service in disabled mode."""
        service = LLMEnrichmentService(provider=None, enabled=False)

        result = service.classify_component(
            mpn="TEST123",
            description="Test component"
        )

        assert result is None

    def test_classify_component_success(self, tmp_path):
        """Test successful component classification."""
        # Mock LLM provider
        mock_provider = Mock(spec=LLMProvider)
        mock_provider.call_with_retry.return_value = LLMResponse(
            success=True,
            data={
                "category": "resistor",
                "confidence": 0.95,
                "typical_price_usd": {"low": 0.01, "typical": 0.02, "high": 0.03},
                "availability": "readily_available",
                "reasoning": "MPN pattern matches resistor"
            },
            tokens_used=100
        )

        cache = LLMCache(cache_file=tmp_path / "test_cache.db")
        service = LLMEnrichmentService(provider=mock_provider, cache=cache)

        result = service.classify_component(
            mpn="RC0603FR-0710KL",
            description="10k ohm resistor",
            reference_designator="R1"
        )

        assert result is not None
        assert result.category == ComponentCategory.RESISTOR
        assert result.confidence == 0.95
        assert result.availability == "readily_available"
        assert result.from_cache is False

    def test_classify_component_cached(self, tmp_path):
        """Test classification from cache."""
        mock_provider = Mock(spec=LLMProvider)
        cache = LLMCache(cache_file=tmp_path / "test_cache.db")

        # Pre-populate cache
        cache.set(
            "classification",
            "RC0603FR-0710KL",
            {
                "category": "resistor",
                "confidence": 0.95,
                "typical_price_usd": None,
                "availability": None,
                "package_type": None,
                "reasoning": None,
                "specifications": None
            },
            tokens_used=100,
            additional_context="10k ohm resistor|R1"
        )

        service = LLMEnrichmentService(provider=mock_provider, cache=cache)

        result = service.classify_component(
            mpn="RC0603FR-0710KL",
            description="10k ohm resistor",
            reference_designator="R1"
        )

        assert result is not None
        assert result.from_cache is True
        assert result.category == ComponentCategory.RESISTOR
        # Provider should not be called
        mock_provider.call_with_retry.assert_not_called()

    def test_check_price_reasonableness(self, tmp_path):
        """Test price reasonableness checking."""
        mock_provider = Mock(spec=LLMProvider)
        mock_provider.call_with_retry.return_value = LLMResponse(
            success=True,
            data={
                "is_reasonable": False,
                "confidence": 0.9,
                "issues": [
                    {
                        "severity": "warning",
                        "issue": "Price significantly above market",
                        "suggestion": "Verify pricing data"
                    }
                ],
                "expected_price_range": {"low": 0.01, "typical": 0.02, "high": 0.03},
                "price_variance_percentage": 150.0,
                "reasoning": "Price is 150% above typical market price"
            },
            tokens_used=120
        )

        cache = LLMCache(cache_file=tmp_path / "test_cache.db")
        service = LLMEnrichmentService(provider=mock_provider, cache=cache)

        result = service.check_price_reasonableness(
            mpn="RC0603FR-0710KL",
            description="10k ohm resistor",
            category="resistor",
            package_type="smd_medium",
            unit_cost_low=0.04,
            unit_cost_typical=0.05,
            unit_cost_high=0.06,
            quantity=100
        )

        assert result is not None
        assert result.is_reasonable is False
        assert result.confidence == 0.9
        assert len(result.issues) == 1
        assert result.price_variance_percentage == 150.0

    def test_check_obsolescence(self, tmp_path):
        """Test obsolescence detection."""
        mock_provider = Mock(spec=LLMProvider)
        mock_provider.call_with_retry.return_value = LLMResponse(
            success=True,
            data={
                "obsolescence_risk": "high",
                "lifecycle_status": "eol",
                "confidence": 0.85,
                "risk_factors": ["EOL announced", "No stock available"],
                "alternatives": [
                    {
                        "mpn": "RC0603FR-0710KP",
                        "manufacturer": "Yageo",
                        "compatibility": "drop-in",
                        "availability": "readily_available",
                        "reason": "Direct replacement from same manufacturer"
                    }
                ],
                "recommendations": ["Source alternative immediately", "Consider redesign"],
                "reasoning": "Component has been marked EOL"
            },
            tokens_used=150
        )

        cache = LLMCache(cache_file=tmp_path / "test_cache.db")
        service = LLMEnrichmentService(provider=mock_provider, cache=cache)

        result = service.check_obsolescence(
            mpn="OLD_PART_123",
            manufacturer="Legacy Corp",
            description="Old component",
            category="ic",
            quantity=100
        )

        assert result is not None
        assert result.obsolescence_risk == "high"
        assert result.lifecycle_status == "eol"
        assert len(result.alternatives) == 1
        assert len(result.risk_factors) == 2

    def test_batch_check_obsolescence(self, tmp_path):
        """Test batch obsolescence checking."""
        mock_provider = Mock(spec=LLMProvider)
        mock_provider.call_with_retry.return_value = LLMResponse(
            success=True,
            data={
                "obsolescence_risk": "low",
                "lifecycle_status": "active",
                "confidence": 0.9,
                "risk_factors": [],
                "alternatives": [],
                "recommendations": [],
                "reasoning": "Component is actively manufactured"
            },
            tokens_used=100
        )

        cache = LLMCache(cache_file=tmp_path / "test_cache.db")
        service = LLMEnrichmentService(provider=mock_provider, cache=cache)

        components = [
            {"mpn": "PART1", "manufacturer": "Mfg1", "description": "Desc1", "category": "resistor", "quantity": 10},
            {"mpn": "PART2", "manufacturer": "Mfg2", "description": "Desc2", "category": "capacitor", "quantity": 20},
        ]

        results = service.batch_check_obsolescence(components)

        assert len(results) == 2
        for result in results:
            assert result.obsolescence_risk == "low"
            assert result.lifecycle_status == "active"

    def test_create_enrichment_service_no_api_key(self):
        """Test creating service without API key."""
        service = create_enrichment_service(
            provider_name="openai",
            api_key=None,
            enabled=True
        )

        assert service.enabled is False
        assert service.provider is None

    def test_create_enrichment_service_with_config(self):
        """Test creating service with full configuration."""
        service = create_enrichment_service(
            provider_name="openai",
            api_key="test-key",
            model="gpt-4o-mini",
            enabled=True,
            temperature=0.0,
            max_tokens=500
        )

        assert service.enabled is True
        assert service.provider is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
