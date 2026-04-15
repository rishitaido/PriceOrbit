"""
Backfill tariff/origin/HTS/import_dependency for variant product names.

This script maps Kroger-enriched product names (brand/size variants) to the
canonical names in `data/tariff_rates.csv`, then applies metadata.
"""

from __future__ import annotations

import csv
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from sqlalchemy.orm import Session

# Ensure project root is importable when running as a script (Render/startup command).
sys.path.append(str(Path(__file__).resolve().parent.parent))

if (os.getenv("DEBUG") or "").strip().lower() == "release":
    os.environ["DEBUG"] = "False"

from app.db.session import SessionLocal
from app.models.product_model import Product


@dataclass
class MetaRow:
    canonical_name: str
    hts_code: str
    tariff_rate: float
    origin_country: str
    import_dependency: str


# High-signal substring aliases for common Kroger renamed products.
ALIAS_SUBSTRINGS: Dict[str, str] = {
    "banana peppers": "Bell Peppers",
    "gala apples": "Apples",
    "navel oranges": "Oranges",
    "strawberr": "Strawberries",
    "blueberr": "Blueberries",
    "hass avocado": "Avocados",
    "yellow onion": "Onions",
    "russet potato": "Potatoes",
    "broccoli": "Broccoli",
    "bell pepper": "Bell Peppers",
    "carrot": "Carrots",
    "lettuce": "Lettuce",
    "whole milk": "Whole Milk",
    "almond milk": "Almond Milk",
    "cheddar": "Cheddar Cheese",
    "mozzarella": "Mozzarella Cheese",
    "greek yogurt": "Greek Yogurt",
    "butter": "Butter",
    "egg": "Eggs",
    "whipping cream": "Heavy Cream",
    "heavy cream": "Heavy Cream",
    "sour cream": "Sour Cream",
    "parmesan": "Parmesan Cheese",
    "chicken breast": "Chicken Breast",
    "ground beef": "Ground Beef",
    "pork chop": "Pork Chops",
    "bacon": "Bacon",
    "salmon": "Salmon Fillet",
    "shrimp": "Shrimp",
    "tilapia": "Tilapia",
    "ground turkey": "Ground Turkey",
    "beef steak": "Beef Steak",
    "lamb chop": "Lamb Chops",
    "jasmine rice": "White Rice",
    "long grain rice": "White Rice",
    "brown rice": "Brown Rice",
    "pasta": "Pasta",
    "olive oil": "Olive Oil",
    "canola oil": "Vegetable Oil",
    "black beans": "Canned Black Beans",
    "chick peas": "Canned Chickpeas",
    "chickpeas": "Canned Chickpeas",
    "powdered sugar": "Sugar",
    "granulated sugar": "Sugar",
    "all purpose flour": "All-Purpose Flour",
    "peanut butter": "Peanut Butter",
    "frozen pizza": "Frozen Pizza",
    "frozen vegetables": "Frozen Vegetables",
    "frozen berries": "Frozen Berries",
    "ice cream": "Ice Cream",
    "chicken nuggets": "Frozen Chicken Nuggets",
    "roma tomato": "Tomatoes",
    "spinach": "Spinach",
}


def _resolve_path(raw_path: str) -> Path:
    p = Path(raw_path).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


def _norm_text(raw: str) -> str:
    text = str(raw or "").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _singularize(token: str) -> str:
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("es") and len(token) > 3:
        return token[:-2]
    if token.endswith("s") and len(token) > 3:
        return token[:-1]
    return token


def _token_set(raw: str) -> set[str]:
    return {_singularize(t) for t in _norm_text(raw).split(" ") if t}


def _load_tariff_rows(csv_path: Path) -> Dict[str, MetaRow]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Tariff CSV not found: {csv_path}")

    result: Dict[str, MetaRow] = {}
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("product_name") or row.get("name") or "").strip()
            if not name:
                continue
            key = _norm_text(name)
            try:
                tariff_rate = float((row.get("tariff_rate") or "0").strip() or 0.0)
            except ValueError:
                tariff_rate = 0.0
            result[key] = MetaRow(
                canonical_name=name,
                hts_code=(row.get("hts_code") or "").strip(),
                tariff_rate=tariff_rate,
                origin_country=(row.get("origin_country") or "").strip(),
                import_dependency=(row.get("import_dependency") or "").strip(),
            )
    return result


def _match_canonical(product_name: str, metadata_by_key: Dict[str, MetaRow]) -> Optional[MetaRow]:
    normalized = _norm_text(product_name)

    # 1) Exact normalized key.
    exact = metadata_by_key.get(normalized)
    if exact:
        return exact

    # 2) Alias substring lookup.
    for needle, canonical in ALIAS_SUBSTRINGS.items():
        if needle in normalized:
            alias_match = metadata_by_key.get(_norm_text(canonical))
            if alias_match:
                return alias_match

    # 3) Token similarity fallback.
    product_tokens = _token_set(product_name)
    if not product_tokens:
        return None

    best_score = 0.0
    best: Optional[MetaRow] = None
    for key, meta in metadata_by_key.items():
        target_tokens = _token_set(key)
        if not target_tokens:
            continue
        overlap = len(product_tokens & target_tokens)
        if overlap == 0:
            continue
        precision = overlap / len(product_tokens)
        recall = overlap / len(target_tokens)
        score = (2 * precision * recall) / (precision + recall)
        if score > best_score:
            best_score = score
            best = meta

    # Conservative threshold to avoid bad matches.
    if best_score >= 0.60:
        return best
    return None


def sync_metadata(csv_path: str = "data/tariff_rates.csv", dry_run: bool = False) -> None:
    tariff_csv = _resolve_path(csv_path)
    metadata_by_key = _load_tariff_rows(tariff_csv)

    db: Session = SessionLocal()
    updated = 0
    unmatched = 0
    untouched = 0
    unmatched_names: list[str] = []

    try:
        products = db.query(Product).order_by(Product.id.asc()).all()
        for product in products:
            match = _match_canonical(product.name, metadata_by_key)
            if not match:
                unmatched += 1
                unmatched_names.append(product.name)
                continue

            changed = False
            if match.hts_code and product.hts_code != match.hts_code:
                product.hts_code = match.hts_code
                changed = True
            if product.tariff_rate is None or float(product.tariff_rate) != float(match.tariff_rate):
                product.tariff_rate = match.tariff_rate
                changed = True
            if match.origin_country and product.origin_country != match.origin_country:
                product.origin_country = match.origin_country
                changed = True
            if match.import_dependency and product.import_dependency != match.import_dependency:
                product.import_dependency = match.import_dependency
                changed = True

            if changed:
                product.calculate_health_score()
                updated += 1
            else:
                untouched += 1

        if dry_run:
            db.rollback()
        else:
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print("Metadata sync complete")
    print(f"Updated: {updated}")
    print(f"Unchanged: {untouched}")
    print(f"Unmatched: {unmatched}")
    if unmatched_names:
        print("Unmatched product names (first 30):")
        for name in unmatched_names[:30]:
            print(f"  - {name}")
    print(f"Committed: {not dry_run}")


if __name__ == "__main__":
    sync_metadata()

