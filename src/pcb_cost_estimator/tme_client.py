"""TME (Transfer Multisort Elektronik) REST API client.

Implements the DistributorClient ABC to query TME's API for component
pricing and stock data.

API documentation:
    https://developers.tme.eu/

Authentication:
    HMAC-SHA1 signed requests.  Each request must include:
      - ``Token`` (API key / app key)
      - ``ApiSignature`` (HMAC-SHA1 of the canonicalised request)

    The signature algorithm:
      1. Collect all POST parameters (including ``Token``).
      2. URL-encode the full endpoint URL.
      3. Build: ``POST&<encoded_url>&<encoded_sorted_params>``
      4. Sign with HMAC-SHA1 using the API secret.
      5. Base64-encode the signature and append as ``ApiSignature``.

Coverage:
    TME is headquartered in Poland and has strong Eastern European coverage.
    All prices are in EUR by default.
"""

import base64
import hashlib
import hmac
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from .distributor_client import DistributorClient, DistributorResult
from .models import PriceBreak

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TME_API_BASE = "https://api.tme.eu"

TME_ENDPOINTS = {
    "search": "/Products/Search",
    "prices": "/Products/GetPrices",
    "stocks": "/Products/GetStocks",
}


class TMEClient(DistributorClient):
    """Client for the TME (Transfer Multisort Elektronik) REST API.

    Usage::

        client = TMEClient(
            api_key="your-tme-app-token",
            api_secret="your-tme-api-secret",
        )
        result = client.lookup_mpn("ATmega328P-AU")

    The client caches results for 24 hours and degrades gracefully on
    network / auth failures.

    Note on API design:
        TME's API splits product search, pricing, and stock into separate
        endpoints.  This client calls Search → GetPrices + GetStocks and
        merges the results into a single DistributorResult.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str = "",
        country: str = "PL",
        currency: str = "EUR",
        language: str = "EN",
        cache: Optional[Any] = None,
        cache_ttl_seconds: int = DistributorClient.DEFAULT_CACHE_TTL_SECONDS,
        enabled: bool = True,
        timeout_seconds: int = 15,
        max_retries: int = 2,
    ) -> None:
        """Initialise the TME client.

        Args:
            api_key: TME App token / API key.
            api_secret: TME API secret for HMAC signing.
            country: ISO country code for pricing context (default ``'PL'``).
            currency: ISO currency code (default ``'EUR'``).
            language: API response language (default ``'EN'``).
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
        self.api_secret = api_secret
        self.country = country.upper()
        self.currency = currency.upper()
        self.language = language.upper()
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    # ------------------------------------------------------------------
    # DistributorClient interface
    # ------------------------------------------------------------------

    @property
    def distributor_name(self) -> str:
        return "TME"

    @property
    def distributor_region(self) -> str:
        return self.country  # e.g. "PL", "DE", etc.

    # ------------------------------------------------------------------
    # HMAC-SHA1 signature helpers
    # ------------------------------------------------------------------

    def _sign_request(
        self,
        endpoint_url: str,
        params: Dict[str, str],
    ) -> Dict[str, str]:
        """Add HMAC-SHA1 signature to params and return updated dict.

        TME signing algorithm:
          1. Add Token to params.
          2. URL-encode all params and sort alphabetically.
          3. Build: ``POST&<url_encoded_endpoint>&<url_encoded_sorted_params>``
          4. Sign with HMAC-SHA1 using api_secret.
          5. Base64-encode and add as ApiSignature.

        Args:
            endpoint_url: Full endpoint URL (no query string).
            params: Request parameters (will be mutated).

        Returns:
            Updated params dict with ApiSignature added.
        """
        params = dict(params)
        params["Token"] = self.api_key

        # Sort alphabetically and URL-encode
        sorted_pairs = sorted(params.items())
        encoded_params = urllib.parse.urlencode(sorted_pairs)

        # Build string to sign
        encoded_url = urllib.parse.quote(endpoint_url, safe="")
        encoded_qs = urllib.parse.quote(encoded_params, safe="")
        string_to_sign = f"POST&{encoded_url}&{encoded_qs}"

        # HMAC-SHA1
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha1,
        ).digest()
        params["ApiSignature"] = base64.b64encode(signature).decode("utf-8")

        return params

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _post(self, endpoint: str, params: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """POST to a TME endpoint with HMAC signing and retry logic.

        Args:
            endpoint: Endpoint path (e.g. ``'/Products/Search'``).
            params: POST parameters (Token and ApiSignature will be added).

        Returns:
            Parsed JSON response, or None on failure.
        """
        url = f"{TME_API_BASE}{endpoint}.json"
        signed_params = self._sign_request(url, params)
        body = urllib.parse.urlencode(signed_params).encode("utf-8")

        for attempt in range(self.max_retries + 1):
            try:
                req = urllib.request.Request(
                    url,
                    data=body,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept": "application/json",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    wait = 2 ** attempt
                    logger.warning(
                        "TME rate limit (attempt %d/%d), waiting %ds",
                        attempt + 1,
                        self.max_retries + 1,
                        wait,
                    )
                    time.sleep(wait)
                elif exc.code in (400, 401, 403):
                    # Read body for TME error detail
                    try:
                        err_body = exc.read().decode("utf-8")
                        err_data = json.loads(err_body)
                        logger.error(
                            "TME API error (%d): %s",
                            exc.code,
                            err_data.get("Status") or err_body,
                        )
                    except Exception:
                        logger.error("TME API error (%d)", exc.code)
                    return None
                else:
                    logger.warning("TME HTTP error %d (attempt %d)", exc.code, attempt + 1)
                    if attempt >= self.max_retries:
                        return None
            except Exception as exc:
                logger.warning("TME request error (attempt %d): %s", attempt + 1, exc)
                if attempt >= self.max_retries:
                    return None
                time.sleep(1)
        return None

    # ------------------------------------------------------------------
    # API operation helpers
    # ------------------------------------------------------------------

    def _search_product(self, mpn: str) -> Optional[str]:
        """Search for a product and return the TME symbol (product code).

        Returns:
            TME product symbol or None if not found.
        """
        params = {
            "Country": self.country,
            "Language": self.language,
            "SearchPlain": mpn,
            "SearchCategory": "",
            "SearchWithStock": "false",
        }
        resp = self._post(TME_ENDPOINTS["search"], params)
        if resp is None:
            return None

        try:
            if resp.get("Status") != "OK":
                logger.debug(
                    "TME search returned status '%s' for %s",
                    resp.get("Status"),
                    mpn,
                )
                return None

            products = resp.get("Data", {}).get("ProductList", [])
            if not products:
                return None

            # Prefer exact MPN match
            mpn_upper = mpn.upper()
            for p in products:
                if p.get("Symbol", "").upper() == mpn_upper or (
                    p.get("OriginalSymbol", "").upper() == mpn_upper
                ):
                    return str(p["Symbol"])

            # Fallback to first result
            return str(products[0]["Symbol"])

        except Exception as exc:
            logger.error("TME search parse error for %s: %s", mpn, exc)
            return None

    def _get_prices(self, symbol: str) -> Tuple[List[PriceBreak], str]:
        """Fetch price breaks for a TME symbol.

        Returns:
            Tuple of (price_breaks, currency).
        """
        params = {
            "Country": self.country,
            "Currency": self.currency,
            "Language": self.language,
            "SymbolList[0]": symbol,
        }
        resp = self._post(TME_ENDPOINTS["prices"], params)
        price_breaks: List[PriceBreak] = []
        currency = self.currency

        if resp is None or resp.get("Status") != "OK":
            return price_breaks, currency

        try:
            product_list = resp.get("Data", {}).get("ProductList", [])
            if not product_list:
                return price_breaks, currency

            prod = product_list[0]
            currency = prod.get("Currency", self.currency)

            for pb_raw in prod.get("PriceList", []):
                try:
                    qty = int(pb_raw.get("Amount", 1))
                    unit = float(pb_raw.get("PriceValue", 0.0))
                    price_breaks.append(
                        PriceBreak(
                            quantity=qty,
                            unit_price=unit,
                            total_price=round(unit * qty, 6),
                        )
                    )
                except (ValueError, TypeError, KeyError):
                    continue

            price_breaks.sort(key=lambda p: p.quantity)
        except Exception as exc:
            logger.error("TME prices parse error for %s: %s", symbol, exc)

        return price_breaks, currency

    def _get_stock(self, symbol: str) -> Optional[int]:
        """Fetch stock level for a TME symbol."""
        params = {
            "Country": self.country,
            "Language": self.language,
            "SymbolList[0]": symbol,
        }
        resp = self._post(TME_ENDPOINTS["stocks"], params)

        if resp is None or resp.get("Status") != "OK":
            return None

        try:
            product_list = resp.get("Data", {}).get("ProductList", [])
            if not product_list:
                return None
            stock_raw = product_list[0].get("Amount")
            return int(stock_raw) if stock_raw is not None else None
        except Exception as exc:
            logger.error("TME stock parse error for %s: %s", symbol, exc)
            return None

    # ------------------------------------------------------------------
    # Core fetch implementation
    # ------------------------------------------------------------------

    def _fetch_mpn(self, mpn: str) -> Optional[DistributorResult]:
        """Query TME for a single MPN (search + prices + stock)."""
        if not self.api_key:
            logger.warning("TME client: no API key configured, skipping lookup")
            return None

        logger.debug("TME lookup: %s", mpn)

        # Step 1: search for the product symbol
        symbol = self._search_product(mpn)
        if symbol is None:
            logger.debug("TME: product not found for %s", mpn)
            return None

        # Step 2: prices and stock (parallel is ideal, but keep it simple)
        price_breaks, currency = self._get_prices(symbol)
        stock_level = self._get_stock(symbol)

        return DistributorResult(
            mpn=mpn,
            distributor_sku=symbol,
            manufacturer=None,  # Not returned by stock/price endpoints
            description=None,
            package=None,
            distributor=self.distributor_name,
            distributor_region=self.distributor_region,
            warehouse_location="tme.eu",
            stock_level=stock_level,
            lead_time_days=None,
            currency=currency,
            price_breaks=price_breaks,
            rohs_compliant=None,
            lifecycle_status=None,
            datasheet_url=None,
            timestamp=time.time(),
        )
