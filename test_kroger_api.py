#!/usr/bin/env python3
import argparse
import asyncio
import logging
import os
import re
import sys
import time
from datetime import datetime
from typing import Optional

try:
    from services.kroger_service import KrogerService, KrogerAPIError, KrogerRateLimitError
except ImportError:
    import httpx

    _token_store_data: dict = {"token": None, "expires_at": 0.0}
    _token_lock = asyncio.Lock()

    KROGER_TOKEN_URL = "https://api.kroger.com/v1/connect/oauth2/token"
    KROGER_BASE_URL = "https://api.kroger.com/v1"

    class KrogerAPIError(Exception):
        def __init__(self, message: str, status_code: Optional[int] = None):
            super().__init__(message)
            self.status_code = status_code

    class KrogerRateLimitError(KrogerAPIError):
        pass

    class KrogerService:
        def __init__(self, client_id, client_secret, location_id="01400943",
                     timeout=15.0, use_cache=True):
            self.client_id = client_id
            self.client_secret = client_secret
            self.location_id = location_id
            self.timeout = timeout
            self.use_cache = use_cache
            self._http = httpx.AsyncClient(base_url=KROGER_BASE_URL, timeout=timeout)
            self._cache: dict = {}

        async def aclose(self):
            await self._http.aclose()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            await self.aclose()

        async def _fetch_token(self):
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    KROGER_TOKEN_URL,
                    data={"grant_type": "client_credentials", "scope": "product.basic"},
                    auth=(self.client_id, self.client_secret),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            if resp.status_code != 200:
                raise KrogerAPIError(
                    f"Token request failed ({resp.status_code}): {resp.text}",
                    status_code=resp.status_code,
                )
            data = resp.json()
            _token_store_data["token"] = data["access_token"]
            _token_store_data["expires_at"] = time.monotonic() + data.get("expires_in", 1800)

        async def _ensure_token(self) -> str:
            async with _token_lock:
                if (not _token_store_data["token"] or
                        time.monotonic() >= _token_store_data["expires_at"] - 60):
                    await self._fetch_token()
            return _token_store_data["token"]

        async def _request(self, method, path, params=None, retries=2):
            token = await self._ensure_token()
            headers = {"Authorization": f"Bearer {token}"}
            for attempt in range(retries + 1):
                try:
                    resp = await self._http.request(method, path, params=params, headers=headers)
                except httpx.TimeoutException as e:
                    raise KrogerAPIError(f"Request timed out: {e}") from e
                except httpx.RequestError as e:
                    raise KrogerAPIError(f"Network error: {e}") from e
                if resp.status_code == 401 and attempt == 0:
                    await self._fetch_token()
                    headers["Authorization"] = f"Bearer {_token_store_data['token']}"
                    continue
                if resp.status_code == 429:
                    raise KrogerRateLimitError(
                        f"Rate limited. Retry after {resp.headers.get('Retry-After', 60)}s.",
                        status_code=429)
                if resp.status_code >= 500 and attempt < retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                if not resp.is_success:
                    raise KrogerAPIError(f"API error {resp.status_code}: {resp.text}",
                                         status_code=resp.status_code)
                try:
                    return resp.json()
                except Exception as e:
                    raise KrogerAPIError(f"Invalid JSON: {e}") from e
            raise KrogerAPIError("Maximum retries exceeded.")

        async def search_products(self, query, limit=10, start=1):
            cache_key = f"search:{query}:{limit}"
            if self.use_cache and cache_key in self._cache:
                return self._cache[cache_key]
            params = {
                "filter.term": query,
                "filter.limit": min(limit, 50),
                "filter.start": max(1, start),
                "filter.locationId": self.location_id,
            }
            data = await self._request("GET", "/products", params=params)
            products = data.get("data", [])[:limit]
            if self.use_cache:
                self._cache[cache_key] = products
            return products

        async def get_product_price(self, product_name):
            products = await self.search_products(product_name, limit=1)
            if not products:
                raise KrogerAPIError(f"No products found for '{product_name}'.")
            product = products[0]
            items = product.get("items", [])
            item = items[0] if items else {}
            fulfillment = item.get("fulfillment", {})
            inventory = item.get("inventory", {})

            def _p(block):
                return {
                    "regular": block.get("regular"),
                    "promo": block.get("promo"),
                    "regularPerUnitEstimate": block.get("regularPerUnitEstimate"),
                    "promoPerUnitEstimate": block.get("promoPerUnitEstimate"),
                }

            return {
                "productId": product.get("productId"),
                "description": product.get("description"),
                "brand": product.get("brand"),
                "size": item.get("size"),
                "soldBy": item.get("soldBy"),
                "stockLevel": inventory.get("stockLevel"),
                "price": _p(item.get("price", {})),
                "nationalPrice": _p(item.get("nationalPrice", {})),
                "fulfillment": {
                    "instore": fulfillment.get("instore"),
                    "curbside": fulfillment.get("curbside"),
                    "delivery": fulfillment.get("delivery"),
                    "shiptohome": fulfillment.get("shiptohome"),
                },
            }


logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

TEST_PRODUCTS = [
    {"label": "Organic Bananas",  "query": "organic bananas"},
    {"label": "Whole Milk",       "query": "whole milk gallon"},
    {"label": "White Bread",      "query": "white bread loaf"},
    {"label": "Chicken Breast",   "query": "boneless chicken breast"},
    {"label": "Eggs (dozen)",     "query": "large eggs dozen"},
]

_SUPPORTS_COLOR = sys.stdout.isatty() and os.name != "nt"

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _SUPPORTS_COLOR else text

def GREEN(t: str) -> str:
    return _c("32", t)


def RED(t: str) -> str:
    return _c("31", t)


def YELLOW(t: str) -> str:
    return _c("33", t)


def CYAN(t: str) -> str:
    return _c("36", t)


def BOLD(t: str) -> str:
    return _c("1", t)


def DIM(t: str) -> str:
    return _c("2", t)

BOX_W = 67

def _fmt_price(val) -> str:
    return DIM("—") if val is None else f"${float(val):.2f}"

def _fmt_bool(val) -> str:
    if val is None:
        return DIM("—")
    return GREEN("Yes") if val else DIM("No")

def _fmt_stock(val) -> str:
    if val is None:
        return DIM("—")
    if val == "HIGH":
        return GREEN("High")
    if val == "LOW":
        return YELLOW("Low")
    return RED("Out of Stock")

def _box_line(label: str, value: str, width: int = BOX_W) -> str:
    content = f"  {label:<20} {value}"
    plain = re.sub(r"\033\[[0-9;]*m", "", content)
    pad = width - len(plain) - 1
    return f"|{content}{' ' * max(pad, 0)} |"

def _print_result_card(index, total, label, result, elapsed, passed, error="", verbose=False):
    price = result.get("price", {})
    national = result.get("nationalPrice", {})
    status = GREEN("PASS") if passed else RED("FAIL")
    header = f"  {index}/{total}  {BOLD(label)}"

    print(f"\n+{'-' * BOX_W}+")
    hdr_plain = f"  {index}/{total}  {label}"
    pad = BOX_W - len(hdr_plain) - 1
    print(f"|{header}{' ' * max(pad, 0)} |")
    print(f"+{'-' * BOX_W}+")

    if passed:
        f = result.get("fulfillment", {})
        print(_box_line("Product",       str(result.get("description", "—"))))
        print(_box_line("Brand",         str(result.get("brand") or "—")))
        print(_box_line("Product ID",    str(result.get("productId", "—"))))
        print(_box_line("Size",          str(result.get("size") or "—")))
        print(_box_line("Sold By",       str(result.get("soldBy") or "—")))
        print(_box_line("Stock Level",   _fmt_stock(result.get("stockLevel"))))
        print(_box_line("Regular $",     _fmt_price(price.get("regular"))))
        print(_box_line("Promo $",       _fmt_price(price.get("promo"))))
        print(_box_line("Per Unit $",    _fmt_price(price.get("regularPerUnitEstimate"))))
        print(_box_line("National $",    _fmt_price(national.get("regular"))))
        print(_box_line("In-store",      _fmt_bool(f.get("instore"))))
        print(_box_line("Curbside",      _fmt_bool(f.get("curbside"))))
        print(_box_line("Delivery",      _fmt_bool(f.get("delivery"))))
        print(_box_line("Ship to Home",  _fmt_bool(f.get("shiptohome"))))
        print(_box_line("Elapsed",       f"{elapsed:.2f}s"))
    else:
        for i, line in enumerate((error or "Unknown error").split("\n")[:4]):
            print(_box_line("Error" if i == 0 else "", RED(line[:50])))
        print(_box_line("Elapsed", f"{elapsed:.2f}s"))

    print(_box_line("Status", status))
    print(f"+{'-' * BOX_W}+")

    if verbose and passed:
        import json
        print(DIM("  Raw payload:"))
        for line in json.dumps(result, indent=4).splitlines():
            print(DIM(f"    {line}"))


async def run_tests(client_id, client_secret, location_id, products, verbose=False):
    print(BOLD("\nKroger API Integration Test"))
    print("=" * 34)
    print(f"  Store location : {CYAN(location_id)}")
    print(f"  Timestamp      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Products       : {len(products)} to test\n")
    print("Authenticating with Kroger API...", end=" ", flush=True)

    async with KrogerService(
        client_id=client_id,
        client_secret=client_secret,
        location_id=location_id,
        use_cache=True,
    ) as svc:
        try:
            await svc._ensure_token()
            print(GREEN("Token acquired"))
        except KrogerAPIError as exc:
            print(RED("FAILED"))
            print(f"\n  {RED('Authentication failed:')} {exc}")
            print("\n  Check KROGER_CLIENT_ID and KROGER_CLIENT_SECRET.")
            print("  Register at: https://developer.kroger.com/\n")
            return 1

        passed_count = 0
        failed_count = 0
        total = len(products)
        overall_start = time.monotonic()

        for idx, product in enumerate(products, start=1):
            t0 = time.monotonic()
            result: dict = {}
            error = ""
            ok = False

            try:
                result = await svc.get_product_price(product["query"])
                ok = True
                passed_count += 1
            except KrogerRateLimitError as exc:
                error = f"Rate limited – {exc}"
                failed_count += 1
            except KrogerAPIError as exc:
                error = str(exc)
                failed_count += 1
            except Exception as exc:
                error = f"Unexpected error: {exc}"
                failed_count += 1

            _print_result_card(idx, total, product["label"], result,
                               time.monotonic() - t0, ok, error=error, verbose=verbose)

            if idx < total:
                await asyncio.sleep(0.3)

        total_time = time.monotonic() - overall_start
        print()
        summary_parts = [
            GREEN(f"{passed_count} passed"),
            (RED(f"{failed_count} failed") if failed_count else DIM("0 failed")),
        ]
        print(BOLD("Results:") + "  " + " - ".join(summary_parts) +
              f"  {DIM(f'(total time: {total_time:.2f}s)')}")

        if failed_count:
            print(f"\n  {YELLOW('!')}  {failed_count} test(s) failed.")
        else:
            print(f"\n  {GREEN('✓')}  All tests passed successfully!")

        print()
        return failed_count


def _parse_args():
    parser = argparse.ArgumentParser(description="Kroger API integration test – Jira ticket #8")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--product", "-p", metavar="QUERY")
    parser.add_argument(
        "--location",
        metavar="LOCATION_ID",
        default=os.getenv("KROGER_LOCATION_ID", "01400943"),
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    client_id = os.getenv("KROGER_CLIENT_ID", "").strip()
    client_secret = os.getenv("KROGER_CLIENT_SECRET", "").strip()

    if not client_id or not client_secret:
        print(RED("\n  Error: Missing Kroger API credentials."))
        print("      export KROGER_CLIENT_ID=\"your_client_id\"")
        print("      export KROGER_CLIENT_SECRET=\"your_client_secret\"\n")
        sys.exit(1)

    products = TEST_PRODUCTS
    if args.product:
        products = [{"label": args.product, "query": args.product}]

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    failures = asyncio.run(
        run_tests(
            client_id=client_id,
            client_secret=client_secret,
            location_id=args.location,
            products=products,
            verbose=args.verbose,
        )
    )
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
