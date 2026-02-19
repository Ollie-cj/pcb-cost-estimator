"""Tests for European distributor API clients.

Covers:
- DistributorClient ABC / DistributorResult model
- DistributorCache (SQLite caching layer)
- FarnellClient — with mocked HTTP responses
- RSComponentsClient — with mocked HTTP responses
- TMEClient — with mocked HTTP responses (search + prices + stocks)
- Config integration for distributors section
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from pcb_cost_estimator.distributor_cache import DistributorCache
from pcb_cost_estimator.distributor_client import DistributorClient, DistributorResult
from pcb_cost_estimator.farnell_client import FarnellClient
from pcb_cost_estimator.models import PriceBreak
from pcb_cost_estimator.rs_components_client import RSComponentsClient
from pcb_cost_estimator.tme_client import TMEClient

# ---------------------------------------------------------------------------
# Helpers & fixtures
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "api_responses"


def load_fixture(filename: str) -> Dict[str, Any]:
    """Load a JSON fixture file."""
    return json.loads((FIXTURES_DIR / filename).read_text())


@pytest.fixture
def tmp_cache(tmp_path: Path) -> DistributorCache:
    """Return a fresh DistributorCache backed by a temp file."""
    return DistributorCache(cache_file=tmp_path / "test_dist_cache.db", ttl_seconds=3600)


@pytest.fixture
def farnell_client(tmp_cache: DistributorCache) -> FarnellClient:
    return FarnellClient(api_key="test-farnell-key", store="uk.farnell.com", cache=tmp_cache)


@pytest.fixture
def rs_client(tmp_cache: DistributorCache) -> RSComponentsClient:
    return RSComponentsClient(api_key="test-rs-key", locale="en", cache=tmp_cache)


@pytest.fixture
def tme_client(tmp_cache: DistributorCache) -> TMEClient:
    return TMEClient(
        api_key="test-tme-key",
        api_secret="test-tme-secret",
        country="PL",
        currency="EUR",
        cache=tmp_cache,
    )


# ===========================================================================
# DistributorResult model tests
# ===========================================================================


class TestDistributorResult:
    @pytest.mark.unit
    def test_basic_creation(self) -> None:
        result = DistributorResult(
            mpn="LM358N",
            distributor="Farnell",
            distributor_region="UK",
            currency="GBP",
        )
        assert result.mpn == "LM358N"
        assert result.distributor == "Farnell"
        assert result.distributor_region == "UK"
        assert result.currency == "GBP"

    @pytest.mark.unit
    def test_unit_price_from_price_breaks(self) -> None:
        pb1 = PriceBreak(quantity=1, unit_price=1.50, total_price=1.50)
        pb10 = PriceBreak(quantity=10, unit_price=1.20, total_price=12.0)
        result = DistributorResult(
            mpn="TEST",
            distributor="Test",
            distributor_region="UK",
            currency="GBP",
            price_breaks=[pb1, pb10],
        )
        assert result.unit_price == pytest.approx(1.50)

    @pytest.mark.unit
    def test_unit_price_no_breaks(self) -> None:
        result = DistributorResult(
            mpn="TEST",
            distributor="Test",
            distributor_region="UK",
            currency="GBP",
        )
        assert result.unit_price is None

    @pytest.mark.unit
    def test_in_stock_true(self) -> None:
        result = DistributorResult(
            mpn="TEST",
            distributor="Test",
            distributor_region="UK",
            currency="GBP",
            stock_level=100,
        )
        assert result.in_stock is True

    @pytest.mark.unit
    def test_in_stock_zero(self) -> None:
        result = DistributorResult(
            mpn="TEST",
            distributor="Test",
            distributor_region="UK",
            currency="GBP",
            stock_level=0,
        )
        assert result.in_stock is False

    @pytest.mark.unit
    def test_in_stock_none(self) -> None:
        result = DistributorResult(
            mpn="TEST",
            distributor="Test",
            distributor_region="UK",
            currency="GBP",
            stock_level=None,
        )
        assert result.in_stock is False

    @pytest.mark.unit
    def test_all_optional_fields(self) -> None:
        result = DistributorResult(
            mpn="TEST",
            distributor="Test",
            distributor_region="UK",
            currency="GBP",
            distributor_sku="123-456",
            manufacturer="ACME",
            description="Test component",
            package="DIP-8",
            warehouse_location="uk.farnell.com",
            stock_level=50,
            lead_time_days=5,
            rohs_compliant=True,
            lifecycle_status="Active",
            datasheet_url="https://example.com/ds.pdf",
        )
        assert result.distributor_sku == "123-456"
        assert result.manufacturer == "ACME"
        assert result.rohs_compliant is True


# ===========================================================================
# DistributorCache tests
# ===========================================================================


class TestDistributorCache:
    @pytest.mark.unit
    def test_cache_miss(self, tmp_cache: DistributorCache) -> None:
        assert tmp_cache.get("Farnell", "NONEXISTENT") is None

    @pytest.mark.unit
    def test_cache_set_and_get(self, tmp_cache: DistributorCache) -> None:
        result = DistributorResult(
            mpn="LM358N",
            distributor="Farnell",
            distributor_region="UK",
            currency="GBP",
            stock_level=100,
        )
        assert tmp_cache.set("Farnell", "LM358N", result) is True

        retrieved = tmp_cache.get("Farnell", "LM358N")
        assert retrieved is not None
        assert retrieved.mpn == "LM358N"
        assert retrieved.stock_level == 100
        assert retrieved.distributor == "Farnell"

    @pytest.mark.unit
    def test_cache_ttl_expiry(self, tmp_path: Path) -> None:
        cache = DistributorCache(
            cache_file=tmp_path / "ttl_test.db",
            ttl_seconds=1,  # 1-second TTL
        )
        result = DistributorResult(
            mpn="EXPIRING",
            distributor="Test",
            distributor_region="EU",
            currency="EUR",
        )
        cache.set("Test", "EXPIRING", result)
        time.sleep(1.1)  # Wait for TTL to expire
        assert cache.get("Test", "EXPIRING") is None

    @pytest.mark.unit
    def test_cache_clear_all(self, tmp_cache: DistributorCache) -> None:
        r1 = DistributorResult(mpn="A", distributor="Farnell", distributor_region="UK", currency="GBP")
        r2 = DistributorResult(mpn="B", distributor="TME", distributor_region="PL", currency="EUR")
        tmp_cache.set("Farnell", "A", r1)
        tmp_cache.set("TME", "B", r2)
        assert tmp_cache.clear() == 2
        assert tmp_cache.get("Farnell", "A") is None

    @pytest.mark.unit
    def test_cache_clear_by_distributor(self, tmp_cache: DistributorCache) -> None:
        r1 = DistributorResult(mpn="A", distributor="Farnell", distributor_region="UK", currency="GBP")
        r2 = DistributorResult(mpn="B", distributor="TME", distributor_region="PL", currency="EUR")
        tmp_cache.set("Farnell", "A", r1)
        tmp_cache.set("TME", "B", r2)
        count = tmp_cache.clear(distributor="Farnell")
        assert count == 1
        assert tmp_cache.get("Farnell", "A") is None
        assert tmp_cache.get("TME", "B") is not None

    @pytest.mark.unit
    def test_cache_clear_by_mpn(self, tmp_cache: DistributorCache) -> None:
        r = DistributorResult(mpn="A", distributor="Farnell", distributor_region="UK", currency="GBP")
        tmp_cache.set("Farnell", "A", r)
        count = tmp_cache.clear(mpn="A")
        assert count == 1
        assert tmp_cache.get("Farnell", "A") is None

    @pytest.mark.unit
    def test_cache_cleanup_expired(self, tmp_path: Path) -> None:
        cache = DistributorCache(cache_file=tmp_path / "cleanup.db", ttl_seconds=1)
        r = DistributorResult(mpn="OLD", distributor="Test", distributor_region="EU", currency="EUR")
        cache.set("Test", "OLD", r)
        time.sleep(1.1)
        cleaned = cache.cleanup_expired()
        assert cleaned >= 1

    @pytest.mark.unit
    def test_cache_get_stats(self, tmp_cache: DistributorCache) -> None:
        r = DistributorResult(mpn="S", distributor="Farnell", distributor_region="UK", currency="GBP")
        tmp_cache.set("Farnell", "S", r)
        stats = tmp_cache.get_stats()
        assert stats["total_entries"] == 1
        assert "Farnell" in stats["by_distributor"]

    @pytest.mark.unit
    def test_cache_mpn_case_insensitive(self, tmp_cache: DistributorCache) -> None:
        r = DistributorResult(mpn="lm358n", distributor="Farnell", distributor_region="UK", currency="GBP")
        tmp_cache.set("Farnell", "lm358n", r)
        # Should retrieve regardless of case
        assert tmp_cache.get("Farnell", "LM358N") is not None
        assert tmp_cache.get("Farnell", "lm358n") is not None


# ===========================================================================
# FarnellClient tests
# ===========================================================================


class TestFarnellClient:
    @pytest.mark.unit
    def test_distributor_name(self, farnell_client: FarnellClient) -> None:
        assert farnell_client.distributor_name == "Farnell"

    @pytest.mark.unit
    def test_distributor_region_uk(self, farnell_client: FarnellClient) -> None:
        assert farnell_client.distributor_region == "UK"

    @pytest.mark.unit
    def test_distributor_region_de(self, tmp_cache: DistributorCache) -> None:
        client = FarnellClient(
            api_key="key", store="de.farnell.com", cache=tmp_cache
        )
        assert client.distributor_region == "DE"

    @pytest.mark.unit
    def test_disabled_returns_none(self, tmp_cache: DistributorCache) -> None:
        client = FarnellClient(api_key="key", enabled=False, cache=tmp_cache)
        assert client.lookup_mpn("LM358N") is None

    @pytest.mark.unit
    def test_no_api_key_returns_none(self, tmp_cache: DistributorCache) -> None:
        client = FarnellClient(api_key="", cache=tmp_cache)
        result = client._fetch_mpn("LM358N")
        assert result is None

    @pytest.mark.integration
    def test_successful_lookup(self, farnell_client: FarnellClient) -> None:
        fixture = load_fixture("farnell_lm358n.json")
        with patch.object(farnell_client, "_http_get", return_value=fixture):
            result = farnell_client.lookup_mpn("LM358N")
        assert result is not None
        assert result.mpn == "LM358N"
        assert result.distributor == "Farnell"
        assert result.distributor_region == "UK"
        assert result.warehouse_location == "uk.farnell.com"
        assert result.manufacturer == "Texas Instruments"
        assert result.stock_level == 5432
        assert result.in_stock is True
        assert len(result.price_breaks) == 7
        assert result.price_breaks[0].quantity == 1
        assert result.price_breaks[0].unit_price == pytest.approx(0.392)
        assert result.rohs_compliant is True
        assert result.lifecycle_status == "Active"
        assert result.currency == "GBP"

    @pytest.mark.integration
    def test_no_results_returns_none(self, farnell_client: FarnellClient) -> None:
        fixture = load_fixture("farnell_no_results.json")
        with patch.object(farnell_client, "_http_get", return_value=fixture):
            result = farnell_client.lookup_mpn("XXXXNOTFOUND")
        assert result is None

    @pytest.mark.integration
    def test_http_failure_returns_none(self, farnell_client: FarnellClient) -> None:
        with patch.object(farnell_client, "_http_get", return_value=None):
            result = farnell_client.lookup_mpn("LM358N")
        assert result is None

    @pytest.mark.integration
    def test_result_is_cached(self, farnell_client: FarnellClient) -> None:
        fixture = load_fixture("farnell_lm358n.json")
        with patch.object(farnell_client, "_http_get", return_value=fixture) as mock_get:
            result1 = farnell_client.lookup_mpn("LM358N")
            result2 = farnell_client.lookup_mpn("LM358N")

        # Second call should use cache — _http_get called only once
        assert mock_get.call_count == 1
        assert result1 is not None
        assert result2 is not None
        assert result1.mpn == result2.mpn

    @pytest.mark.integration
    def test_price_breaks_sorted(self, farnell_client: FarnellClient) -> None:
        fixture = load_fixture("farnell_lm358n.json")
        with patch.object(farnell_client, "_http_get", return_value=fixture):
            result = farnell_client.lookup_mpn("LM358N")
        assert result is not None
        quantities = [pb.quantity for pb in result.price_breaks]
        assert quantities == sorted(quantities)

    @pytest.mark.integration
    def test_de_store_currency(self, tmp_cache: DistributorCache) -> None:
        client = FarnellClient(
            api_key="key", store="de.farnell.com", cache=tmp_cache
        )
        fixture = load_fixture("farnell_lm358n.json")
        with patch.object(client, "_http_get", return_value=fixture):
            result = client.lookup_mpn("LM358N")
        assert result is not None
        assert result.currency == "EUR"

    @pytest.mark.unit
    def test_build_url_contains_mpn(self, farnell_client: FarnellClient) -> None:
        url = farnell_client._build_url("LM358N")
        assert "LM358N" in url
        assert "uk.farnell.com" in url
        assert farnell_client.api_key in url


# ===========================================================================
# RSComponentsClient tests
# ===========================================================================


class TestRSComponentsClient:
    @pytest.mark.unit
    def test_distributor_name(self, rs_client: RSComponentsClient) -> None:
        assert rs_client.distributor_name == "RS Components"

    @pytest.mark.unit
    def test_distributor_region_uk(self, rs_client: RSComponentsClient) -> None:
        assert rs_client.distributor_region == "UK"

    @pytest.mark.unit
    def test_distributor_region_de(self, tmp_cache: DistributorCache) -> None:
        client = RSComponentsClient(api_key="key", locale="de", cache=tmp_cache)
        assert client.distributor_region == "DE"

    @pytest.mark.unit
    def test_disabled_returns_none(self, tmp_cache: DistributorCache) -> None:
        client = RSComponentsClient(api_key="key", enabled=False, cache=tmp_cache)
        assert client.lookup_mpn("NE555P") is None

    @pytest.mark.unit
    def test_no_api_key_returns_none(self, tmp_cache: DistributorCache) -> None:
        client = RSComponentsClient(api_key="", cache=tmp_cache)
        result = client._fetch_mpn("NE555P")
        assert result is None

    @pytest.mark.integration
    def test_successful_lookup(self, rs_client: RSComponentsClient) -> None:
        fixture = load_fixture("rs_components_ne555p.json")
        with patch.object(rs_client, "_http_get", return_value=fixture):
            result = rs_client.lookup_mpn("NE555P")
        assert result is not None
        assert result.mpn == "NE555P"
        assert result.distributor == "RS Components"
        assert result.distributor_region == "UK"
        assert result.warehouse_location == "rs-online.com"
        assert result.manufacturer == "Texas Instruments"
        assert result.stock_level == 12450
        assert result.in_stock is True
        assert len(result.price_breaks) == 6
        assert result.price_breaks[0].unit_price == pytest.approx(0.295)
        assert result.rohs_compliant is True
        assert result.currency == "GBP"

    @pytest.mark.integration
    def test_no_results_returns_none(self, rs_client: RSComponentsClient) -> None:
        fixture = load_fixture("rs_components_no_results.json")
        with patch.object(rs_client, "_http_get", return_value=fixture):
            result = rs_client.lookup_mpn("XXXXNOTFOUND")
        assert result is None

    @pytest.mark.integration
    def test_http_failure_returns_none(self, rs_client: RSComponentsClient) -> None:
        with patch.object(rs_client, "_http_get", return_value=None):
            result = rs_client.lookup_mpn("NE555P")
        assert result is None

    @pytest.mark.integration
    def test_result_is_cached(self, rs_client: RSComponentsClient) -> None:
        fixture = load_fixture("rs_components_ne555p.json")
        with patch.object(rs_client, "_http_get", return_value=fixture) as mock_get:
            result1 = rs_client.lookup_mpn("NE555P")
            result2 = rs_client.lookup_mpn("NE555P")
        assert mock_get.call_count == 1
        assert result1 is not None
        assert result2 is not None

    @pytest.mark.integration
    def test_price_breaks_sorted(self, rs_client: RSComponentsClient) -> None:
        fixture = load_fixture("rs_components_ne555p.json")
        with patch.object(rs_client, "_http_get", return_value=fixture):
            result = rs_client.lookup_mpn("NE555P")
        assert result is not None
        quantities = [pb.quantity for pb in result.price_breaks]
        assert quantities == sorted(quantities)

    @pytest.mark.integration
    def test_de_locale_currency(self, tmp_cache: DistributorCache) -> None:
        client = RSComponentsClient(api_key="key", locale="de", cache=tmp_cache)
        fixture = load_fixture("rs_components_ne555p.json")
        with patch.object(client, "_http_get", return_value=fixture):
            result = client.lookup_mpn("NE555P")
        assert result is not None
        assert result.currency == "EUR"
        assert result.distributor_region == "DE"

    @pytest.mark.unit
    def test_headers_contain_auth(self, rs_client: RSComponentsClient) -> None:
        headers = rs_client._build_headers()
        assert "Authorization" in headers
        assert rs_client.api_key in headers["Authorization"]

    @pytest.mark.integration
    def test_flat_unit_price_fallback(self, tmp_cache: DistributorCache) -> None:
        """RS client should handle a flat unitPrice field with no priceBreaks."""
        client = RSComponentsClient(api_key="key", cache=tmp_cache)
        flat_resp = {
            "products": [
                {
                    "id": "123",
                    "description": "Test component",
                    "manufacturer": "ACME",
                    "stock": {"quantity": 10},
                    "unitPrice": 1.99,
                }
            ]
        }
        with patch.object(client, "_http_get", return_value=flat_resp):
            result = client.lookup_mpn("TEST123")
        assert result is not None
        assert len(result.price_breaks) == 1
        assert result.price_breaks[0].unit_price == pytest.approx(1.99)

    @pytest.mark.integration
    def test_lookup_mpns_batch(self, rs_client: RSComponentsClient) -> None:
        fixture = load_fixture("rs_components_ne555p.json")
        with patch.object(rs_client, "_http_get", return_value=fixture):
            results = rs_client.lookup_mpns(["NE555P", "NE555P_COPY"])
        assert len(results) == 2


# ===========================================================================
# TMEClient tests
# ===========================================================================


class TestTMEClient:
    @pytest.mark.unit
    def test_distributor_name(self, tme_client: TMEClient) -> None:
        assert tme_client.distributor_name == "TME"

    @pytest.mark.unit
    def test_distributor_region(self, tme_client: TMEClient) -> None:
        assert tme_client.distributor_region == "PL"

    @pytest.mark.unit
    def test_disabled_returns_none(self, tmp_cache: DistributorCache) -> None:
        client = TMEClient(api_key="key", api_secret="secret", enabled=False, cache=tmp_cache)
        assert client.lookup_mpn("ATMEGA328P-AU") is None

    @pytest.mark.unit
    def test_no_api_key_returns_none(self, tmp_cache: DistributorCache) -> None:
        client = TMEClient(api_key="", api_secret="", cache=tmp_cache)
        result = client._fetch_mpn("ATMEGA328P-AU")
        assert result is None

    @pytest.mark.unit
    def test_sign_request_adds_signature(self, tme_client: TMEClient) -> None:
        params = {"Country": "PL", "Language": "EN"}
        signed = tme_client._sign_request("https://api.tme.eu/Products/Search.json", params)
        assert "ApiSignature" in signed
        assert "Token" in signed
        assert signed["Token"] == tme_client.api_key

    @pytest.mark.unit
    def test_sign_request_deterministic(self, tme_client: TMEClient) -> None:
        """Same inputs must always produce the same signature."""
        params = {"Country": "PL"}
        url = "https://api.tme.eu/Products/Search.json"
        sig1 = tme_client._sign_request(url, dict(params))["ApiSignature"]
        sig2 = tme_client._sign_request(url, dict(params))["ApiSignature"]
        assert sig1 == sig2

    @pytest.mark.integration
    def test_successful_lookup(self, tme_client: TMEClient) -> None:
        search_fixture = load_fixture("tme_search_atmega328.json")
        prices_fixture = load_fixture("tme_prices_atmega328.json")
        stocks_fixture = load_fixture("tme_stocks_atmega328.json")

        def side_effect(endpoint: str, params: Dict[str, str]) -> Optional[Dict[str, Any]]:
            if "Search" in endpoint:
                return search_fixture
            elif "GetPrices" in endpoint:
                return prices_fixture
            elif "GetStocks" in endpoint:
                return stocks_fixture
            return None

        with patch.object(tme_client, "_post", side_effect=side_effect):
            result = tme_client.lookup_mpn("ATMEGA328P-AU")

        assert result is not None
        assert result.mpn == "ATMEGA328P-AU"
        assert result.distributor == "TME"
        assert result.distributor_region == "PL"
        assert result.warehouse_location == "tme.eu"
        assert result.distributor_sku == "ATMEGA328P-AU"
        assert result.stock_level == 1250
        assert result.in_stock is True
        assert result.currency == "EUR"
        assert len(result.price_breaks) == 4
        assert result.price_breaks[0].unit_price == pytest.approx(3.28)
        assert result.price_breaks[1].unit_price == pytest.approx(2.71)

    @pytest.mark.integration
    def test_search_returns_none_when_no_results(self, tme_client: TMEClient) -> None:
        search_fixture = load_fixture("tme_search_no_results.json")
        with patch.object(tme_client, "_post", return_value=search_fixture):
            result = tme_client.lookup_mpn("XXXXNOTFOUND")
        assert result is None

    @pytest.mark.integration
    def test_search_http_failure_returns_none(self, tme_client: TMEClient) -> None:
        with patch.object(tme_client, "_post", return_value=None):
            result = tme_client.lookup_mpn("ATMEGA328P-AU")
        assert result is None

    @pytest.mark.integration
    def test_result_is_cached(self, tme_client: TMEClient) -> None:
        search_fixture = load_fixture("tme_search_atmega328.json")
        prices_fixture = load_fixture("tme_prices_atmega328.json")
        stocks_fixture = load_fixture("tme_stocks_atmega328.json")

        call_count = {"n": 0}

        def side_effect(endpoint: str, params: Dict[str, str]) -> Optional[Dict[str, Any]]:
            call_count["n"] += 1
            if "Search" in endpoint:
                return search_fixture
            elif "GetPrices" in endpoint:
                return prices_fixture
            elif "GetStocks" in endpoint:
                return stocks_fixture
            return None

        with patch.object(tme_client, "_post", side_effect=side_effect):
            result1 = tme_client.lookup_mpn("ATMEGA328P-AU")
            result2 = tme_client.lookup_mpn("ATMEGA328P-AU")

        # All 3 API calls should only happen once (cache hit on second call)
        assert call_count["n"] == 3
        assert result1 is not None
        assert result2 is not None

    @pytest.mark.integration
    def test_price_breaks_sorted(self, tme_client: TMEClient) -> None:
        search_fixture = load_fixture("tme_search_atmega328.json")
        prices_fixture = load_fixture("tme_prices_atmega328.json")
        stocks_fixture = load_fixture("tme_stocks_atmega328.json")

        def side_effect(endpoint: str, params: Dict[str, str]) -> Optional[Dict[str, Any]]:
            if "Search" in endpoint:
                return search_fixture
            elif "GetPrices" in endpoint:
                return prices_fixture
            return stocks_fixture

        with patch.object(tme_client, "_post", side_effect=side_effect):
            result = tme_client.lookup_mpn("ATMEGA328P-AU")

        assert result is not None
        quantities = [pb.quantity for pb in result.price_breaks]
        assert quantities == sorted(quantities)

    @pytest.mark.integration
    def test_exact_symbol_match_preferred(self, tme_client: TMEClient) -> None:
        """When the search returns multiple products, exact MPN match wins."""
        search_resp = {
            "Status": "OK",
            "Data": {
                "ProductList": [
                    {"Symbol": "ATMEGA328P-MU", "OriginalSymbol": "ATMEGA328P-MU"},
                    {"Symbol": "ATMEGA328P-AU", "OriginalSymbol": "ATMEGA328P-AU"},
                ],
                "Amount": 2,
            },
        }
        with patch.object(tme_client, "_post", return_value=search_resp):
            symbol = tme_client._search_product("ATMEGA328P-AU")
        assert symbol == "ATMEGA328P-AU"

    @pytest.mark.integration
    def test_tme_bad_status_returns_none(self, tme_client: TMEClient) -> None:
        error_resp = {"Status": "ERR_INVALID_SIGNATURE", "Data": None}
        with patch.object(tme_client, "_post", return_value=error_resp):
            result = tme_client.lookup_mpn("ATMEGA328P-AU")
        assert result is None


# ===========================================================================
# Config integration tests
# ===========================================================================


class TestDistributorsConfig:
    @pytest.mark.unit
    def test_default_config_all_disabled(self) -> None:
        from pcb_cost_estimator.config import DistributorsConfig

        cfg = DistributorsConfig()
        assert cfg.farnell.enabled is False
        assert cfg.rs_components.enabled is False
        assert cfg.tme.enabled is False

    @pytest.mark.unit
    def test_farnell_config_fields(self) -> None:
        from pcb_cost_estimator.config import DistributorConfig

        cfg = DistributorConfig(enabled=True, api_key="abc123", store="de.farnell.com")
        assert cfg.enabled is True
        assert cfg.api_key == "abc123"
        assert cfg.store == "de.farnell.com"

    @pytest.mark.unit
    def test_tme_config_fields(self) -> None:
        from pcb_cost_estimator.config import DistributorConfig

        cfg = DistributorConfig(
            enabled=True,
            api_key="token",
            api_secret="secret",
            country="PL",
            currency="EUR",
        )
        assert cfg.api_secret == "secret"
        assert cfg.country == "PL"
        assert cfg.currency == "EUR"

    @pytest.mark.unit
    def test_main_config_has_distributors(self) -> None:
        from pcb_cost_estimator.config import Config

        cfg = Config()
        assert hasattr(cfg, "distributors")
        assert hasattr(cfg.distributors, "farnell")
        assert hasattr(cfg.distributors, "rs_components")
        assert hasattr(cfg.distributors, "tme")

    @pytest.mark.unit
    def test_config_load_with_distributors(self, tmp_path: Path) -> None:
        from pcb_cost_estimator.config import load_config

        config_yaml = """
api:
  provider: openai
  api_key: ""
  model: gpt-4
  temperature: 0.0
  max_tokens: 1000
distributors:
  farnell:
    enabled: true
    api_key: farnell-test-key
    store: uk.farnell.com
  rs_components:
    enabled: false
    api_key: ""
    locale: en
  tme:
    enabled: false
    api_key: ""
    api_secret: ""
    country: PL
    currency: EUR
"""
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text(config_yaml)

        cfg = load_config(config_file)
        assert cfg["distributors"]["farnell"]["enabled"] is True
        assert cfg["distributors"]["farnell"]["api_key"] == "farnell-test-key"
        assert cfg["distributors"]["rs_components"]["enabled"] is False
        assert cfg["distributors"]["tme"]["country"] == "PL"


# ===========================================================================
# lookup_mpns batch default implementation
# ===========================================================================


class TestBatchLookup:
    @pytest.mark.integration
    def test_lookup_mpns_returns_dict(self, farnell_client: FarnellClient) -> None:
        fixture = load_fixture("farnell_lm358n.json")
        no_results = load_fixture("farnell_no_results.json")

        call_args: list = []

        def side_effect(url: str) -> Optional[Dict[str, Any]]:
            call_args.append(url)
            if "LM358N" in url:
                return fixture
            return no_results

        with patch.object(farnell_client, "_http_get", side_effect=side_effect):
            results = farnell_client.lookup_mpns(["LM358N", "UNKNOWN_PART"])

        assert "LM358N" in results
        assert "UNKNOWN_PART" in results
        assert results["LM358N"] is not None
        assert results["UNKNOWN_PART"] is None

    @pytest.mark.integration
    def test_lookup_mpns_empty_list(self, rs_client: RSComponentsClient) -> None:
        results = rs_client.lookup_mpns([])
        assert results == {}
