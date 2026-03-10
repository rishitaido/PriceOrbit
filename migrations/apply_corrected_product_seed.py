"""
Apply corrected product seed data to existing products and recalculate health scores.

This script updates existing rows by product name using:
- category
- import_dependency
- origin_country
- hts_code
- tariff_rate

It can optionally create missing products from the CSV.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.product_model import Product


@dataclass
class UpdateSummary:
    """Execution counters for script output."""

    total_rows: int = 0
    updated: int = 0
    created: int = 0
    unchanged: int = 0
    missing: int = 0
    recalculated: int = 0


REQUIRED_COLUMNS = {
    "name",
    "category",
    "import_dependency",
    "origin_country",
    "hts_code",
    "tariff_rate",
}


def _resolve_csv_path(raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate


def _load_rows(csv_path: Path) -> List[Dict[str, str]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV is missing header row.")

        missing_columns = REQUIRED_COLUMNS.difference(set(reader.fieldnames))
        if missing_columns:
            raise ValueError(
                f"CSV is missing required columns: {', '.join(sorted(missing_columns))}"
            )
        return list(reader)


def _parse_tariff_rate(raw_value: str, product_name: str) -> Decimal:
    try:
        value = Decimal(str(raw_value).strip())
    except (InvalidOperation, AttributeError):
        raise ValueError(
            f"Invalid tariff_rate '{raw_value}' for product '{product_name}'."
        ) from None

    if value < 0 or value > 100:
        raise ValueError(
            f"Out-of-range tariff_rate '{raw_value}' for product '{product_name}'. "
            "Expected 0..100."
        )

    return value.quantize(Decimal("0.01"))


def _normalize_text(raw: str) -> str:
    return str(raw or "").strip()


def _find_by_name(db: Session, name: str) -> Product | None:
    return (
        db.query(Product)
        .filter(func.lower(Product.name) == name.lower())
        .first()
    )


def _apply_row_to_product(product: Product, row: Dict[str, str]) -> bool:
    """
    Apply CSV values to a product.

    Returns:
        bool: True when any tracked field changed.
    """
    new_category = _normalize_text(row["category"])
    new_dependency = _normalize_text(row["import_dependency"])
    new_origin = _normalize_text(row["origin_country"]) or None
    new_hts = _normalize_text(row["hts_code"]) or None
    new_tariff = _parse_tariff_rate(row["tariff_rate"], row["name"])

    changed = False
    if product.category != new_category:
        product.category = new_category
        changed = True
    if product.import_dependency != new_dependency:
        product.import_dependency = new_dependency
        changed = True
    if product.origin_country != new_origin:
        product.origin_country = new_origin
        changed = True
    if product.hts_code != new_hts:
        product.hts_code = new_hts
        changed = True
    if (product.tariff_rate or Decimal("0.00")) != new_tariff:
        product.tariff_rate = new_tariff
        changed = True

    return changed


def apply_corrected_seed(
    csv_path: str,
    create_missing: bool = False,
    dry_run: bool = False,
) -> UpdateSummary:
    db: Session = SessionLocal()
    summary = UpdateSummary()

    resolved_csv_path = _resolve_csv_path(csv_path)
    rows = _load_rows(resolved_csv_path)
    summary.total_rows = len(rows)

    try:
        for row in rows:
            name = _normalize_text(row["name"])
            if not name:
                raise ValueError("Encountered empty product name in CSV.")

            product = _find_by_name(db, name)
            if product is None:
                if not create_missing:
                    summary.missing += 1
                    continue

                product = Product(
                    name=name,
                    retailer="Kroger",
                )
                db.add(product)
                db.flush()
                summary.created += 1

            changed = _apply_row_to_product(product, row)
            if changed:
                summary.updated += 1
            else:
                summary.unchanged += 1

            product.calculate_health_score()
            summary.recalculated += 1

        if dry_run:
            db.rollback()
        else:
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply data/products_seed_corrected.csv to products and recalculate health scores."
    )
    parser.add_argument(
        "--csv",
        default="data/products_seed_corrected.csv",
        help="Path to corrected product CSV (default: data/products_seed_corrected.csv).",
    )
    parser.add_argument(
        "--create-missing",
        action="store_true",
        help="Create products present in CSV but missing in DB.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and compute updates, but rollback instead of commit.",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    summary = apply_corrected_seed(
        csv_path=args.csv,
        create_missing=args.create_missing,
        dry_run=args.dry_run,
    )

    print("Corrected product seed apply complete")
    print(f"CSV rows: {summary.total_rows}")
    print(f"Updated: {summary.updated}")
    print(f"Created: {summary.created}")
    print(f"Unchanged: {summary.unchanged}")
    print(f"Missing (not created): {summary.missing}")
    print(f"Health scores recalculated: {summary.recalculated}")
    print(f"Committed: {not args.dry_run}")


if __name__ == "__main__":
    main()
