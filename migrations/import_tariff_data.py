import csv
import os
import re
import sys
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

# Ensure project root is importable when running as a script (e.g., Render startup command).
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Some local setups store DEBUG=release, which is not parseable as a bool.
if (os.getenv("DEBUG") or "").strip().lower() == "release":
    os.environ["DEBUG"] = "False"

from app.db.session import SessionLocal
from app.models.product_model import Product


def _normalize_name_key(raw: str) -> str:
    value = str(raw or "").lower()
    value = re.sub(r"[^a-z0-9 ]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _token_set(raw: str) -> set[str]:
    key = _normalize_name_key(raw)
    return {token for token in key.split(" ") if token}


def _find_matches_by_name(db: Session, name: str) -> list[Product]:
    exact = db.query(Product).filter(func.lower(Product.name) == name.lower()).all()
    if exact:
        return exact

    target_key = _normalize_name_key(name)
    all_products = db.query(Product).all()

    normalized_exact = [
        product for product in all_products if _normalize_name_key(product.name) == target_key
    ]
    if normalized_exact:
        return normalized_exact

    target_tokens = _token_set(name)
    if not target_tokens:
        return []

    token_matches: list[Product] = []
    for product in all_products:
        if target_tokens.issubset(_token_set(product.name)):
            token_matches.append(product)
    return token_matches


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

                matches = _find_matches_by_name(db, product_name)
                if not matches:
                    skipped += 1
                    print(f"  Skipped (not in DB): {product_name}")
                    continue

                raw_tariff = (row.get("tariff_rate") or "0").strip()
                hts_code = (row.get("hts_code") or "").strip()
                origin_country = (row.get("origin_country") or "").strip()
                import_dependency = (row.get("import_dependency") or "").strip()

                for product in matches:
                    try:
                        tariff_rate = float(raw_tariff or 0)
                    except ValueError:
                        tariff_rate = float(product.tariff_rate or 0)

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
                        f"  Updated: {product.name} "
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
