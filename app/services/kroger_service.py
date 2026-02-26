import asyncio
import logging
import time
from difflib import SequenceMatcher
from typing import Any, Literal, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

KROGER_TOKEN_URL = "https://api.kroger.com/v1/connect/oauth2/token"
KROGER_BASE_URL = "https://api.kroger.com/v1"
KROGER_SCOPES = "product.compact"

FulfillmentFilter = Literal["ais", "csp", "dth", "sth"]

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


def _parse_error_reason(response: httpx.Response) -> str:
    try:
        body = response.json()
        if "reason" in body:
            return body["reason"]
        errors = body.get("errors", {})
        if isinstance(errors, dict):
            return errors.get("reason") or errors.get("error_description") or response.text
    except Exception:
        pass
    return response.text


class KrogerService:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        location_id: str = "01400943",
        timeout: float = 10.0,
        use_cache: bool = True,
        base_url: Optional[str] = None,
        token_url: Optional[str] = None,
        scope: str = KROGER_SCOPES,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.location_id = location_id
        self.timeout = timeout
        self.use_cache = use_cache
        self.base_url = base_url or settings.KROGER_BASE_URL or KROGER_BASE_URL
        self.token_url = token_url or settings.KROGER_AUTH_URL or KROGER_TOKEN_URL
        self.scope = scope
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "KrogerService":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    async def _fetch_token(self) -> None:
        logger.debug("Fetching new OAuth token from Kroger...")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.token_url,
                    data={
                        "grant_type": "client_credentials",
                        "scope": self.scope,
                    },
                    auth=(self.client_id, self.client_secret),
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "User-Agent": (
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/121.0.0.0 Safari/537.36"
                        ),
                    },
                )
        except httpx.RequestError as exc:
            raise KrogerAPIError(f"Token request network error: {exc}") from exc

        if response.status_code != 200:
            raise KrogerAPIError(
                f"Token request failed: {response.status_code} - {response.text}",
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
        headers = {"Authorization": f"Bearer {token}",
                   "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"}

        for attempt in range(retries + 1):
            logger.debug("-> %s %s params=%s (attempt %d)", method, path, params, attempt + 1)
            try:
                response = await self._http.request(
                    method, path, params=params, headers=headers
                )
            except httpx.TimeoutException as exc:
                raise KrogerAPIError(f"Request timed out: {exc}") from exc
            except httpx.RequestError as exc:
                raise KrogerAPIError(f"Network error: {exc}") from exc

            logger.debug("<- %s %s", response.status_code, path)

            if response.status_code == 401 and attempt == 0:
                logger.warning("401 received - refreshing token and retrying...")
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
                logger.warning("5xx error - retrying in %ss...", backoff)
                await asyncio.sleep(backoff)
                continue

            if not response.is_success:
                reason = _parse_error_reason(response)
                raise KrogerAPIError(
                    f"API error {response.status_code}: {reason}",
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
        *,
        brand: Optional[str] = None,
        fulfillment: Optional[FulfillmentFilter] = None,
        limit: int = 10,
        start: int = 1,
    ) -> list[dict]:
        if not query and not brand:
            raise ValueError("At least one of 'query' or 'brand' is required.")

        word_count = len(query.split()) if query else 0
        if word_count > 8:
            raise ValueError(f"Search term exceeds the 8-word API limit (got {word_count} words).")

        cache_key = f"search:{query}:{brand}:{fulfillment}:{limit}:{start}"
        if self.use_cache and (cached := _cache_get(cache_key)):
            return cached

        params: dict[str, Any] = {
            "filter.limit": max(1, min(limit, 50)),
            "filter.start": max(1, min(start, 1000)),
            "filter.locationId": self.location_id,
        }
        if query:
            params["filter.term"] = query
        if brand:
            params["filter.brand"] = brand
        if fulfillment:
            params["filter.fulfillment"] = fulfillment

        data = await self._request("GET", "/products", params=params)
        products: list[dict] = data.get("data", [])

        if self.use_cache:
            _cache_set(cache_key, products)

        logger.info("search_products('%s') -> %d results", query or brand, len(products))
        return products

    @staticmethod
    def _extract_image_url(product_payload: dict) -> Optional[str]:
        images = product_payload.get("images") or []
        if not images:
            return None

        first_image = images[0]
        sizes = first_image.get("sizes") or []
        if not sizes:
            return None

        return sizes[-1].get("url")

    @staticmethod
    def _confidence(search_term: str, description: str) -> float:
        return round(SequenceMatcher(None, search_term.lower(), description.lower()).ratio() * 100, 1)

    async def find_kroger_product(
        self,
        product_name: str,
        *,
        min_confidence: float = 70.0,
        limit: int = 5,
    ) -> Optional[dict]:
        """
        Search Kroger products and return the best match with confidence score.
        """
        query = product_name.strip()
        if not query:
            raise ValueError("Product name is required.")

        candidates = await self.search_products(query, limit=limit)
        if not candidates:
            logger.info("No Kroger matches found for '%s'", product_name)
            return None

        scored: list[tuple[float, dict]] = []
        for product in candidates:
            description = product.get("description") or ""
            if not description:
                continue
            scored.append((self._confidence(query, description), product))

        if not scored:
            return None

        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best_product = scored[0]
        if best_score < min_confidence:
            logger.info(
                "No Kroger match above confidence threshold for '%s'. Best=%.1f",
                product_name,
                best_score,
            )
            return None

        second_best = scored[1][0] if len(scored) > 1 else 0.0
        ambiguous = second_best >= min_confidence and (best_score - second_best) <= 5.0
        suggestions = [
            {
                "product_id": item.get("productId"),
                "description": item.get("description"),
                "confidence": score,
            }
            for score, item in scored[:3]
        ]

        match = {
            "product_id": best_product.get("productId"),
            "description": best_product.get("description"),
            "confidence": best_score,
            "ambiguous": ambiguous,
            "image_url": self._extract_image_url(best_product),
            "suggestions": suggestions,
        }
        logger.info(
            "Kroger best match for '%s': id=%s confidence=%.1f ambiguous=%s",
            product_name,
            match["product_id"],
            best_score,
            ambiguous,
        )
        return match

    async def get_product_by_id(self, product_id: str) -> dict:
        if len(product_id) != 13:
            raise ValueError(f"productId must be exactly 13 digits (got {len(product_id)}).")

        cache_key = f"product:{product_id}:{self.location_id}"
        if self.use_cache and (cached := _cache_get(cache_key)):
            return cached

        params = {"filter.locationId": self.location_id}
        data = await self._request("GET", f"/products/{product_id}", params=params)
        product: dict = data.get("data", {})

        if self.use_cache:
            _cache_set(cache_key, product)

        logger.info("get_product_by_id('%s') -> %s", product_id, product.get("description"))
        return product

    async def get_product_details(self, kroger_product_id: str) -> dict:
        """Return full Kroger payload for a specific Kroger product ID."""
        return await self.get_product_by_id(kroger_product_id)

    async def get_product_price(self, product_name: str) -> dict:
        cache_key = f"price:{product_name}:{self.location_id}"
        if self.use_cache and (cached := _cache_get(cache_key)):
            return cached

        products = await self.search_products(product_name, limit=1)

        if not products:
            raise KrogerAPIError(f"No products found for '{product_name}'.")

        product = products[0]
        items: list[dict] = product.get("items", [])
        item = items[0] if items else {}

        def _extract_price(block: dict) -> dict:
            return {
                "regular": block.get("regular"),
                "promo": block.get("promo"),
                "regularPerUnitEstimate": block.get("regularPerUnitEstimate"),
                "promoPerUnitEstimate": block.get("promoPerUnitEstimate"),
            }

        fulfillment_block = item.get("fulfillment", {})
        inventory_block = item.get("inventory", {})

        result = {
            "productId": product.get("productId"),
            "description": product.get("description"),
            "brand": product.get("brand"),
            "size": item.get("size"),
            "soldBy": item.get("soldBy"),
            "stockLevel": inventory_block.get("stockLevel"),
            "price": _extract_price(item.get("price", {})),
            "nationalPrice": _extract_price(item.get("nationalPrice", {})),
            "fulfillment": {
                "instore": fulfillment_block.get("instore"),
                "curbside": fulfillment_block.get("curbside"),
                "delivery": fulfillment_block.get("delivery"),
                "shiptohome": fulfillment_block.get("shiptohome"),
            },
        }

        if self.use_cache:
            _cache_set(cache_key, result)

        logger.info(
            "get_product_price('%s') -> %s @ $%s",
            product_name,
            result["description"],
            result["price"].get("regular"),
        )
        return result

    def clear_cache(self) -> None:
        _response_cache.clear()
        logger.info("Response cache cleared.")
