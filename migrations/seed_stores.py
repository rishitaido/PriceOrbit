"""
Seed script for Kroger store locations.

Fetches 10-20 Kroger stores near Atlanta, GA via the Kroger API
and inserts them into the database.
- Inserts new stores
- Skips duplicates by kroger_location_id
"""

import asyncio
import json
import logging
from sqlalchemy.orm import Session

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
            radius=SEED_RADIUS,
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
    skipped = 0

    try:
        for store_data in stores_data:
            location_id = store_data.get("location_id")
            address_block = store_data.get("address", {})
            geo_block = store_data.get("geolocation", {})

            # Skip stores missing required fields
            lat = geo_block.get("lat")
            lng = geo_block.get("lng")
            address = address_block.get("line1")
            city = address_block.get("city")
            state = address_block.get("state")
            zip_code = address_block.get("zip_code")

            if not all([lat, lng, address, city, state, zip_code]):
                logger.warning(
                    "Skipping store '%s' - missing required fields.", store_data.get("name")
                )
                skipped += 1
                continue

            # Skip duplicates by kroger_location_id
            if location_id:
                existing = (
                    db.query(Store)
                    .filter(Store.kroger_location_id == location_id)
                    .first()
                )
                if existing:
                    logger.debug("Skipping duplicate store: %s", location_id)
                    skipped += 1
                    continue

            # Serialize hours dict to JSON string for Text column
            hours_raw = store_data.get("hours")
            hours_str = json.dumps(hours_raw) if hours_raw else None

            store = Store(
                name=store_data.get("name", "Kroger"),
                address=address,
                city=city,
                state=state,
                zip_code=zip_code,
                kroger_location_id=location_id,
                latitude=lat,
                longitude=lng,
                phone=store_data.get("phone"),
                hours=hours_str,
            )

            db.add(store)
            inserted += 1

        db.commit()

    except Exception as exc:
        db.rollback()
        logger.error("Seeding failed: %s", exc)
        raise
    finally:
        db.close()

    print("Store seeding complete")
    print(f"Inserted: {inserted}")
    print(f"Skipped (duplicates or incomplete): {skipped}")


if __name__ == "__main__":
    seed_stores()
