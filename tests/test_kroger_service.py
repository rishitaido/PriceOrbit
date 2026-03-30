import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio

from app.services.kroger_service import (
    KrogerAPIError,
    KrogerRateLimitError,
    KrogerService,
    _cache_get,
    _cache_set,
    _response_cache,
    _token_store,
)

CLIENT_ID = "test-client-id"
CLIENT_SECRET = "test-client-secret"


@pytest.fixture(autouse=True)
def reset_token_store():
    _token_store.access_token = None
    _token_store.expires_at = 0.0
    yield
    _token_store.access_token = None
    _token_store.expires_at = 0.0


@pytest.fixture(autouse=True)
def reset_cache():
    _response_cache.clear()
    yield
    _response_cache.clear()


@pytest_asyncio.fixture
async def service():
    svc = KrogerService(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, use_cache=False)
    yield svc
    await svc.aclose()


def _mock_token_response(expires_in: int = 1800) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {
        "access_token": "fake-token-abc",
        "expires_in": expires_in,
        "token_type": "Bearer",
    }
    resp.is_success = True
    return resp


def _mock_product_response(products: list[dict]) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.is_success = True
    resp.json.return_value = {"data": products, "meta": {}}
    return resp


def _mock_single_product_response(product: dict) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.is_success = True
    resp.json.return_value = {"data": product, "meta": {}}
    return resp


SAMPLE_PRODUCT = {
    "productId": "0001111060903",
    "description": "Simple Truth Organic Whole Milk",
    "brand": "Simple Truth Organic",
    "categories": ["Dairy"],
    "items": [
        {
            "itemId": "0001111060903",
            "size": "1 gal",
            "soldBy": "unit",
            "price": {
                "regular": 5.99,
                "promo": 4.99,
                "regularPerUnitEstimate": 5.99,
                "promoPerUnitEstimate": 4.99,
            },
            "nationalPrice": {
                "regular": 6.29,
                "promo": None,
                "regularPerUnitEstimate": 6.29,
                "promoPerUnitEstimate": None,
            },
            "fulfillment": {
                "instore": True,
                "curbside": True,
                "delivery": False,
                "shiptohome": False,
            },
            "inventory": {"stockLevel": "HIGH"},
        }
    ],
}

SAMPLE_LOCATION = {
    "locationId": "01400943",
    "name": "Kroger Midtown",
    "address": {
        "addressLine1": "725 Ponce De Leon Ave",
        "city": "Atlanta",
        "state": "GA",
        "zipCode": "30306",
    },
    "geolocation": {
        "latitude": 33.7721,
        "longitude": -84.3656,
    },
    "phone": {"number": "(404) 555-1212"},
    "hours": {"timezone": "EST"},
}


# --- Authentication ---

@pytest.mark.asyncio
async def test_token_fetched_on_first_call(service: KrogerService):
    token_resp = _mock_token_response()
    product_resp = _mock_product_response([SAMPLE_PRODUCT])

    with patch("httpx.AsyncClient") as MockClient:
        mock_ctx = AsyncMock()
        mock_ctx.post = AsyncMock(return_value=token_resp)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        service._http.request = AsyncMock(return_value=product_resp)
        await service.search_products("milk")

    assert _token_store.access_token == "fake-token-abc"
    assert _token_store.expires_at > time.monotonic()


@pytest.mark.asyncio
async def test_token_not_refreshed_when_valid(service: KrogerService):
    _token_store.access_token = "cached-token"
    _token_store.expires_at = time.monotonic() + 3600
    service._http.request = AsyncMock(return_value=_mock_product_response([SAMPLE_PRODUCT]))

    with patch("httpx.AsyncClient") as MockClient:
        await service.search_products("eggs")
        MockClient.assert_not_called()


@pytest.mark.asyncio
async def test_token_refreshed_on_401(service: KrogerService):
    _token_store.access_token = "old-token"
    _token_store.expires_at = time.monotonic() + 3600

    unauthorized = MagicMock(spec=httpx.Response)
    unauthorized.status_code = 401
    unauthorized.is_success = False
    service._http.request = AsyncMock(
        side_effect=[unauthorized, _mock_product_response([SAMPLE_PRODUCT])]
    )

    with patch("httpx.AsyncClient") as MockClient:
        mock_ctx = AsyncMock()
        mock_ctx.post = AsyncMock(return_value=_mock_token_response())
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        results = await service.search_products("cheese")

    assert len(results) == 1
    assert _token_store.access_token == "fake-token-abc"


@pytest.mark.asyncio
async def test_token_request_failure_raises():
    async with KrogerService(CLIENT_ID, CLIENT_SECRET, use_cache=False) as svc:
        bad_resp = MagicMock(spec=httpx.Response)
        bad_resp.status_code = 401
        bad_resp.text = "Unauthorized"

        with patch("httpx.AsyncClient") as MockClient:
            mock_ctx = AsyncMock()
            mock_ctx.post = AsyncMock(return_value=bad_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(KrogerAPIError, match="Token request failed"):
                await svc._fetch_token()


# --- search_products ---

@pytest.mark.asyncio
async def test_search_products_returns_list(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600
    service._http.request = AsyncMock(return_value=_mock_product_response([SAMPLE_PRODUCT]))

    results = await service.search_products("milk")
    assert isinstance(results, list)
    assert results[0]["description"] == SAMPLE_PRODUCT["description"]


@pytest.mark.asyncio
async def test_search_products_passes_correct_params(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600
    service._http.request = AsyncMock(return_value=_mock_product_response([]))

    await service.search_products("butter", brand="Kroger", fulfillment="ais", limit=5, start=1)

    call_kwargs = service._http.request.call_args
    params = call_kwargs[1].get("params") or call_kwargs[0][2]
    assert params["filter.term"] == "butter"
    assert params["filter.brand"] == "Kroger"
    assert params["filter.fulfillment"] == "ais"
    assert params["filter.limit"] == 5
    assert params["filter.start"] == 1


@pytest.mark.asyncio
async def test_search_products_clamps_limit(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600
    service._http.request = AsyncMock(return_value=_mock_product_response([]))

    await service.search_products("milk", limit=999)

    call_kwargs = service._http.request.call_args
    params = call_kwargs[1].get("params") or call_kwargs[0][2]
    assert params["filter.limit"] == 50


@pytest.mark.asyncio
async def test_search_products_rejects_over_8_words(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600

    with pytest.raises(ValueError, match="8-word"):
        await service.search_products("one two three four five six seven eight nine")


@pytest.mark.asyncio
async def test_search_requires_query_or_brand(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600

    with pytest.raises(ValueError, match="query.*brand"):
        await service.search_products("")


@pytest.mark.asyncio
async def test_search_products_empty_returns_empty_list(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600
    service._http.request = AsyncMock(return_value=_mock_product_response([]))

    results = await service.search_products("xyznonexistentproduct999")
    assert results == []


# --- get_product_by_id ---

@pytest.mark.asyncio
async def test_get_product_by_id_success(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600
    service._http.request = AsyncMock(
        return_value=_mock_single_product_response(SAMPLE_PRODUCT)
    )

    result = await service.get_product_by_id("0001111060903")
    assert result["productId"] == SAMPLE_PRODUCT["productId"]
    assert result["description"] == SAMPLE_PRODUCT["description"]


@pytest.mark.asyncio
async def test_get_product_by_id_invalid_length_raises(service: KrogerService):
    with pytest.raises(ValueError, match="13 digits"):
        await service.get_product_by_id("123")


@pytest.mark.asyncio
async def test_get_product_by_id_passes_location(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600
    service._http.request = AsyncMock(
        return_value=_mock_single_product_response(SAMPLE_PRODUCT)
    )

    await service.get_product_by_id("0001111060903")

    call_kwargs = service._http.request.call_args
    params = call_kwargs[1].get("params") or call_kwargs[0][2]
    assert "filter.locationId" in params


# --- store search ---

@pytest.mark.asyncio
async def test_search_stores_by_zip_returns_parsed_store(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600
    service._http.request = AsyncMock(return_value=_mock_product_response([SAMPLE_LOCATION]))

    stores = await service.search_stores("30303", radius_miles=10, limit=5)

    assert len(stores) == 1
    assert stores[0]["kroger_location_id"] == "01400943"
    assert stores[0]["city"] == "Atlanta"
    assert stores[0]["state"] == "GA"
    assert stores[0]["zip_code"] == "30306"


@pytest.mark.asyncio
async def test_search_stores_by_coords_passes_correct_params(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600
    service._http.request = AsyncMock(return_value=_mock_product_response([]))

    await service.search_stores_by_coords(33.7490, -84.3880, radius_miles=12, limit=7)

    call_kwargs = service._http.request.call_args
    params = call_kwargs[1].get("params") or call_kwargs[0][2]
    assert params["filter.lat.near"] == pytest.approx(33.7490, rel=1e-6)
    assert params["filter.lon.near"] == pytest.approx(-84.3880, rel=1e-6)
    assert params["filter.radiusInMiles"] == 12
    assert params["filter.limit"] == 7


@pytest.mark.asyncio
async def test_search_stores_invalid_zip_raises(service: KrogerService):
    with pytest.raises(ValueError, match="5-digit"):
        await service.search_stores("3030A")


# --- get_product_price ---

@pytest.mark.asyncio
async def test_get_product_price_success(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600
    service._http.request = AsyncMock(return_value=_mock_product_response([SAMPLE_PRODUCT]))

    result = await service.get_product_price("organic milk")
    assert result["productId"] == SAMPLE_PRODUCT["productId"]
    assert result["price"]["regular"] == 5.99
    assert result["price"]["promo"] == 4.99
    assert result["price"]["regularPerUnitEstimate"] == 5.99
    assert result["nationalPrice"]["regular"] == 6.29
    assert result["size"] == "1 gal"
    assert result["soldBy"] == "unit"
    assert result["stockLevel"] == "HIGH"


@pytest.mark.asyncio
async def test_get_product_price_fulfillment_keys(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600
    service._http.request = AsyncMock(return_value=_mock_product_response([SAMPLE_PRODUCT]))

    result = await service.get_product_price("milk")
    f = result["fulfillment"]
    assert f["instore"] is True
    assert f["curbside"] is True
    assert f["delivery"] is False
    assert f["shiptohome"] is False


@pytest.mark.asyncio
async def test_get_product_price_no_results_raises(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600
    service._http.request = AsyncMock(return_value=_mock_product_response([]))

    with pytest.raises(KrogerAPIError, match="No products found"):
        await service.get_product_price("zyxwvutsrq")


@pytest.mark.asyncio
async def test_get_product_price_no_items_returns_empty_price(service: KrogerService):
    product_no_items = {**SAMPLE_PRODUCT, "items": []}
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600
    service._http.request = AsyncMock(return_value=_mock_product_response([product_no_items]))

    result = await service.get_product_price("mystery item")
    assert result["price"] == {
        "regular": None, "promo": None,
        "regularPerUnitEstimate": None, "promoPerUnitEstimate": None,
    }


@pytest.mark.asyncio
async def test_get_product_price_by_location(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600
    service._http.request = AsyncMock(
        return_value=_mock_single_product_response(SAMPLE_PRODUCT)
    )

    result = await service.get_product_price_by_location("0001111060903", "01400943")

    assert result["productId"] == SAMPLE_PRODUCT["productId"]
    assert result["locationId"] == "01400943"
    assert result["price"]["regular"] == 5.99


# --- Error handling ---

@pytest.mark.asyncio
async def test_rate_limit_raises_KrogerRateLimitError(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600

    rate_limited = MagicMock(spec=httpx.Response)
    rate_limited.status_code = 429
    rate_limited.is_success = False
    rate_limited.headers = {"Retry-After": "30"}
    service._http.request = AsyncMock(return_value=rate_limited)

    with pytest.raises(KrogerRateLimitError, match="Rate limited"):
        await service.search_products("milk")


@pytest.mark.asyncio
async def test_timeout_raises_KrogerAPIError(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600
    service._http.request = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

    with pytest.raises(KrogerAPIError, match="timed out"):
        await service.search_products("milk")


@pytest.mark.asyncio
async def test_network_error_raises_KrogerAPIError(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600
    service._http.request = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

    with pytest.raises(KrogerAPIError, match="Network error"):
        await service.search_products("milk")


@pytest.mark.asyncio
async def test_400_parses_reason_field(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600

    bad_req = MagicMock(spec=httpx.Response)
    bad_req.status_code = 400
    bad_req.is_success = False
    bad_req.json.return_value = {"reason": "Field 'locationId' must have a length of 8 characters", "code": "API-4101-400"}
    service._http.request = AsyncMock(return_value=bad_req)

    with pytest.raises(KrogerAPIError, match="locationId"):
        await service.search_products("milk")


@pytest.mark.asyncio
async def test_5xx_retries_then_raises(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600

    server_error = MagicMock(spec=httpx.Response)
    server_error.status_code = 503
    server_error.is_success = False
    server_error.json.return_value = {"errors": {"reason": "Internal server error"}}
    service._http.request = AsyncMock(return_value=server_error)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(KrogerAPIError, match="503"):
            await service.search_products("milk")


@pytest.mark.asyncio
async def test_invalid_json_raises_KrogerAPIError(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600

    bad_resp = MagicMock(spec=httpx.Response)
    bad_resp.status_code = 200
    bad_resp.is_success = True
    bad_resp.json.side_effect = ValueError("No JSON")
    service._http.request = AsyncMock(return_value=bad_resp)

    with pytest.raises(KrogerAPIError, match="Invalid JSON"):
        await service.search_products("milk")


# --- Cache ---

@pytest.mark.asyncio
async def test_cache_is_used_on_second_call():
    async with KrogerService(CLIENT_ID, CLIENT_SECRET, use_cache=True) as svc:
        _token_store.access_token = "tok"
        _token_store.expires_at = time.monotonic() + 3600
        svc._http.request = AsyncMock(return_value=_mock_product_response([SAMPLE_PRODUCT]))

        r1 = await svc.search_products("milk")
        r2 = await svc.search_products("milk")

        assert svc._http.request.call_count == 1
        assert r1 == r2


@pytest.mark.asyncio
async def test_cache_expires():
    _cache_set("search:milk:None:None:10:1", [SAMPLE_PRODUCT])
    _response_cache["search:milk:None:None:10:1"] = (time.monotonic() - 9999, [SAMPLE_PRODUCT])
    assert _cache_get("search:milk:None:None:10:1") is None


def test_clear_cache():
    _cache_set("some:key", {"data": True})
    assert _cache_get("some:key") is not None
    KrogerService(CLIENT_ID, CLIENT_SECRET).clear_cache()
    assert _cache_get("some:key") is None


@pytest.mark.asyncio
async def test_async_context_manager():
    async with KrogerService(CLIENT_ID, CLIENT_SECRET, use_cache=False) as svc:
        assert isinstance(svc, KrogerService)
