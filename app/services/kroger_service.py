import asyncio
import logging
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)

KROGER_TOKEN_URL = "https://api.kroger.com/v1/connect/oauth2/token"
KROGER_BASE_URL = "https://api.kroger.com/v1"
KROGER_SCOPES = "product.compact"

_response_cache: dict[str, tuple[float, Any]] = {}
CACHE_TTL_SECONDS = 300


def _cache_get(key: str) -> Optional[Any]:
    entry = _response_cache.get(key)
    if entry is None:
        return None
    ts, payload = entry
    if time.monotonic() - ts > CACHE_TTL_SECONDS:
        del _response_cache[key]
        return None
    logger.debug("Cache HIT for key: %s", key)
    return payload


def _cache_set(key: str, payload: Any) -> None:
    _response_cache[key] = (time.monotonic(), payload)
    logger.debug("Cache SET for key: %s", key)


class _TokenStore:
    def __init__(self) -> None:
        self.access_token: Optional[str] = None
        self.expires_at: float = 0.0
        self._lock = asyncio.Lock()

    def is_valid(self, buffer_seconds: int = 60) -> bool:
        return (
            self.access_token is not None
            and time.monotonic() < self.expires_at - buffer_seconds
        )


_token_store = _TokenStore()


class KrogerAPIError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class KrogerRateLimitError(KrogerAPIError):
    pass


class KrogerService:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        location_id: str = "01400943",
        timeout: float = 10.0,
        use_cache: bool = True,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.location_id = location_id
        self.timeout = timeout
        self.use_cache = use_cache
        self._http = httpx.AsyncClient(
            base_url=KROGER_BASE_URL,
            timeout=self.timeout,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "KrogerService":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    async def _fetch_token(self) -> None:
        logger.debug("Fetching new OAuth token from Kroger…")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                KROGER_TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "scope": KROGER_SCOPES,
                },
                auth=(self.client_id, self.client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if response.status_code != 200:
            raise KrogerAPIError(
                f"Token request failed: {response.status_code} – {response.text}",
                status_code=response.status_code,
            )

        data = response.json()
        _token_store.access_token = data["access_token"]
        _token_store.expires_at = time.monotonic() + data.get("expires_in", 1800)
        logger.info("OAuth token acquired; expires in %s s", data.get("expires_in"))

    async def _ensure_token(self) -> str:
        async with _token_store._lock:
            if not _token_store.is_valid():
                await self._fetch_token()
        return _token_store.access_token  # type: ignore[return-value]

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        retries: int = 2,
    ) -> dict:
        token = await self._ensure_token()
        headers = {"Authorization": f"Bearer {token}"}

        for attempt in range(retries + 1):
            logger.debug("→ %s %s params=%s (attempt %d)", method, path, params, attempt + 1)
            try:
                response = await self._http.request(
                    method, path, params=params, headers=headers
                )
            except httpx.TimeoutException as exc:
                raise KrogerAPIError(f"Request timed out: {exc}") from exc
            except httpx.RequestError as exc:
                raise KrogerAPIError(f"Network error: {exc}") from exc

            logger.debug("← %s %s", response.status_code, path)

            if response.status_code == 401 and attempt == 0:
                logger.warning("401 received – refreshing token and retrying…")
                async with _token_store._lock:
                    await self._fetch_token()
                headers["Authorization"] = f"Bearer {_token_store.access_token}"
                continue

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                raise KrogerRateLimitError(
                    f"Rate limited by Kroger API. Retry after {retry_after}s.",
                    status_code=429,
                )

            if response.status_code >= 500 and attempt < retries:
                backoff = 2 ** attempt
                logger.warning("5xx error – retrying in %ss…", backoff)
                await asyncio.sleep(backoff)
                continue

            if not response.is_success:
                raise KrogerAPIError(
                    f"API error {response.status_code}: {response.text}",
                    status_code=response.status_code,
                )

            try:
                return response.json()
            except Exception as exc:
                raise KrogerAPIError(f"Invalid JSON response: {exc}") from exc

        raise KrogerAPIError("Maximum retries exceeded.")

    async def search_products(
        self,
        query: str,
        limit: int = 10,
        page: int = 1,
    ) -> list[dict]:
        cache_key = f"search:{query}:{limit}:{page}"
        if self.use_cache and (cached := _cache_get(cache_key)):
            return cached

        params = {
            "filter.term": query,
            "filter.limit": min(limit, 50),
            "filter.start": (page - 1) * min(limit, 50) + 1,
            "filter.locationId": self.location_id,
        }

        data = await self._request("GET", "/products", params=params)
        products: list[dict] = data.get("data", [])

        total_requested = limit
        fetched = len(products)
        current_page = page

        while fetched < total_requested:
            meta = data.get("meta", {})
            pagination = meta.get("pagination", {})
            total_available = pagination.get("total", fetched)

            if fetched >= total_available:
                break

            current_page += 1
            next_params = {**params, "filter.start": (current_page - 1) * 50 + 1}
            data = await self._request("GET", "/products", params=next_params)
            next_products = data.get("data", [])
            if not next_products:
                break
            products.extend(next_products)
            fetched = len(products)

        products = products[:total_requested]

        if self.use_cache:
            _cache_set(cache_key, products)

        logger.info("search_products('%s') → %d results", query, len(products))
        return products

    async def get_product_price(self, product_name: str) -> dict:
        cache_key = f"price:{product_name}"
        if self.use_cache and (cached := _cache_get(cache_key)):
            return cached

        products = await self.search_products(product_name, limit=1)

        if not products:
            raise KrogerAPIError(f"No products found for '{product_name}'.")

        product = products[0]
        items: list[dict] = product.get("items", [])
        price_data: dict = {}

        if items:
            item = items[0]
            price_block = item.get("price", {})
            price_data = {
                "regular": price_block.get("regular"),
                "promo": price_block.get("promo"),
                "unitOfMeasure": item.get("size"),
                "pricePer": price_block.get("regularPerUnitEstimate"),
            }

        result = {
            "productId": product.get("productId"),
            "description": product.get("description"),
            "brand": product.get("brand"),
            "price": price_data,
            "fulfillment": items[0].get("fulfillment", {}) if items else {},
        }

        if self.use_cache:
            _cache_set(cache_key, result)

        logger.info(
            "get_product_price('%s') → %s @ $%s",
            product_name,
            result["description"],
            price_data.get("regular"),
        )
        return result

    def clear_cache(self) -> None:
        _response_cache.clear()
        logger.info("Response cache cleared.")
