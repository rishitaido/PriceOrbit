"""
Remove products whose names are exactly the base seed names.

Useful when `seed_products.py` was re-run after products were enriched/renamed,
which can re-introduce generic rows like "Eggs" and "Strawberries".
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

from sqlalchemy.orm import Session

# Ensure project root is importable when running as a script (e.g., Render startup command).
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Some setups use DEBUG=release, which is not parseable as bool for Settings.
if (os.getenv("DEBUG") or "").strip().lower() == "release":
    os.environ["DEBUG"] = "False"

from app.db.session import SessionLocal
from app.models.product_model import Product


def _norm(value: str) -> str:
    return (value or "").strip().lower()


def _resolve_csv_path(raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate


def _load_base_names(csv_path: Path) -> set[str]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or "name" not in reader.fieldnames:
            raise ValueError("CSV must include a 'name' column.")
        return {_norm(row.get("name", "")) for row in reader if _norm(row.get("name", ""))}


def remove_base_seed_products(csv_path: str, apply: bool) -> None:
    resolved = _resolve_csv_path(csv_path)
    base_names = _load_base_names(resolved)

    db: Session = SessionLocal()
    try:
        candidates = (
            db.query(Product)
            .order_by(Product.id.asc())
            .all()
        )
        to_remove = [p for p in candidates if _norm(p.name) in base_names]

        print(f"Total products in DB: {len(candidates)}")
        print(f"Base-name products found: {len(to_remove)}")
        for product in to_remove[:25]:
            print(f"  - id={product.id} name={product.name}")
        if len(to_remove) > 25:
            print(f"  ... and {len(to_remove) - 25} more")

        if not apply:
            print("Dry run only. Re-run with --apply to delete these rows.")
            return

        for product in to_remove:
            db.delete(product)
        db.commit()
        print(f"Deleted {len(to_remove)} base-name products.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove products whose names exactly match entries in data/products_seed.csv."
    )
    parser.add_argument(
        "--csv",
        default="data/products_seed.csv",
        help="Path to base seed CSV (default: data/products_seed.csv).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete rows. Without this flag, script runs in dry-run mode.",
    )
    args = parser.parse_args()
    remove_base_seed_products(csv_path=args.csv, apply=args.apply)


if __name__ == "__main__":
    main()

