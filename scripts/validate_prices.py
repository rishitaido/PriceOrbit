"""
Validate and repair product prices for Sprint 3 data quality targets.

Usage:
    python scripts/validate_prices.py
"""

from __future__ import annotations

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


CATEGORY_RANGES = {
    "Fresh Produce": (0.50, 8.00),
    "Dairy & Eggs": (1.00, 12.00),
    "Meat & Seafood": (3.00, 25.00),
    "Pantry Staples": (1.00, 15.00),
    "Frozen Foods": (2.00, 15.00),
}

DEFAULT_PRICES = {
    "Bananas": 0.69,
    "Apples": 1.99,
    "Oranges": 1.49,
    "Strawberries": 3.99,
    "Blueberries": 4.49,
    "Avocados": 1.50,
    "Tomatoes": 1.79,
    "Onions": 1.29,
    "Potatoes": 0.99,
    "Spinach": 2.49,
    "Broccoli": 1.99,
    "Bell Peppers": 1.29,
    "Carrots": 1.49,
    "Lettuce": 1.99,
    "Garlic": 0.79,
    "Whole Milk": 3.69,
    "Almond Milk": 3.49,
    "Cheddar Cheese": 3.99,
    "Mozzarella Cheese": 3.49,
    "Greek Yogurt": 5.49,
    "Butter": 4.49,
    "Eggs": 3.99,
    "Heavy Cream": 4.29,
    "Sour Cream": 2.49,
    "Parmesan Cheese": 6.99,
    "Chicken Breast": 8.99,
    "Ground Beef": 5.99,
    "Pork Chops": 4.99,
    "Bacon": 6.99,
    "Salmon Fillet": 9.99,
    "Shrimp": 8.99,
    "Tilapia": 6.99,
    "Ground Turkey": 5.49,
    "Beef Steak": 12.99,
    "Lamb Chops": 14.99,
    "White Rice": 3.49,
    "Brown Rice": 3.99,
    "Pasta": 1.49,
    "Olive Oil": 7.99,
    "Vegetable Oil": 3.99,
    "Canned Black Beans": 1.19,
    "Canned Chickpeas": 1.29,
    "Sugar": 3.49,
    "All-Purpose Flour": 3.99,
    "Peanut Butter": 3.49,
    "Frozen Pizza": 5.99,
    "Frozen Vegetables": 2.49,
    "Frozen Berries": 3.99,
    "Ice Cream": 5.49,
    "Frozen Chicken Nuggets": 7.99,
}


def _is_suspicious_tariff_gap(product: Product) -> bool:
    tariff_rate = float(product.tariff_rate or 0)
    dependency = (product.import_dependency or "").strip().lower()
    origin = (product.origin_country or "").strip().lower()
    return tariff_rate == 0 and dependency == "high" and origin != "united states"


def main() -> None:
    db = SessionLocal()
    try:
        products = db.query(Product).order_by(Product.id.asc()).all()
        total = len(products)

        fixed_null_or_zero = 0
        out_of_range = 0
        suspicious_tariff_gaps = 0
        valid_prices = 0

        for product in products:
            category = (product.category or "").strip()
            min_price, max_price = CATEGORY_RANGES.get(category, (0.50, 25.00))
            current = None if product.current_price is None else float(product.current_price)

            if current is None or current <= 0:
                default_price = DEFAULT_PRICES.get(product.name, round((min_price + max_price) / 2, 2))
                product.current_price = default_price
                current = float(default_price)
                fixed_null_or_zero += 1

            if current < min_price or current > max_price:
                out_of_range += 1

            if _is_suspicious_tariff_gap(product):
                suspicious_tariff_gaps += 1

            if current > 0 and min_price <= current <= max_price:
                valid_prices += 1

        db.commit()

        with_nonzero_tariff = sum(1 for p in products if float(p.tariff_rate or 0) > 0)
        with_hts = sum(1 for p in products if (p.hts_code or "").strip())
        with_origin = sum(1 for p in products if (p.origin_country or "").strip())
        with_dependency = sum(
            1
            for p in products
            if (p.import_dependency or "").strip() and (p.import_dependency or "").strip().lower() != "unknown"
        )

        print("=== PRICE VALIDATION REPORT ===")
        print(f"Products with valid prices: {valid_prices}/{total}")
        print(f"Products with NULL prices (fixed): {fixed_null_or_zero}")
        print(f"Products with out-of-range prices: {out_of_range}")
        print(f"Products with suspicious tariff gaps: {suspicious_tariff_gaps}")
        print()
        print("=== TARIFF COVERAGE REPORT ===")
        print(f"Products with non-zero tariff: {with_nonzero_tariff}/{total}")
        print(f"Products with HTS code: {with_hts}/{total}")
        print(f"Products with origin country: {with_origin}/{total}")
        print(f"Products with import dependency set: {with_dependency}/{total}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
