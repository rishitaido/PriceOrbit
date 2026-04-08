"""
Backfill daily price-history points so 30-day charts have data.

Usage:
    python scripts/backfill_price_history.py
    python scripts/backfill_price_history.py --days 30
    python scripts/backfill_price_history.py --days 45 --overwrite
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Ensure project root is importable when running as a script.
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Some local setups store DEBUG=release, which is not parseable as a bool.
if (os.getenv("DEBUG") or "").strip().lower() == "release":
    os.environ["DEBUG"] = "False"

from app.db.session import SessionLocal
from app.models.product_model import Product
from app.services.price_history_service import PriceHistoryService


CATEGORY_BASE_FALLBACKS = {
    "Fresh Produce": 2.49,
    "Dairy & Eggs": 4.49,
    "Meat & Seafood": 9.99,
    "Pantry Staples": 4.99,
    "Frozen Foods": 5.49,
}


def _seed_price(product: Product) -> float:
    current = float(product.current_price or 0)
    if current > 0:
        return round(current, 2)
    return CATEGORY_BASE_FALLBACKS.get(product.category, 4.99)


def _build_missing_series(
    product: Product,
    *,
    days: int,
    overwrite: bool,
    max_daily_pct_move: float = 0.035,
    max_total_drift: float = 0.25,
) -> list[dict[str, Any]]:
    today = date.today()
    existing = product.price_history or []
    existing_by_day: dict[str, dict[str, Any]] = {}
    for entry in existing:
        raw_date = str((entry or {}).get("date") or "")
        day_key = raw_date.split("T")[0]
        if day_key:
            existing_by_day[day_key] = entry

    base = _seed_price(product)
    rng = random.Random((product.id or 0) * 1009 + days)

    oldest_day = today - timedelta(days=max(days - 1, 0))
    walk_value = base * (1 + rng.uniform(-0.06, 0.06))
    floor = max(0.01, base * (1 - max_total_drift))
    ceiling = max(floor + 0.01, base * (1 + max_total_drift))

    generated_by_day: dict[str, dict[str, Any]] = {}
    current_day = oldest_day
    while current_day <= today:
        day_key = current_day.isoformat()
        walk_value *= 1 + rng.uniform(-max_daily_pct_move, max_daily_pct_move)
        walk_value = min(max(walk_value, floor), ceiling)
        generated_by_day[day_key] = {
            "date": datetime.combine(
                current_day,
                datetime.min.time(),
                tzinfo=timezone.utc,
            ).isoformat(),
            "price": round(max(0.01, walk_value), 2),
            "source": "synthetic_backfill",
        }
        current_day += timedelta(days=1)

    if product.current_price is not None:
        today_key = today.isoformat()
        generated_by_day[today_key] = {
            "date": datetime.now(timezone.utc).isoformat(),
            "price": round(float(product.current_price), 2),
            "source": "synthetic_backfill",
        }

    merged = dict(existing_by_day)
    for day_key, entry in generated_by_day.items():
        if overwrite or day_key not in merged:
            merged[day_key] = entry

    merged_rows = sorted(
        merged.values(),
        key=lambda item: str((item or {}).get("date") or ""),
        reverse=True,
    )
    return PriceHistoryService.clean_old_history(merged_rows, max_days=365)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill product price history.")
    parser.add_argument("--days", type=int, default=30, help="Number of days to backfill (default: 30).")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing entries in the backfill date window.",
    )
    args = parser.parse_args()

    if args.days < 1:
        raise ValueError("--days must be >= 1")
    if args.days > 365:
        raise ValueError("--days must be <= 365")

    db = SessionLocal()
    try:
        products = db.query(Product).order_by(Product.id.asc()).all()
        if not products:
            print("No products found. Nothing to backfill.")
            return

        updated_products = 0
        added_points = 0
        overwritten_points = 0
        today = date.today()
        window_start = today - timedelta(days=args.days - 1)

        for product in products:
            before = product.price_history or []
            before_by_day = {
                str((entry or {}).get("date") or "").split("T")[0]: entry
                for entry in before
                if str((entry or {}).get("date") or "").split("T")[0]
            }

            product.price_history = _build_missing_series(
                product,
                days=args.days,
                overwrite=args.overwrite,
            )
            product.updated_at = datetime.now(timezone.utc)

            after = product.price_history or []
            after_by_day = {
                str((entry or {}).get("date") or "").split("T")[0]: entry
                for entry in after
                if str((entry or {}).get("date") or "").split("T")[0]
            }

            product_added = 0
            product_overwritten = 0
            day_cursor = window_start
            while day_cursor <= today:
                day_key = day_cursor.isoformat()
                before_entry = before_by_day.get(day_key)
                after_entry = after_by_day.get(day_key)
                if after_entry is None:
                    day_cursor += timedelta(days=1)
                    continue
                if before_entry is None:
                    product_added += 1
                elif args.overwrite and before_entry != after_entry:
                    product_overwritten += 1
                day_cursor += timedelta(days=1)

            if product_added > 0 or product_overwritten > 0:
                updated_products += 1
                added_points += product_added
                overwritten_points += product_overwritten
                product.calculate_health_score()

        db.commit()
        print(f"Products touched: {updated_products}/{len(products)}")
        print(f"Price points added: {added_points}")
        print(f"Price points overwritten: {overwritten_points}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
