"""
LLM Provider abstraction layer with strategy pattern.

Supports multiple LLM providers (OpenAI, Anthropic) with a common interface
for component enrichment, price checking, and obsolescence detection.
"""

import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

import openai
from anthropic import Anthropic
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class LLMResponse(BaseModel):
    """Structured LLM response with parsed data and metadata."""

    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    raw_response: Optional[str] = None
    tokens_used: int = 0
    latency_ms: float = 0.0
    cached: bool = False


class RateLimiter:
    """Simple token bucket rate limiter for API calls."""

    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.tokens = requests_per_minute
        self.last_update = time.time()
        self.lock_time = 60.0 / requests_per_minute

    def acquire(self) -> None:
        """Block until a request token is available."""
        now = time.time()
        time_passed = now - self.last_update
        self.tokens = min(
            self.requests_per_minute,
            self.tokens + time_passed * (self.requests_per_minute / 60.0)
        )
        self.last_update = now

        if self.tokens < 1:
            sleep_time = (1 - self.tokens) * (60.0 / self.requests_per_minute)
            logger.debug(f"Rate limit reached, sleeping for {sleep_time:.2f}s")
            time.sleep(sleep_time)
            self.tokens = 1

        self.tokens -= 1


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(
        self,
        api_key: str,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        requests_per_minute: int = 60,
        max_retries: int = 3
    ):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.rate_limiter = RateLimiter(requests_per_minute)

    @abstractmethod
    def call(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = True
    ) -> LLMResponse:
        """
        Make an LLM API call.

        Args:
            prompt: User prompt
            system_prompt: System prompt (optional)
            json_mode: Whether to request JSON-formatted output

        Returns:
            LLMResponse with parsed data or error
        """
        pass

    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> Optional[str]:
        """Call the LLM and return the response as a JSON string (compatibility alias).

        Attempts JSON parsing (including stripping markdown code blocks).  On
        success returns ``json.dumps(data)``; on failure returns the raw
        response text; returns ``None`` only if no response was obtained.
        """
        response = self.call(prompt, system_prompt, json_mode=True)
        if response.success and response.data:
            return json.dumps(response.data)
        # Fallback: try with json_mode=False and return raw text
        response = self.call(prompt, system_prompt, json_mode=False)
        if response.success:
            return response.raw_response
        return None

    def call_with_retry(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = True
    ) -> LLMResponse:
        """
        Make an LLM API call with retry logic.

        Implements exponential backoff on rate limit errors and transient failures.
        """
        last_error = None

        for attempt in range(self.max_retries):
            try:
                # Apply rate limiting
                self.rate_limiter.acquire()

                # Make the API call
                start_time = time.time()
                response = self.call(prompt, system_prompt, json_mode)
                response.latency_ms = (time.time() - start_time) * 1000

                if response.success:
                    return response

                last_error = response.error

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"LLM API call failed (attempt {attempt + 1}/{self.max_retries}): {e}"
                )

            # Exponential backoff
            if attempt < self.max_retries - 1:
                sleep_time = (2 ** attempt) * 1.0  # 1s, 2s, 4s
                logger.debug(f"Retrying in {sleep_time}s...")
                time.sleep(sleep_time)

        # All retries exhausted
        return LLMResponse(
            success=False,
            error=f"Failed after {self.max_retries} retries. Last error: {last_error}"
        )

    @staticmethod
    def parse_json_response(response_text: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        Parse JSON from LLM response with robust error handling.

        Returns:
            (success, parsed_data, error_message)
        """
        try:
            # Try direct JSON parse
            data = json.loads(response_text)
            return True, data, None
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code blocks
        try:
            if "```json" in response_text:
                start = response_text.index("```json") + 7
                end = response_text.index("```", start)
                json_text = response_text[start:end].strip()
                data = json.loads(json_text)
                return True, data, None
            elif "```" in response_text:
                start = response_text.index("```") + 3
                end = response_text.index("```", start)
                json_text = response_text[start:end].strip()
                data = json.loads(json_text)
                return True, data, None
        except (ValueError, json.JSONDecodeError):
            pass

        return False, None, f"Could not parse JSON from response: {response_text[:200]}"


class OpenAIProvider(LLMProvider):
    """OpenAI API provider implementation."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", **kwargs):
        super().__init__(api_key, model, **kwargs)
        self.client = openai.OpenAI(api_key=api_key)

    def call(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = True
    ) -> LLMResponse:
        """Make an OpenAI API call."""
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            # Build request parameters
            request_params = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            }

            if json_mode:
                request_params["response_format"] = {"type": "json_object"}

            # Make API call
            response = self.client.chat.completions.create(**request_params)

            raw_response = response.choices[0].message.content
            tokens_used = response.usage.total_tokens

            # Parse JSON response
            if json_mode:
                success, data, error = self.parse_json_response(raw_response)
                if not success:
                    return LLMResponse(
                        success=False,
                        error=error,
                        raw_response=raw_response,
                        tokens_used=tokens_used
                    )
                return LLMResponse(
                    success=True,
                    data=data,
                    raw_response=raw_response,
                    tokens_used=tokens_used
                )
            else:
                return LLMResponse(
                    success=True,
                    data={"response": raw_response},
                    raw_response=raw_response,
                    tokens_used=tokens_used
                )

        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            return LLMResponse(success=False, error=str(e))


class AnthropicProvider(LLMProvider):
    """Anthropic API provider implementation."""

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022", **kwargs):
        super().__init__(api_key, model, **kwargs)
        self.client = Anthropic(api_key=api_key)

    def call(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = True
    ) -> LLMResponse:
        """Make an Anthropic API call."""
        try:
            # For JSON mode, add instruction to system prompt
            if json_mode and system_prompt:
                system_prompt += "\n\nYou must respond with valid JSON only. Do not include any text outside the JSON object."
            elif json_mode:
                system_prompt = "You must respond with valid JSON only. Do not include any text outside the JSON object."

            # Make API call
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system_prompt or "",
                messages=[{"role": "user", "content": prompt}]
            )

            raw_response = response.content[0].text
            tokens_used = response.usage.input_tokens + response.usage.output_tokens

            # Parse JSON response
            if json_mode:
                success, data, error = self.parse_json_response(raw_response)
                if not success:
                    return LLMResponse(
                        success=False,
                        error=error,
                        raw_response=raw_response,
                        tokens_used=tokens_used
                    )
                return LLMResponse(
                    success=True,
                    data=data,
                    raw_response=raw_response,
                    tokens_used=tokens_used
                )
            else:
                return LLMResponse(
                    success=True,
                    data={"response": raw_response},
                    raw_response=raw_response,
                    tokens_used=tokens_used
                )

        except Exception as e:
            logger.error(f"Anthropic API call failed: {e}")
            return LLMResponse(success=False, error=str(e))


def create_llm_provider(
    provider: str,
    api_key: str,
    model: Optional[str] = None,
    **kwargs
) -> LLMProvider:
    """
    Factory function to create LLM provider instances.

    Args:
        provider: Provider name ('openai' or 'anthropic')
        api_key: API key for the provider
        model: Model name (uses provider default if not specified)
        **kwargs: Additional provider-specific parameters

    Returns:
        LLMProvider instance

    Raises:
        ValueError: If provider is not supported
    """
    provider = provider.lower()

    if provider == "openai":
        if model is None:
            model = "gpt-4o-mini"
        return OpenAIProvider(api_key=api_key, model=model, **kwargs)

    elif provider == "anthropic":
        if model is None:
            model = "claude-3-5-sonnet-20241022"
        return AnthropicProvider(api_key=api_key, model=model, **kwargs)

    else:
        raise ValueError(
            f"Unsupported LLM provider: {provider}. "
            f"Supported providers: openai, anthropic"
        )
