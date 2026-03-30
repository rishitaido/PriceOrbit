"""
Backfill store-specific product prices for Sprint 3.

Usage:
    python scripts/backfill_store_prices.py
"""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

# Ensure project root is importable when running as a script.
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Some local setups store DEBUG=release, which is not parseable as a bool.
if (os.getenv("DEBUG") or "").strip().lower() == "release":
    os.environ["DEBUG"] = "False"

from app.db.session import SessionLocal
from app.models.product_model import Product
from app.models.product_store_price_model import ProductStorePrice
from app.models.store_model import Store


def _vary_price(base_price: float, rng: random.Random) -> float:
    magnitude = rng.uniform(0.05, 0.15)
    sign = -1 if rng.random() < 0.5 else 1
    varied = base_price * (1 + sign * magnitude)
    return round(max(0.01, varied), 2)


def main() -> None:
    db = SessionLocal()
    created = 0
    updated = 0

    try:
        products = db.query(Product).order_by(Product.id.asc()).all()
        stores = (
            db.query(Store)
            .filter(Store.kroger_location_id.isnot(None))
            .filter(Store.kroger_location_id != "")
            .order_by(Store.id.asc())
            .all()
        )

        if not products:
            print("No products found. Nothing to backfill.")
            return

        if not stores:
            print("No Kroger-mapped stores found. Nothing to backfill.")
            return

        existing = {
            (row.product_id, row.store_id): row
            for row in db.query(ProductStorePrice).all()
        }

        touched_products: set[int] = set()
        touched_stores: set[int] = set()

        for product in products:
            base_price = float(product.current_price or 0)
            if base_price <= 0:
                base_price = 1.99

            # Stable selection so reruns are predictable.
            product_rng = random.Random(1000 + int(product.id))
            store_count = min(5, len(stores))
            selected_store_ids = product_rng.sample([s.id for s in stores], store_count)

            for store_id in selected_store_ids:
                varied_price = _vary_price(base_price, product_rng)
                key = (product.id, store_id)

                row = existing.get(key)
                if row is None:
                    row = ProductStorePrice(
                        product_id=product.id,
                        store_id=store_id,
                        price=varied_price,
                    )
                    db.add(row)
                    existing[key] = row
                    created += 1
                else:
                    row.price = varied_price
                    updated += 1

                touched_products.add(product.id)
                touched_stores.add(store_id)

        db.commit()
        print(
            f"Created {created} new price records across "
            f"{len(touched_products)} products and {len(touched_stores)} stores"
        )
        print(f"Updated {updated} existing price records")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
