"""
Rebuild price_history so points come only from live Kroger fetches.

Important:
- Kroger API in this project provides current price, not historical daily series.
- This script can clear existing synthetic history and repopulate one live
  Kroger point per product per run.

Usage:
    python scripts/rebuild_kroger_only_history.py --clear-existing
    python scripts/rebuild_kroger_only_history.py --clear-existing --limit 20 --delay-seconds 1.5
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Ensure project root is importable when running as a script.
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Some local setups store DEBUG=release, which is not parseable as a bool.
if (os.getenv("DEBUG") or "").strip().lower() == "release":
    os.environ["DEBUG"] = "False"

from app.db.session import SessionLocal
from app.models.product_model import Product
from app.services.product_service import ProductService


async def run(clear_existing: bool, limit: int, delay_seconds: float) -> None:
    db = SessionLocal()
    processed = 0
    updated = 0
    failed = 0
    cleared = 0

    try:
        products = db.query(Product).order_by(Product.id.asc()).limit(limit).all()
        if not products:
            print("No products found. Nothing to rebuild.")
            return

        service = ProductService(db)

        for index, product in enumerate(products):
            processed += 1

            if clear_existing:
                product.price_history = []
                db.commit()
                cleared += 1

            try:
                await service.update_price_from_kroger(product.id)
                refreshed = service.get_product_by_id(product.id)
                refreshed.price_history = [
                    entry
                    for entry in (refreshed.price_history or [])
                    if str((entry or {}).get("source") or "").strip().lower() == "kroger_api"
                ]
                db.commit()
                updated += 1
                print(f"[{processed}/{len(products)}] {product.name}: OK")
            except Exception as exc:
                db.rollback()
                failed += 1
                print(f"[{processed}/{len(products)}] {product.name}: ERROR -> {exc}")

            if index < len(products) - 1 and delay_seconds > 0:
                await asyncio.sleep(delay_seconds)

        print("\nKroger-only history rebuild complete")
        print(f"Processed: {processed}")
        print(f"Updated: {updated}")
        print(f"Failed: {failed}")
        print(f"Histories cleared first: {cleared}")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild product history using Kroger-only points.")
    parser.add_argument(
        "--clear-existing",
        action="store_true",
        help="Clear existing history before fetching fresh Kroger points.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Maximum number of products to process (default: 1000).",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=1.0,
        help="Delay between products to reduce API pressure (default: 1.0).",
    )
    args = parser.parse_args()

    if args.limit < 1:
        raise ValueError("--limit must be >= 1")
    if args.delay_seconds < 0:
        raise ValueError("--delay-seconds must be >= 0")

    asyncio.run(run(args.clear_existing, args.limit, args.delay_seconds))


if __name__ == "__main__":
    main()
