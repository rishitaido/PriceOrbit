"""
Product Store Price Service - PriceOrbit.

Fetches location-specific product prices from the Kroger API
and persists them to the ProductStorePrice table.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ExternalAPIError, NotFoundError, ValidationError
from app.models.product_model import Product
from app.models.product_store_price_model import ProductStorePrice
from app.models.store_model import Store
from app.services.kroger_service import KrogerAPIError, KrogerService

logger = logging.getLogger(__name__)


class ProductStorePriceService:
    """Handles fetching and persisting location-specific product prices."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_product_or_raise(self, product_id: int) -> Product:
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise NotFoundError(f"Product with id={product_id} not found.")
        return product

    def _get_store_or_raise(self, store_id: int) -> Store:
        store = self.db.query(Store).filter(Store.id == store_id).first()
        if not store:
            raise NotFoundError(f"Store with id={store_id} not found.")
        return store

    def _upsert_store_price(
        self,
        product_id: int,
        store_id: int,
        price: Decimal,
    ) -> ProductStorePrice:
        """Insert or update the ProductStorePrice row for a product/store pair."""
        record = (
            self.db.query(ProductStorePrice)
            .filter(
                ProductStorePrice.product_id == product_id,
                ProductStorePrice.store_id == store_id,
            )
            .first()
        )

        if record:
            record.price = price
            logger.debug(
                "Updated ProductStorePrice product_id=%s store_id=%s price=%s",
                product_id,
                store_id,
                price,
            )
        else:
            record = ProductStorePrice(
                product_id=product_id,
                store_id=store_id,
                price=price,
            )
            self.db.add(record)
            logger.debug(
                "Inserted ProductStorePrice product_id=%s store_id=%s price=%s",
                product_id,
                store_id,
                price,
            )

        try:
            self.db.commit()
            self.db.refresh(record)
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise ValidationError(
                f"Failed to save price for product_id={product_id}, store_id={store_id}."
            ) from exc

        return record

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    async def fetch_and_save_price(
        self,
        product_id: int,
        store_id: int,
    ) -> Dict[str, Any]:
        """Fetch the Kroger price for a product at a specific store and save it.

        Args:
            product_id: Internal DB product ID.
            store_id: Internal DB store ID.

        Returns:
            dict with product_id, store_id, store_name, kroger_location_id,
            regular_price, promo_price, and record id.
        """
        product = self._get_product_or_raise(product_id)
        store = self._get_store_or_raise(store_id)

        if not product.kroger_product_id:
            raise ValidationError(
                f"Product id={product_id} has no kroger_product_id set. "
                "Run the Kroger product mapping step first."
            )

        if not store.kroger_location_id:
            raise ValidationError(
                f"Store id={store_id} has no kroger_location_id set."
            )

        try:
            async with KrogerService(
                client_id=settings.KROGER_CLIENT_ID,
                client_secret=settings.KROGER_CLIENT_SECRET,
                location_id=store.kroger_location_id,
            ) as kroger:
                price_data = await kroger.get_product_price_by_location(
                    product.kroger_product_id,
                    location_id=store.kroger_location_id,
                )
        except KrogerAPIError as exc:
            raise ExternalAPIError("Kroger", str(exc)) from exc

        regular_price = price_data.get("regular_price")
        if regular_price is None:
            raise ExternalAPIError(
                "Kroger",
                f"No price returned for product={product.kroger_product_id} "
                f"at location={store.kroger_location_id}.",
            )

        record = self._upsert_store_price(
            product_id=product_id,
            store_id=store_id,
            price=Decimal(str(regular_price)),
        )

        logger.info(
            "Saved price product_id=%s store_id=%s price=%s",
            product_id,
            store_id,
            record.price,
        )

        return {
            "id": record.id,
            "product_id": product_id,
            "product_name": product.name,
            "store_id": store_id,
            "store_name": store.name,
            "kroger_location_id": store.kroger_location_id,
            "regular_price": float(record.price),
            "promo_price": price_data.get("promo_price"),
            "last_updated": record.last_updated,
        }

    async def fetch_and_save_prices_for_all_stores(
        self,
        product_id: int,
    ) -> Dict[str, Any]:
        """Fetch and save prices for a product across all stores that have
        a kroger_location_id set.

        Args:
            product_id: Internal DB product ID.

        Returns:
            Summary dict with results and errors per store.
        """
        product = self._get_product_or_raise(product_id)

        if not product.kroger_product_id:
            raise ValidationError(
                f"Product id={product_id} has no kroger_product_id set."
            )

        stores: List[Store] = (
            self.db.query(Store)
            .filter(Store.kroger_location_id.isnot(None))
            .all()
        )

        if not stores:
            return {
                "product_id": product_id,
                "processed": 0,
                "saved": 0,
                "failed": 0,
                "results": [],
                "errors": [],
            }

        results = []
        errors = []

        async with KrogerService(
            client_id=settings.KROGER_CLIENT_ID,
            client_secret=settings.KROGER_CLIENT_SECRET,
        ) as kroger:
            for store in stores:
                try:
                    price_data = await kroger.get_product_price_by_location(
                        product.kroger_product_id,
                        location_id=store.kroger_location_id,
                    )
                    regular_price = price_data.get("regular_price")
                    if regular_price is None:
                        raise ExternalAPIError(
                            "Kroger", "No price in API response."
                        )

                    record = self._upsert_store_price(
                        product_id=product_id,
                        store_id=store.id,
                        price=Decimal(str(regular_price)),
                    )
                    results.append({
                        "store_id": store.id,
                        "store_name": store.name,
                        "kroger_location_id": store.kroger_location_id,
                        "regular_price": float(record.price),
                        "promo_price": price_data.get("promo_price"),
                        "last_updated": record.last_updated,
                    })
                except (KrogerAPIError, ExternalAPIError, ValidationError) as exc:
                    errors.append({
                        "store_id": store.id,
                        "store_name": store.name,
                        "detail": str(exc),
                    })
                    logger.warning(
                        "Failed to fetch price for product_id=%s store_id=%s: %s",
                        product_id,
                        store.id,
                        exc,
                    )

        return {
            "product_id": product_id,
            "product_name": product.name,
            "processed": len(stores),
            "saved": len(results),
            "failed": len(errors),
            "results": results,
            "errors": errors,
        }

    def get_prices_for_product(self, product_id: int) -> List[Dict[str, Any]]:
        """Return all saved store prices for a product from the database.

        Args:
            product_id: Internal DB product ID.

        Returns:
            List of dicts with store info and price.
        """
        self._get_product_or_raise(product_id)

        records = (
            self.db.query(ProductStorePrice, Store)
            .join(Store, ProductStorePrice.store_id == Store.id)
            .filter(ProductStorePrice.product_id == product_id)
            .all()
        )

        return [
            {
                "store_id": store.id,
                "store_name": store.name,
                "kroger_location_id": store.kroger_location_id,
                "address": store.address,
                "city": store.city,
                "state": store.state,
                "price": float(record.price),
                "last_updated": record.last_updated,
            }
            for record, store in records
        ]
