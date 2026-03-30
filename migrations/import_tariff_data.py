import csv
import os
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

# Some local setups store DEBUG=release, which is not parseable as a bool.
if (os.getenv("DEBUG") or "").strip().lower() == "release":
    os.environ["DEBUG"] = "False"

from app.db.session import SessionLocal
from app.models.product_model import Product


def import_tariffs(csv_path="data/tariff_rates.csv"):
    db: Session = SessionLocal()
    updated = 0
    skipped = 0

    try:
        path = Path(csv_path)
        with path.open(newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)

            for row in reader:
                product_name = (row.get("product_name") or row.get("name") or "").strip()
                if not product_name:
                    skipped += 1
                    print("  Skipped row with missing product_name")
                    continue

                product = db.query(Product).filter(Product.name == product_name).first()
                if product is None:
                    product = db.query(Product).filter(func.lower(Product.name) == product_name.lower()).first()

                if product is None:
                    skipped += 1
                    print(f"  Skipped (not in DB): {product_name}")
                    continue

                raw_tariff = (row.get("tariff_rate") or "0").strip()
                try:
                    tariff_rate = float(raw_tariff or 0)
                except ValueError:
                    tariff_rate = float(product.tariff_rate or 0)

                hts_code = (row.get("hts_code") or "").strip()
                origin_country = (row.get("origin_country") or "").strip()
                import_dependency = (row.get("import_dependency") or "").strip()

                if hts_code:
                    product.hts_code = hts_code
                product.tariff_rate = tariff_rate
                if origin_country:
                    product.origin_country = origin_country
                if import_dependency:
                    product.import_dependency = import_dependency

                product.calculate_health_score()
                updated += 1
                print(
                    f"  Updated: {product_name} "
                    f"(tariff={product.tariff_rate}%, origin={product.origin_country}, dependency={product.import_dependency})"
                )

        db.commit()
        print(f"\nDone. Updated: {updated}, Skipped: {skipped}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import_tariffs()
