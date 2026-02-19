"""Farnell / element14 REST API client.

Implements the DistributorClient ABC to query the element14 Partner API for
component pricing and stock data.

API documentation:
    https://partner.element14.com/docs/Product_Search_API_REST_Description

Authentication:
    Free API key obtained from https://partner.element14.com

Regional stores:
    uk.farnell.com, de.farnell.com, fr.farnell.com, it.farnell.com,
    es.farnell.com, nl.farnell.com, be.farnell.com, pl.farnell.com, ...
"""

import logging
import time
import urllib.error
import urllib.parse
import urllib.request
import json
from typing import Any, Dict, List, Optional

from .distributor_client import DistributorClient, DistributorResult
from .models import PriceBreak

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FARNELL_API_BASE = "https://api.element14.com/catalog/products"

# Maps store hostnames to ISO region codes
STORE_REGION_MAP: Dict[str, str] = {
    "uk.farnell.com": "UK",
    "de.farnell.com": "DE",
    "fr.farnell.com": "FR",
    "it.farnell.com": "IT",
    "es.farnell.com": "ES",
    "nl.farnell.com": "NL",
    "be.farnell.com": "BE",
    "pl.farnell.com": "PL",
    "cz.farnell.com": "CZ",
    "au.element14.com": "AU",
    "sg.element14.com": "SG",
    "in.element14.com": "IN",
}

# Default currency by store
STORE_CURRENCY_MAP: Dict[str, str] = {
    "uk.farnell.com": "GBP",
    "de.farnell.com": "EUR",
    "fr.farnell.com": "EUR",
    "it.farnell.com": "EUR",
    "es.farnell.com": "EUR",
    "nl.farnell.com": "EUR",
    "be.farnell.com": "EUR",
    "pl.farnell.com": "PLN",
    "cz.farnell.com": "CZK",
    "au.element14.com": "AUD",
    "sg.element14.com": "SGD",
    "in.element14.com": "INR",
}


class FarnellClient(DistributorClient):
    """Client for the Farnell / element14 Product Search REST API.

    Usage::

        client = FarnellClient(
            api_key="your-farnell-api-key",
            store="uk.farnell.com",
        )
        result = client.lookup_mpn("LM358N")

    The client caches results in the local SQLite database for 24 hours.
    On any network or API error it logs a warning and returns ``None``
    (graceful degradation).
    """

    def __init__(
        self,
        api_key: str,
        store: str = "uk.farnell.com",
        cache: Optional[Any] = None,
        cache_ttl_seconds: int = DistributorClient.DEFAULT_CACHE_TTL_SECONDS,
        enabled: bool = True,
        timeout_seconds: int = 10,
        max_retries: int = 2,
    ) -> None:
        """Initialise the Farnell client.

        Args:
            api_key: element14 Partner API key.
            store: Regional store hostname (e.g. ``'uk.farnell.com'``).
            cache: Optional DistributorCache instance.
            cache_ttl_seconds: Cache TTL override.
            enabled: Toggle client on/off.
            timeout_seconds: HTTP request timeout.
            max_retries: Number of retry attempts on transient errors.
        """
        super().__init__(
            api_key=api_key,
            cache=cache,
            cache_ttl_seconds=cache_ttl_seconds,
            enabled=enabled,
        )
        self.store = store
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    # ------------------------------------------------------------------
    # DistributorClient interface
    # ------------------------------------------------------------------

    @property
    def distributor_name(self) -> str:
        return "Farnell"

    @property
    def distributor_region(self) -> str:
        return STORE_REGION_MAP.get(self.store, "EU")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_url(self, mpn: str) -> str:
        """Build the element14 API URL for an MPN search."""
        params = {
            "callsign": self.api_key,
            "term": f"mfr:{mpn}",
            "storeInfo.id": self.store,
            "resultsSettings.offset": "0",
            "resultsSettings.numberOfResults": "5",
            "resultsSettings.responseGroup": "large",
        }
        return f"{FARNELL_API_BASE}?{urllib.parse.urlencode(params)}"

    def _http_get(self, url: str) -> Optional[Dict[str, Any]]:
        """Perform an HTTP GET request with retries.

        Returns parsed JSON dict, or None on failure.
        """
        for attempt in range(self.max_retries + 1):
            try:
                req = urllib.request.Request(
                    url,
                    headers={"Accept": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    body = resp.read().decode("utf-8")
                    return json.loads(body)
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    # Rate limited — back off
                    wait = 2 ** attempt
                    logger.warning(
                        "Farnell rate limit hit (attempt %d/%d), waiting %ds",
                        attempt + 1,
                        self.max_retries + 1,
                        wait,
                    )
                    time.sleep(wait)
                elif exc.code in (401, 403):
                    logger.error("Farnell authentication error (%d): check API key", exc.code)
                    return None
                else:
                    logger.warning("Farnell HTTP error %d (attempt %d)", exc.code, attempt + 1)
                    if attempt >= self.max_retries:
                        return None
            except Exception as exc:
                logger.warning("Farnell request error (attempt %d): %s", attempt + 1, exc)
                if attempt >= self.max_retries:
                    return None
                time.sleep(1)
        return None

    def _parse_response(self, raw: Dict[str, Any], mpn: str) -> Optional[DistributorResult]:
        """Convert a raw Farnell API response into a DistributorResult."""
        try:
            products = (
                raw.get("keywordSearchReturn", {}).get("products", [])
                or raw.get("manufacturerPartNumberSearchReturn", {}).get("products", [])
            )

            if not products:
                logger.debug("Farnell: no products found for %s", mpn)
                return None

            # Use first (best-match) product
            product = products[0]

            # Stock
            stock_val = product.get("stock", {})
            if isinstance(stock_val, dict):
                stock_level: Optional[int] = stock_val.get("liveInventory", {}).get("value")
                if stock_level is not None:
                    try:
                        stock_level = int(stock_level)
                    except (ValueError, TypeError):
                        stock_level = None
            else:
                stock_level = None

            # Price breaks
            price_breaks: List[PriceBreak] = []
            for price_entry in product.get("prices", []):
                try:
                    qty = int(price_entry.get("from", 1))
                    unit = float(price_entry.get("cost", 0.0))
                    price_breaks.append(
                        PriceBreak(
                            quantity=qty,
                            unit_price=unit,
                            total_price=round(unit * qty, 6),
                        )
                    )
                except (ValueError, TypeError, KeyError):
                    continue

            # Sort by ascending quantity
            price_breaks.sort(key=lambda pb: pb.quantity)

            currency = STORE_CURRENCY_MAP.get(self.store, "GBP")

            # RoHS
            rohs_code = product.get("rohsStatusCode", "")
            rohs_compliant: Optional[bool] = None
            if rohs_code:
                rohs_compliant = rohs_code.upper() not in ("NOT_COMPLIANT", "UNKNOWN", "")

            return DistributorResult(
                mpn=mpn,
                distributor_sku=product.get("sku") or product.get("id"),
                manufacturer=product.get("mfrName"),
                description=product.get("displayName") or product.get("description"),
                package=product.get("packSize") or product.get("packaging"),
                distributor=self.distributor_name,
                distributor_region=self.distributor_region,
                warehouse_location=self.store,
                stock_level=stock_level,
                lead_time_days=None,  # Not directly provided by this endpoint
                currency=currency,
                price_breaks=price_breaks,
                rohs_compliant=rohs_compliant,
                lifecycle_status=product.get("lifecycleStatus"),
                datasheet_url=product.get("dataSheetUrl"),
                timestamp=time.time(),
                raw_response=raw,
            )
        except Exception as exc:
            logger.error("Farnell response parsing error for %s: %s", mpn, exc)
            return None

    # ------------------------------------------------------------------
    # Core fetch implementation
    # ------------------------------------------------------------------

    def _fetch_mpn(self, mpn: str) -> Optional[DistributorResult]:
        """Query the Farnell element14 API for a single MPN."""
        if not self.api_key:
            logger.warning("Farnell client: no API key configured, skipping lookup")
            return None

        url = self._build_url(mpn)
        logger.debug("Farnell lookup: %s -> %s", mpn, url)

        raw = self._http_get(url)
        if raw is None:
            return None

        return self._parse_response(raw, mpn)
