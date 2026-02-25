"""
Seed script for initial Product data.

Loads products from data/products_seed.csv into the database.
- Inserts new products
- Skips duplicates by product name
"""

import csv
from pathlib import Path
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.product_model import Product

# Resolve project root directory
BASE_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = BASE_DIR / "data" / "products_seed.csv"


def seed_products() -> None:
    db: Session = SessionLocal()
    inserted = 0
    skipped = 0

    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV file not found at {CSV_PATH}")

    with open(CSV_PATH, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            name = row["name"].strip()
            category = row["category"].strip()
            import_dependency = row["import_dependency"].strip()

            # Skip duplicate products by name
            existing = (
                db.query(Product)
                .filter(Product.name == name)
                .first()
            )

            if existing:
                skipped += 1
                continue

            product = Product(
                name=name,
                category=category,
                import_dependency=import_dependency,
            )

            db.add(product)
            inserted += 1

    db.commit()
    db.close()

    print("Product seeding complete")
    print(f"Inserted: {inserted}")
    print(f"Skipped (duplicates): {skipped}")


if __name__ == "__main__":
    seed_products()
