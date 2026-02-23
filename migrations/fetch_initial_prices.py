"""
Fetch initial price data for all mapped products from Kroger API.

Acceptance Criteria:
- Fetches prices for all products with kroger_product_id
- Updates product.current_price
- Adds initial entry to product.price_history
- Updates product.last_price_check timestamp
- Handles unavailable products
- Respects rate limits (batch size = 10)
- Detailed logging
- Summary report
- Incremental mode (only products with no current_price)
"""

import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from statistics import mean

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.product import Product
from app.services.kroger_service import KrogerService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)

logger = logging.getLogger(__name__)


BATCH_SIZE = 10


async def fetch_single_product(product: Product, kroger: KrogerService):
    """
    Fetch price for a single product and return structured result.
    """
    try:
        response = await kroger.get_product_by_id(product.kroger_product_id)

        logger.debug("Kroger response for %s: %s", product.name, response)

        items = response.get("items", [])
        if not items:
            return ("unavailable", None)

        price_block = items[0].get("price", {})
        price_value = price_block.get("regular")

        if price_value is None:
            return ("unavailable", None)

        return ("success", Decimal(str(price_value)))

    except Exception as e:
        logger.error("Error fetching %s: %s", product.name, e)
        return ("error", None)


async def fetch_initial_prices():
    print("Fetching prices from Kroger API...")

    db = SessionLocal()

    kroger = KrogerService(
        client_id=settings.KROGER_CLIENT_ID,
        client_secret=settings.KROGER_CLIENT_SECRET
    )

    try:
        # Incremental mode
        products = (
            db.query(Product)
            .filter(Product.kroger_product_id.isnot(None))
            .filter(Product.current_price.is_(None))
            .all()
        )

        total = len(products)

        if total == 0:
            print("No products require initial pricing.")
            return

        prices_fetched = 0
        unavailable_count = 0
        api_calls = 0
        collected_prices = []

        for i in range(0, total, BATCH_SIZE):
            batch = products[i:i + BATCH_SIZE]

            tasks = [
                fetch_single_product(product, kroger)
                for product in batch
            ]

            results = await asyncio.gather(*tasks)

            for idx, (product, result) in enumerate(zip(batch, results)):
                api_calls += 1
                status, price = result
                current_index = i + idx + 1

                product.last_price_check = datetime.utcnow()

                if status == "success":
                    product.current_price = price
                    product.add_price_to_history(price)
                    prices_fetched += 1
                    collected_prices.append(float(price))

                    print(f"[{current_index}/{total}] {product.name}: ${price} ✅")

                elif status == "unavailable":
                    product.current_price = None
                    unavailable_count += 1
                    print(f"[{current_index}/{total}] {product.name}: Price unavailable")

                else:
                    print(f"[{current_index}/{total}] {product.name}: ERROR fetching price")

            # Commit every batch
            db.commit()
            logger.info("Committed batch ending at product %s", i + len(batch))

        # Summary
        print("\nSummary:")
        print(f"- Prices fetched: {prices_fetched}/{total}")
        print(f"- Unavailable: {unavailable_count}")

        if collected_prices:
            avg_price = round(mean(collected_prices), 2)
            print(f"- Average price: ${avg_price}")
        else:
            print("- Average price: N/A")

        print(f"- Total API calls: {api_calls}")

    finally:
        await kroger.aclose()
        db.close()


if __name__ == "__main__":
    asyncio.run(fetch_initial_prices())