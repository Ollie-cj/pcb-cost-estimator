"""RS Components REST API client.

Implements the DistributorClient ABC to query the RS Components / Allied
Electronics product search API for component pricing and stock data.

API documentation:
    https://docs.rs-online.com/

Authentication:
    API key obtained from RS Online developer portal.  The key is sent as
    an ``Authorization`` header: ``Bearer <api_key>``.

Regional coverage:
    UK (rs-online.com), DE, FR, IT, ES, NL, BE, PL, US (alliedelec.com), …
"""

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from .distributor_client import DistributorClient, DistributorResult
from .models import PriceBreak

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RS_API_BASE = "https://api.rs-online.com/products/v1"

# Locale / region mapping
LOCALE_REGION_MAP: Dict[str, str] = {
    "en": "UK",
    "de": "DE",
    "fr": "FR",
    "it": "IT",
    "es": "ES",
    "nl": "NL",
    "be": "BE",
    "pl": "PL",
    "us": "US",
}

LOCALE_CURRENCY_MAP: Dict[str, str] = {
    "en": "GBP",
    "de": "EUR",
    "fr": "EUR",
    "it": "EUR",
    "es": "EUR",
    "nl": "EUR",
    "be": "EUR",
    "pl": "PLN",
    "us": "USD",
}

LOCALE_STORE_MAP: Dict[str, str] = {
    "en": "rs-online.com",
    "de": "de.rs-online.com",
    "fr": "fr.rs-online.com",
    "it": "it.rs-online.com",
    "es": "es.rs-online.com",
    "nl": "nl.rs-online.com",
    "be": "be.rs-online.com",
    "pl": "pl.rs-online.com",
    "us": "uk.rs-online.com",
}


class RSComponentsClient(DistributorClient):
    """Client for the RS Components / Allied Electronics product search API.

    Usage::

        client = RSComponentsClient(
            api_key="your-rs-api-key",
            locale="en",   # 'en' = UK
        )
        result = client.lookup_mpn("NE555P")

    The client caches results for 24 hours and degrades gracefully on
    network / auth failures.
    """

    def __init__(
        self,
        api_key: str,
        locale: str = "en",
        cache: Optional[Any] = None,
        cache_ttl_seconds: int = DistributorClient.DEFAULT_CACHE_TTL_SECONDS,
        enabled: bool = True,
        timeout_seconds: int = 10,
        max_retries: int = 2,
    ) -> None:
        """Initialise the RS Components client.

        Args:
            api_key: RS Online API key.
            locale: Locale / region code (``'en'`` for UK, ``'de'`` for Germany, …).
            cache: Optional DistributorCache instance.
            cache_ttl_seconds: Cache TTL override (default 24 h).
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
        self.locale = locale.lower()
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    # ------------------------------------------------------------------
    # DistributorClient interface
    # ------------------------------------------------------------------

    @property
    def distributor_name(self) -> str:
        return "RS Components"

    @property
    def distributor_region(self) -> str:
        return LOCALE_REGION_MAP.get(self.locale, "EU")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_search_url(self, mpn: str) -> str:
        """Build RS Components search URL for a manufacturer part number."""
        params = {
            "query": mpn,
            "pricingFamilyCode": self.locale,
            "pageSize": "5",
            "pageNumber": "1",
        }
        return f"{RS_API_BASE}/search?{urllib.parse.urlencode(params)}"

    def _build_headers(self) -> Dict[str, str]:
        """Return HTTP request headers including auth."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _http_get(self, url: str) -> Optional[Dict[str, Any]]:
        """Perform an HTTP GET with retry logic.

        Returns parsed JSON dict, or None on failure.
        """
        headers = self._build_headers()
        for attempt in range(self.max_retries + 1):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    body = resp.read().decode("utf-8")
                    return json.loads(body)
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    wait = 2 ** attempt
                    logger.warning(
                        "RS Components rate limit (attempt %d/%d), waiting %ds",
                        attempt + 1,
                        self.max_retries + 1,
                        wait,
                    )
                    time.sleep(wait)
                elif exc.code in (401, 403):
                    logger.error(
                        "RS Components authentication error (%d): check API key", exc.code
                    )
                    return None
                else:
                    logger.warning(
                        "RS Components HTTP error %d (attempt %d)", exc.code, attempt + 1
                    )
                    if attempt >= self.max_retries:
                        return None
            except Exception as exc:
                logger.warning(
                    "RS Components request error (attempt %d): %s", attempt + 1, exc
                )
                if attempt >= self.max_retries:
                    return None
                time.sleep(1)
        return None

    def _parse_price_breaks(self, product: Dict[str, Any]) -> List[PriceBreak]:
        """Extract quantity-break pricing from a product dict."""
        price_breaks: List[PriceBreak] = []

        # RS API returns priceBreaks list or a flat unitPrice
        for pb in product.get("priceBreaks", []):
            try:
                qty = int(pb.get("quantity", 1))
                unit = float(pb.get("unitPrice", 0.0))
                price_breaks.append(
                    PriceBreak(quantity=qty, unit_price=unit, total_price=round(unit * qty, 6))
                )
            except (ValueError, TypeError, KeyError):
                continue

        # Fallback: single unit price
        if not price_breaks:
            unit_price = product.get("unitPrice") or product.get("price")
            if unit_price is not None:
                try:
                    unit = float(unit_price)
                    price_breaks.append(
                        PriceBreak(quantity=1, unit_price=unit, total_price=unit)
                    )
                except (ValueError, TypeError):
                    pass

        price_breaks.sort(key=lambda pb: pb.quantity)
        return price_breaks

    def _parse_response(self, raw: Dict[str, Any], mpn: str) -> Optional[DistributorResult]:
        """Convert a raw RS API response into a DistributorResult."""
        try:
            products = (
                raw.get("products", [])
                or raw.get("searchResults", {}).get("products", [])
            )

            if not products:
                logger.debug("RS Components: no products found for %s", mpn)
                return None

            product = products[0]

            # Stock
            stock_level: Optional[int] = None
            stock_info = product.get("stock", {})
            if isinstance(stock_info, dict):
                stock_level = stock_info.get("quantity")
            elif isinstance(stock_info, (int, float)):
                stock_level = int(stock_info)

            if stock_level is not None:
                try:
                    stock_level = int(stock_level)
                except (ValueError, TypeError):
                    stock_level = None

            # Lead time
            lead_time: Optional[int] = None
            lt_raw = product.get("leadTime") or product.get("leadTimeDays")
            if lt_raw is not None:
                try:
                    lead_time = int(lt_raw)
                except (ValueError, TypeError):
                    pass

            price_breaks = self._parse_price_breaks(product)
            currency = LOCALE_CURRENCY_MAP.get(self.locale, "GBP")
            warehouse = LOCALE_STORE_MAP.get(self.locale, "rs-online.com")

            # RoHS
            rohs_compliant: Optional[bool] = None
            rohs_raw = product.get("rohsCompliance") or product.get("rohsStatus")
            if rohs_raw is not None:
                if isinstance(rohs_raw, bool):
                    rohs_compliant = rohs_raw
                elif isinstance(rohs_raw, str):
                    rohs_compliant = rohs_raw.lower() in ("compliant", "yes", "true", "rohs")

            return DistributorResult(
                mpn=mpn,
                distributor_sku=product.get("id") or product.get("stockCode"),
                manufacturer=product.get("manufacturer", {}).get("name")
                if isinstance(product.get("manufacturer"), dict)
                else product.get("manufacturer"),
                description=product.get("description") or product.get("displayName"),
                package=product.get("packageType") or product.get("package"),
                distributor=self.distributor_name,
                distributor_region=self.distributor_region,
                warehouse_location=warehouse,
                stock_level=stock_level,
                lead_time_days=lead_time,
                currency=currency,
                price_breaks=price_breaks,
                rohs_compliant=rohs_compliant,
                lifecycle_status=product.get("lifecycle") or product.get("lifecycleStatus"),
                datasheet_url=product.get("datasheetUrl") or product.get("datasheet"),
                timestamp=time.time(),
                raw_response=raw,
            )
        except Exception as exc:
            logger.error("RS Components response parsing error for %s: %s", mpn, exc)
            return None

    # ------------------------------------------------------------------
    # Core fetch implementation
    # ------------------------------------------------------------------

    def _fetch_mpn(self, mpn: str) -> Optional[DistributorResult]:
        """Query the RS Components API for a single MPN."""
        if not self.api_key:
            logger.warning("RS Components client: no API key configured, skipping lookup")
            return None

        url = self._build_search_url(mpn)
        logger.debug("RS Components lookup: %s -> %s", mpn, url)

        raw = self._http_get(url)
        if raw is None:
            return None

        return self._parse_response(raw, mpn)
