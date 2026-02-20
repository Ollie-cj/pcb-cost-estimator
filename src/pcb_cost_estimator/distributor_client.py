"""Abstract base class and data models for distributor API clients.

Defines the DistributorClient ABC and DistributorResult model that all
European distributor integrations must implement.
"""

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .models import PriceBreak


class DistributorResult(BaseModel):
    """Result from a distributor API lookup.

    Contains pricing, stock, and metadata for a component from a specific distributor.
    """

    # Component identification
    mpn: str = Field(..., description="Manufacturer part number (as queried)")
    distributor_sku: Optional[str] = Field(None, description="Distributor-specific SKU/order code")
    manufacturer: Optional[str] = Field(None, description="Manufacturer name")
    description: Optional[str] = Field(None, description="Component description from distributor")
    package: Optional[str] = Field(None, description="Package type from distributor")

    # Distributor metadata
    distributor: str = Field(..., description="Distributor name (e.g., 'Farnell', 'RS Components', 'TME')")
    distributor_region: str = Field(
        ..., description="Region code for this result (e.g., 'UK', 'DE', 'PL', 'EU')"
    )
    warehouse_location: Optional[str] = Field(
        None, description="Warehouse/store location (e.g., 'uk.farnell.com', 'rs-online.com')"
    )

    # Availability
    stock_level: Optional[int] = Field(None, description="Current stock quantity", ge=0)
    lead_time_days: Optional[int] = Field(
        None, description="Lead time in days if not in stock", ge=0
    )

    # Pricing
    currency: str = Field(default="GBP", description="Currency for prices")
    price_breaks: List[PriceBreak] = Field(
        default_factory=list, description="Quantity break pricing tiers"
    )

    # Compliance / lifecycle
    rohs_compliant: Optional[bool] = Field(None, description="RoHS compliance status")
    lifecycle_status: Optional[str] = Field(
        None, description="Lifecycle status (e.g., 'Active', 'NRND', 'Obsolete')"
    )
    datasheet_url: Optional[str] = Field(None, description="URL to component datasheet")

    # Provenance
    timestamp: float = Field(default_factory=time.time, description="Unix timestamp of lookup")
    raw_response: Optional[Dict[str, Any]] = Field(
        None, description="Raw API response for debugging", exclude=True
    )

    @property
    def unit_price(self) -> Optional[float]:
        """Return unit price at quantity 1, if available."""
        if not self.price_breaks:
            return None
        return self.price_breaks[0].unit_price

    @property
    def in_stock(self) -> bool:
        """Return True if stock_level > 0."""
        return self.stock_level is not None and self.stock_level > 0


class DistributorClient(ABC):
    """Abstract base class for distributor API clients.

    All European distributor integrations must implement this interface to
    slot into the Tier 1 intelligence layer.

    Subclasses should:
    - Call `_check_cache()` before making API requests
    - Call `_store_cache()` after successful API responses
    - Handle rate limiting and auth gracefully
    - Return None (not raise) on lookup failure
    """

    # Default 24-hour TTL for distributor data
    DEFAULT_CACHE_TTL_SECONDS: int = 86400

    def __init__(
        self,
        api_key: str,
        cache: Optional[Any] = None,
        cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
        enabled: bool = True,
    ) -> None:
        """Initialise the distributor client.

        Args:
            api_key: API key / credentials for the distributor service.
            cache: Optional DistributorCache instance. If None a default
                   cache will be created on first use.
            cache_ttl_seconds: Cache TTL in seconds (default 24 h).
            enabled: Whether this client is active.
        """
        self.api_key = api_key
        self._cache = cache
        self.cache_ttl_seconds = cache_ttl_seconds
        self.enabled = enabled

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def distributor_name(self) -> str:
        """Human-readable distributor name (e.g., 'Farnell')."""

    @property
    @abstractmethod
    def distributor_region(self) -> str:
        """Primary region code for this client (e.g., 'UK')."""

    @abstractmethod
    def _fetch_mpn(self, mpn: str) -> Optional[DistributorResult]:
        """Perform the actual API request for a single MPN.

        Implementations should NOT handle caching here; caching is managed
        by the public `lookup_mpn()` method.

        Args:
            mpn: Manufacturer part number to look up.

        Returns:
            DistributorResult on success, None on failure / not found.
        """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def lookup_mpn(self, mpn: str) -> Optional[DistributorResult]:
        """Look up a single MPN, using cache when available.

        Args:
            mpn: Manufacturer part number to look up.

        Returns:
            DistributorResult or None if not found / disabled.
        """
        if not self.enabled:
            return None

        # Try cache first
        cached = self._check_cache(mpn)
        if cached is not None:
            return cached

        # Live lookup
        result = self._fetch_mpn(mpn)
        if result is not None:
            self._store_cache(mpn, result)

        return result

    def lookup_mpns(self, mpns: List[str]) -> Dict[str, Optional[DistributorResult]]:
        """Look up multiple MPNs.

        Default implementation calls lookup_mpn() in a loop. Subclasses
        that support batch endpoints should override this.

        Args:
            mpns: List of manufacturer part numbers.

        Returns:
            Dict mapping MPN -> DistributorResult (or None).
        """
        return {mpn: self.lookup_mpn(mpn) for mpn in mpns}

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    @property
    def cache(self) -> Any:
        """Lazily create and return the distributor cache."""
        if self._cache is None:
            from .distributor_cache import DistributorCache

            self._cache = DistributorCache(ttl_seconds=self.cache_ttl_seconds)
        return self._cache

    def _check_cache(self, mpn: str) -> Optional[DistributorResult]:
        """Return a cached DistributorResult or None."""
        try:
            return self.cache.get(self.distributor_name, mpn)
        except Exception:
            return None

    def _store_cache(self, mpn: str, result: DistributorResult) -> None:
        """Persist a DistributorResult to cache."""
        try:
            self.cache.set(self.distributor_name, mpn, result)
        except Exception:
            pass
