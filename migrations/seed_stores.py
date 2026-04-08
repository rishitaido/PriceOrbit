"""
Seed script for Kroger store locations.

Fetches 10-20 Kroger stores near Atlanta, GA via the Kroger API
and inserts them into the database.
- Inserts new stores
- Skips duplicates by kroger_location_id
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

# Ensure project root is importable when running as a script.
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Some local setups store DEBUG=release, which is not parseable as a bool.
if (os.getenv("DEBUG") or "").strip().lower() == "release":
    os.environ["DEBUG"] = "False"

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.store_model import Store
from app.services.kroger_service import KrogerService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test area: Atlanta, GA
SEED_ZIP_CODE = "30303"
SEED_LIMIT = 20
SEED_RADIUS = 15  # miles


async def fetch_stores() -> list[dict]:
    async with KrogerService(
        client_id=settings.KROGER_CLIENT_ID,
        client_secret=settings.KROGER_CLIENT_SECRET,
    ) as kroger:
        return await kroger.search_stores(
            SEED_ZIP_CODE,
            limit=SEED_LIMIT,
            radius_miles=SEED_RADIUS,
        )


def seed_stores() -> None:
    logger.info("Fetching Kroger stores near Atlanta, GA (ZIP %s)...", SEED_ZIP_CODE)
    stores_data = asyncio.run(fetch_stores())

    if not stores_data:
        logger.warning("No stores returned from Kroger API. Exiting.")
        return

    logger.info("Fetched %d stores from API. Seeding database...", len(stores_data))

    db: Session = SessionLocal()
    inserted = 0
    updated = 0
    skipped = 0

    try:
        for store_data in stores_data:
            location_id = store_data.get("kroger_location_id")
            address = (store_data.get("address") or "").strip()
            city = (store_data.get("city") or "").strip()
            state = (store_data.get("state") or "").strip()
            zip_code = (store_data.get("zip_code") or "").strip()
            lat = store_data.get("latitude")
            lng = store_data.get("longitude")

            if (
                lat is None
                or lng is None
                or not address
                or not city
                or not state
                or not zip_code
            ):
                logger.warning(
                    "Skipping store '%s' - missing required fields.", store_data.get("name")
                )
                skipped += 1
                continue

            # Upsert by kroger_location_id when present.
            existing: Optional[Store] = None
            if location_id:
                existing = (
                    db.query(Store)
                    .filter(Store.kroger_location_id == location_id)
                    .first()
                )
            else:
                # Fallback for entries with missing location ID.
                existing = (
                    db.query(Store)
                    .filter(Store.name == (store_data.get("name") or "Kroger"))
                    .filter(Store.address == address)
                    .filter(Store.zip_code == zip_code)
                    .first()
                )

            hours_raw = store_data.get("hours")
            if isinstance(hours_raw, str) or hours_raw is None:
                hours_str = hours_raw
            else:
                hours_str = json.dumps(hours_raw, separators=(",", ":"), sort_keys=True)

            name = (store_data.get("name") or "Kroger").strip() or "Kroger"
            phone = (store_data.get("phone") or "").strip() or None

            if existing is None:
                store = Store(
                    name=name,
                    address=address,
                    city=city,
                    state=state[:2],
                    zip_code=zip_code[:10],
                    kroger_location_id=location_id,
                    latitude=float(lat),
                    longitude=float(lng),
                    phone=phone,
                    hours=hours_str,
                )
                db.add(store)
                inserted += 1
            else:
                existing.name = name
                existing.address = address
                existing.city = city
                existing.state = state[:2]
                existing.zip_code = zip_code[:10]
                existing.latitude = float(lat)
                existing.longitude = float(lng)
                existing.phone = phone
                existing.hours = hours_str
                if location_id:
                    existing.kroger_location_id = location_id
                updated += 1

        db.commit()

    except Exception as exc:
        db.rollback()
        logger.error("Seeding failed: %s", exc)
        raise
    finally:
        db.close()

    print("Store seeding complete")
    print(f"Inserted: {inserted}")
    print(f"Updated: {updated}")
    print(f"Skipped (incomplete): {skipped}")


if __name__ == "__main__":
    seed_stores()
