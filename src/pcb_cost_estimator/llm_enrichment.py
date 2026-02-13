"""
LLM-powered component enrichment and pricing intelligence service.

Integrates LLM provider, caching, and prompt templates to enhance
the deterministic cost model with AI-powered analysis.
"""

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .llm_cache import LLMCache, get_llm_cache
from .llm_provider import LLMProvider, LLMResponse, create_llm_provider
from .models import ComponentCategory
from .prompt_templates import PromptTemplateManager, get_template_manager

logger = logging.getLogger(__name__)


class ComponentClassificationResult(BaseModel):
    """Result from LLM-powered component classification."""

    category: ComponentCategory
    confidence: float = Field(ge=0.0, le=1.0)
    typical_price_usd: Optional[Dict[str, float]] = None
    availability: Optional[str] = None
    package_type: Optional[str] = None
    reasoning: Optional[str] = None
    specifications: Optional[Dict[str, Any]] = None
    from_cache: bool = False
    tokens_used: int = 0


class PriceReasonablenessResult(BaseModel):
    """Result from LLM-powered price reasonableness check."""

    is_reasonable: bool
    confidence: float = Field(ge=0.0, le=1.0)
    issues: List[Dict[str, str]] = Field(default_factory=list)
    expected_price_range: Optional[Dict[str, float]] = None
    price_variance_percentage: Optional[float] = None
    reasoning: Optional[str] = None
    from_cache: bool = False
    tokens_used: int = 0


class ObsolescenceRisk(BaseModel):
    """Component obsolescence risk assessment."""

    mpn: str
    manufacturer: Optional[str] = None
    obsolescence_risk: str  # none, low, medium, high, obsolete
    lifecycle_status: str  # active, nrnd, eol, obsolete, unknown
    confidence: float = Field(ge=0.0, le=1.0)
    risk_factors: List[str] = Field(default_factory=list)
    alternatives: List[Dict[str, Any]] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    reasoning: Optional[str] = None
    from_cache: bool = False
    tokens_used: int = 0


class LLMEnrichmentService:
    """
    Service for LLM-powered component enrichment.

    Provides classification, price checking, and obsolescence detection
    with caching and graceful fallback.
    """

    def __init__(
        self,
        provider: Optional[LLMProvider] = None,
        cache: Optional[LLMCache] = None,
        template_manager: Optional[PromptTemplateManager] = None,
        enabled: bool = True
    ):
        """
        Initialize the enrichment service.

        Args:
            provider: LLM provider instance (if None, service operates in degraded mode)
            cache: Cache instance (uses global cache if None)
            template_manager: Template manager (uses global if None)
            enabled: Whether enrichment is enabled
        """
        self.provider = provider
        self.cache = cache or get_llm_cache()
        self.template_manager = template_manager or get_template_manager()
        self.enabled = enabled and provider is not None

        if not self.enabled:
            logger.warning(
                "LLM enrichment service initialized in degraded mode "
                "(no provider available or disabled)"
            )

    def classify_component(
        self,
        mpn: str,
        description: str = "",
        reference_designator: str = ""
    ) -> Optional[ComponentClassificationResult]:
        """
        Classify an ambiguous component using LLM.

        Args:
            mpn: Manufacturer part number
            description: Component description
            reference_designator: Reference designator (e.g., R1, C2, U1)

        Returns:
            ComponentClassificationResult if successful, None otherwise
        """
        if not self.enabled:
            logger.debug("LLM enrichment disabled, skipping classification")
            return None

        # Check cache first
        cache_key_context = f"{description}|{reference_designator}"
        cached = self.cache.get("classification", mpn, cache_key_context)
        if cached:
            try:
                result = ComponentClassificationResult(**cached)
                result.from_cache = True
                logger.debug(f"Using cached classification for {mpn}")
                return result
            except Exception as e:
                logger.warning(f"Failed to parse cached classification: {e}")

        # Render prompt template
        prompts = self.template_manager.render_template(
            "component_classification",
            {
                "mpn": mpn or "Unknown",
                "description": description or "No description",
                "reference_designator": reference_designator or "Unknown"
            }
        )

        if not prompts:
            logger.error("Failed to render component classification template")
            return None

        system_prompt, user_prompt = prompts

        # Call LLM with retry
        response = self.provider.call_with_retry(
            user_prompt,
            system_prompt=system_prompt,
            json_mode=True
        )

        if not response.success or not response.data:
            logger.error(
                f"LLM classification failed for {mpn}: {response.error}"
            )
            return None

        # Parse response
        try:
            # Map string category to enum
            category_str = response.data.get("category", "unknown").lower()
            category = self._parse_category(category_str)

            result = ComponentClassificationResult(
                category=category,
                confidence=response.data.get("confidence", 0.0),
                typical_price_usd=response.data.get("typical_price_usd"),
                availability=response.data.get("availability"),
                package_type=response.data.get("package_type"),
                reasoning=response.data.get("reasoning"),
                specifications=response.data.get("specifications"),
                tokens_used=response.tokens_used
            )

            # Cache the result
            self.cache.set(
                "classification",
                mpn,
                result.model_dump(exclude={"from_cache", "tokens_used"}),
                tokens_used=response.tokens_used,
                additional_context=cache_key_context
            )

            logger.info(
                f"Classified {mpn} as {category.value} "
                f"(confidence: {result.confidence:.2f})"
            )

            return result

        except Exception as e:
            logger.error(f"Failed to parse classification response: {e}")
            return None

    def check_price_reasonableness(
        self,
        mpn: str,
        description: str,
        category: str,
        package_type: str,
        unit_cost_low: float,
        unit_cost_typical: float,
        unit_cost_high: float,
        quantity: int
    ) -> Optional[PriceReasonablenessResult]:
        """
        Check if a component price estimate is reasonable.

        Args:
            mpn: Manufacturer part number
            description: Component description
            category: Component category
            package_type: Package type
            unit_cost_low: Low unit cost estimate
            unit_cost_typical: Typical unit cost estimate
            unit_cost_high: High unit cost estimate
            quantity: Quantity

        Returns:
            PriceReasonablenessResult if successful, None otherwise
        """
        if not self.enabled:
            logger.debug("LLM enrichment disabled, skipping price check")
            return None

        # Check cache
        cache_key_context = (
            f"{category}|{package_type}|"
            f"{unit_cost_typical:.4f}|{quantity}"
        )
        cached = self.cache.get("price_check", mpn, cache_key_context)
        if cached:
            try:
                result = PriceReasonablenessResult(**cached)
                result.from_cache = True
                logger.debug(f"Using cached price check for {mpn}")
                return result
            except Exception as e:
                logger.warning(f"Failed to parse cached price check: {e}")

        # Render prompt template
        prompts = self.template_manager.render_template(
            "price_reasonableness",
            {
                "mpn": mpn or "Unknown",
                "description": description or "No description",
                "category": category,
                "package_type": package_type,
                "unit_cost_low": unit_cost_low,
                "unit_cost_typical": unit_cost_typical,
                "unit_cost_high": unit_cost_high,
                "quantity": quantity
            }
        )

        if not prompts:
            logger.error("Failed to render price reasonableness template")
            return None

        system_prompt, user_prompt = prompts

        # Call LLM with retry
        response = self.provider.call_with_retry(
            user_prompt,
            system_prompt=system_prompt,
            json_mode=True
        )

        if not response.success or not response.data:
            logger.warning(
                f"LLM price check failed for {mpn}: {response.error}"
            )
            return None

        # Parse response
        try:
            result = PriceReasonablenessResult(
                is_reasonable=response.data.get("is_reasonable", True),
                confidence=response.data.get("confidence", 0.0),
                issues=response.data.get("issues", []),
                expected_price_range=response.data.get("expected_price_range"),
                price_variance_percentage=response.data.get("price_variance_percentage"),
                reasoning=response.data.get("reasoning"),
                tokens_used=response.tokens_used
            )

            # Cache the result
            self.cache.set(
                "price_check",
                mpn,
                result.model_dump(exclude={"from_cache", "tokens_used"}),
                tokens_used=response.tokens_used,
                additional_context=cache_key_context
            )

            if not result.is_reasonable:
                logger.warning(
                    f"Price check flagged {mpn}: {result.reasoning}"
                )

            return result

        except Exception as e:
            logger.error(f"Failed to parse price check response: {e}")
            return None

    def check_obsolescence(
        self,
        mpn: str,
        manufacturer: str = "",
        description: str = "",
        category: str = "",
        quantity: int = 1
    ) -> Optional[ObsolescenceRisk]:
        """
        Check component obsolescence risk.

        Args:
            mpn: Manufacturer part number
            manufacturer: Manufacturer name
            description: Component description
            category: Component category
            quantity: Quantity required

        Returns:
            ObsolescenceRisk if successful, None otherwise
        """
        if not self.enabled:
            logger.debug("LLM enrichment disabled, skipping obsolescence check")
            return None

        # Check cache
        cache_key_context = f"{manufacturer}|{category}"
        cached = self.cache.get("obsolescence", mpn, cache_key_context)
        if cached:
            try:
                result = ObsolescenceRisk(**cached, mpn=mpn, manufacturer=manufacturer)
                result.from_cache = True
                logger.debug(f"Using cached obsolescence check for {mpn}")
                return result
            except Exception as e:
                logger.warning(f"Failed to parse cached obsolescence check: {e}")

        # Render prompt template
        prompts = self.template_manager.render_template(
            "obsolescence_detection",
            {
                "mpn": mpn or "Unknown",
                "manufacturer": manufacturer or "Unknown",
                "description": description or "No description",
                "category": category or "unknown",
                "quantity": quantity
            }
        )

        if not prompts:
            logger.error("Failed to render obsolescence detection template")
            return None

        system_prompt, user_prompt = prompts

        # Call LLM with retry
        response = self.provider.call_with_retry(
            user_prompt,
            system_prompt=system_prompt,
            json_mode=True
        )

        if not response.success or not response.data:
            logger.warning(
                f"LLM obsolescence check failed for {mpn}: {response.error}"
            )
            return None

        # Parse response
        try:
            result = ObsolescenceRisk(
                mpn=mpn,
                manufacturer=manufacturer,
                obsolescence_risk=response.data.get("obsolescence_risk", "unknown"),
                lifecycle_status=response.data.get("lifecycle_status", "unknown"),
                confidence=response.data.get("confidence", 0.0),
                risk_factors=response.data.get("risk_factors", []),
                alternatives=response.data.get("alternatives", []),
                recommendations=response.data.get("recommendations", []),
                reasoning=response.data.get("reasoning"),
                tokens_used=response.tokens_used
            )

            # Cache the result
            self.cache.set(
                "obsolescence",
                mpn,
                result.model_dump(exclude={"from_cache", "tokens_used", "mpn", "manufacturer"}),
                tokens_used=response.tokens_used,
                additional_context=cache_key_context
            )

            if result.obsolescence_risk in ["high", "obsolete"]:
                logger.warning(
                    f"Obsolescence risk detected for {mpn}: {result.obsolescence_risk}"
                )

            return result

        except Exception as e:
            logger.error(f"Failed to parse obsolescence response: {e}")
            return None

    def batch_check_obsolescence(
        self,
        components: List[Dict[str, Any]]
    ) -> List[ObsolescenceRisk]:
        """
        Check obsolescence for multiple components.

        Args:
            components: List of component dictionaries with keys:
                       mpn, manufacturer, description, category, quantity

        Returns:
            List of ObsolescenceRisk results
        """
        results = []

        for component in components:
            result = self.check_obsolescence(
                mpn=component.get("mpn", ""),
                manufacturer=component.get("manufacturer", ""),
                description=component.get("description", ""),
                category=component.get("category", ""),
                quantity=component.get("quantity", 1)
            )

            if result:
                results.append(result)

        return results

    @staticmethod
    def _parse_category(category_str: str) -> ComponentCategory:
        """Parse category string to ComponentCategory enum."""
        category_map = {
            "resistor": ComponentCategory.RESISTOR,
            "capacitor": ComponentCategory.CAPACITOR,
            "inductor": ComponentCategory.INDUCTOR,
            "ic": ComponentCategory.IC,
            "connector": ComponentCategory.CONNECTOR,
            "diode": ComponentCategory.DIODE,
            "transistor": ComponentCategory.TRANSISTOR,
            "led": ComponentCategory.LED,
            "crystal": ComponentCategory.CRYSTAL,
            "oscillator": ComponentCategory.CRYSTAL,
            "switch": ComponentCategory.SWITCH,
            "relay": ComponentCategory.RELAY,
            "fuse": ComponentCategory.FUSE,
            "transformer": ComponentCategory.TRANSFORMER,
            "sensor": ComponentCategory.SENSOR,
            "other": ComponentCategory.OTHER,
            "unknown": ComponentCategory.UNKNOWN,
        }

        return category_map.get(category_str.lower(), ComponentCategory.UNKNOWN)


def create_enrichment_service(
    provider_name: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    enabled: bool = True,
    **kwargs
) -> LLMEnrichmentService:
    """
    Factory function to create an enrichment service.

    Args:
        provider_name: LLM provider ('openai' or 'anthropic')
        api_key: API key for the provider
        model: Model name
        enabled: Whether enrichment is enabled
        **kwargs: Additional provider parameters

    Returns:
        LLMEnrichmentService instance
    """
    provider = None

    if enabled and provider_name and api_key:
        try:
            provider = create_llm_provider(
                provider=provider_name,
                api_key=api_key,
                model=model,
                **kwargs
            )
            logger.info(
                f"Created LLM enrichment service with {provider_name} provider"
            )
        except Exception as e:
            logger.error(f"Failed to create LLM provider: {e}")
            logger.warning("LLM enrichment will operate in degraded mode")

    return LLMEnrichmentService(provider=provider, enabled=enabled)
