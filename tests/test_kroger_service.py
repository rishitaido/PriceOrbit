import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio

from services.kroger_service import (
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
    resp.json.return_value = {
        "data": products,
        "meta": {"pagination": {"total": len(products)}},
    }
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
            "price": {
                "regular": 5.99,
                "promo": 4.99,
                "regularPerUnitEstimate": 5.99,
            },
            "fulfillment": {"inStore": True, "pickupEligible": True},
        }
    ],
}


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
    product_resp = _mock_product_response([SAMPLE_PRODUCT])
    service._http.request = AsyncMock(return_value=product_resp)

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
    success_resp = _mock_product_response([SAMPLE_PRODUCT])
    service._http.request = AsyncMock(side_effect=[unauthorized, success_resp])

    token_resp = _mock_token_response()
    with patch("httpx.AsyncClient") as MockClient:
        mock_ctx = AsyncMock()
        mock_ctx.post = AsyncMock(return_value=token_resp)
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


@pytest.mark.asyncio
async def test_search_products_returns_list(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600
    product_resp = _mock_product_response([SAMPLE_PRODUCT])
    service._http.request = AsyncMock(return_value=product_resp)

    results = await service.search_products("milk")
    assert isinstance(results, list)
    assert results[0]["description"] == SAMPLE_PRODUCT["description"]


@pytest.mark.asyncio
async def test_search_products_passes_query_param(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600
    product_resp = _mock_product_response([])
    service._http.request = AsyncMock(return_value=product_resp)

    await service.search_products("butter")
    call_kwargs = service._http.request.call_args
    params = call_kwargs[1]["params"] if "params" in call_kwargs[1] else call_kwargs[0][2]
    assert params["filter.term"] == "butter"


@pytest.mark.asyncio
async def test_search_products_empty_returns_empty_list(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600
    product_resp = _mock_product_response([])
    service._http.request = AsyncMock(return_value=product_resp)

    results = await service.search_products("xyznonexistentproduct999")
    assert results == []


@pytest.mark.asyncio
async def test_get_product_price_success(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600
    product_resp = _mock_product_response([SAMPLE_PRODUCT])
    service._http.request = AsyncMock(return_value=product_resp)

    result = await service.get_product_price("organic milk")
    assert result["productId"] == SAMPLE_PRODUCT["productId"]
    assert result["price"]["regular"] == 5.99
    assert result["price"]["promo"] == 4.99
    assert result["price"]["unitOfMeasure"] == "1 gal"


@pytest.mark.asyncio
async def test_get_product_price_no_results_raises(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600
    product_resp = _mock_product_response([])
    service._http.request = AsyncMock(return_value=product_resp)

    with pytest.raises(KrogerAPIError, match="No products found"):
        await service.get_product_price("zyxwvutsrq")


@pytest.mark.asyncio
async def test_get_product_price_no_items_returns_empty_price(service: KrogerService):
    product_no_items = {**SAMPLE_PRODUCT, "items": []}
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600
    product_resp = _mock_product_response([product_no_items])
    service._http.request = AsyncMock(return_value=product_resp)

    result = await service.get_product_price("mystery item")
    assert result["price"] == {}


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
async def test_5xx_retries_then_raises(service: KrogerService):
    _token_store.access_token = "tok"
    _token_store.expires_at = time.monotonic() + 3600

    server_error = MagicMock(spec=httpx.Response)
    server_error.status_code = 503
    server_error.is_success = False
    server_error.text = "Service Unavailable"
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


@pytest.mark.asyncio
async def test_cache_is_used_on_second_call():
    async with KrogerService(CLIENT_ID, CLIENT_SECRET, use_cache=True) as svc:
        _token_store.access_token = "tok"
        _token_store.expires_at = time.monotonic() + 3600
        product_resp = _mock_product_response([SAMPLE_PRODUCT])
        svc._http.request = AsyncMock(return_value=product_resp)

        r1 = await svc.search_products("milk")
        r2 = await svc.search_products("milk")

        assert svc._http.request.call_count == 1
        assert r1 == r2


@pytest.mark.asyncio
async def test_cache_expires():
    _cache_set("search:milk:10:1", [SAMPLE_PRODUCT])
    _response_cache["search:milk:10:1"] = (time.monotonic() - 9999, [SAMPLE_PRODUCT])
    assert _cache_get("search:milk:10:1") is None


def test_clear_cache():
    _cache_set("some:key", {"data": True})
    assert _cache_get("some:key") is not None
    svc = KrogerService(CLIENT_ID, CLIENT_SECRET)
    svc.clear_cache()
    assert _cache_get("some:key") is None


@pytest.mark.asyncio
async def test_async_context_manager():
    async with KrogerService(CLIENT_ID, CLIENT_SECRET, use_cache=False) as svc:
        assert isinstance(svc, KrogerService)
