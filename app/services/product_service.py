"""
Product Service Layer - PriceOrbit.

Contains business logic for product CRUD, health scoring, price history,
and automated Kroger price updates.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    DuplicateError,
    ExternalAPIError,
    NotFoundError,
    ValidationError,
)
from app.models.product_model import Product
from app.schemas.product_schemas import ProductCreate, ProductUpdate
from app.services.kroger_service import KrogerAPIError, KrogerRateLimitError, KrogerService
from app.services.price_history_service import PriceHistoryService

logger = logging.getLogger(__name__)


class ProductService:
    """Service class for Product CRUD and product-domain workflows."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_pagination(skip: int, limit: int) -> None:
        if skip < 0:
            raise ValidationError("Pagination 'skip' must be >= 0.", details={"skip": skip})
        if limit < 1 or limit > 100:
            raise ValidationError(
                "Pagination 'limit' must be between 1 and 100.",
                details={"limit": limit},
            )

    def _commit_or_raise(self) -> None:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            logger.exception("Integrity error during DB commit")
            raise ValidationError(
                "Database integrity error.",
                details={"error": str(exc.orig) if exc.orig else str(exc)},
            )
        except SQLAlchemyError as exc:
            self.db.rollback()
            logger.exception("SQLAlchemy error during DB commit")
            raise ValidationError("Database operation failed.", details={"error": str(exc)})

    def _commit_refresh_or_raise(self, product: Product) -> Product:
        self._commit_or_raise()
        try:
            self.db.refresh(product)
        except SQLAlchemyError as exc:
            self.db.rollback()
            logger.exception("Failed to refresh product id=%s", product.id)
            raise ValidationError("Failed to refresh updated product.", details={"error": str(exc)})
        return product

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_all_products(
        self,
        skip: int = 0,
        limit: int = 100,
        category: Optional[str] = None,
    ) -> List[Product]:
        self._validate_pagination(skip, limit)
        query = self.db.query(Product)
        if category:
            query = query.filter(Product.category == category)
        return query.order_by(Product.id.asc()).offset(skip).limit(limit).all()

    def get_product_count(self, category: Optional[str] = None) -> int:
        query = self.db.query(Product)
        if category:
            query = query.filter(Product.category == category)
        return query.count()

    def get_product_by_id(self, product_id: int) -> Product:
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise NotFoundError("Product", product_id)
        return product

    def get_products_by_category(
        self,
        category: str,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Product]:
        self._validate_pagination(skip, limit)
        category_value = category.strip()
        if not category_value:
            raise ValidationError("Category cannot be empty.")
        return (
            self.db.query(Product)
            .filter(Product.category == category_value)
            .order_by(Product.id.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_all_categories(self) -> List[str]:
        rows = self.db.query(Product.category).distinct().all()
        return sorted(row[0] for row in rows)

    def search_products(self, query: str) -> List[Product]:
        search_term = query.strip()
        if len(search_term) < 2:
            raise ValidationError(
                "Search query must be at least 2 characters.",
                details={"query": query, "min_length": 2},
            )

        pattern = f"%{search_term}%"
        logger.debug("Searching products by name query='%s'", search_term)
        return (
            self.db.query(Product)
            .filter(Product.name.ilike(pattern))
            .order_by(Product.id.asc())
            .all()
        )

    def get_price_history(self, product_id: int) -> Dict[str, Any]:
        product = self.get_product_by_id(product_id)

        history: List[Dict[str, Any]] = product.price_history or []
        current_price = float(product.current_price) if product.current_price is not None else None
        stats = PriceHistoryService.calculate_statistics(history, current_price)

        return PriceHistoryService.format_response(
            product_id=product.id,
            product_name=product.name,
            current_price=current_price,
            history=history,
            stats=stats,
        )

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def create_product(self, product_data: ProductCreate) -> Product:
        name = product_data.name.strip()
        if not name:
            raise ValidationError("Product name cannot be blank.")

        existing = (
            self.db.query(Product)
            .filter(func.lower(Product.name) == name.lower())
            .first()
        )
        if existing:
            raise DuplicateError("Product", "name", product_data.name)

        payload = product_data.model_dump()
        payload["name"] = name

        product = Product(**payload)
        product.calculate_health_score()

        self.db.add(product)
        self._commit_refresh_or_raise(product)
        logger.info("Created product id=%s name=%s", product.id, product.name)
        return product

    def update_product(self, product_id: int, product_data: ProductUpdate) -> Product:
        product = self.get_product_by_id(product_id)
        update_data = product_data.model_dump(exclude_unset=True)

        if "name" in update_data and update_data["name"] is not None:
            new_name = update_data["name"].strip()
            if not new_name:
                raise ValidationError("Product name cannot be blank.")

            existing = (
                self.db.query(Product)
                .filter(func.lower(Product.name) == new_name.lower(), Product.id != product_id)
                .first()
            )
            if existing:
                raise DuplicateError("Product", "name", new_name)
            update_data["name"] = new_name

        if "current_price" in update_data and update_data["current_price"] is not None:
            if (
                product.current_price is not None
                and product.current_price != update_data["current_price"]
            ):
                product.add_price_to_history(
                    product.current_price,
                    datetime.now(timezone.utc).isoformat(),
                )

        for field, value in update_data.items():
            setattr(product, field, value)

        if any(key in update_data for key in ("tariff_rate", "import_dependency", "current_price")):
            product.calculate_health_score()

        product.updated_at = datetime.now(timezone.utc)
        self._commit_refresh_or_raise(product)
        logger.info("Updated product id=%s", product_id)
        return product

    def delete_product(self, product_id: int) -> None:
        product = self.get_product_by_id(product_id)
        self.db.delete(product)
        self._commit_or_raise()
        logger.info("Deleted product id=%s", product_id)

    def add_manual_price(self, product_id: int, price: Decimal) -> Product:
        return self.add_price_point(product_id=product_id, price=price, record_date=None)

    def add_price_point(
        self,
        product_id: int,
        price: Decimal,
        record_date: Optional[str] = None,
    ) -> Product:
        if price <= 0:
            raise ValidationError(
                "Price must be greater than zero.",
                details={"product_id": product_id, "price": str(price)},
            )

        today_str = date.today().isoformat()
        if record_date is not None:
            try:
                date.fromisoformat(record_date)
            except ValueError:
                raise ValidationError(
                    f"Invalid date format '{record_date}'. Expected YYYY-MM-DD.",
                    details={"product_id": product_id, "date": record_date},
                )

        is_live_update = record_date is None or record_date == today_str
        product = self.get_product_by_id(product_id)

        if is_live_update:
            if product.current_price is not None:
                product.add_price_to_history(
                    product.current_price,
                    datetime.now(timezone.utc).isoformat(),
                )
            product.current_price = price
            product.last_price_check = datetime.now(timezone.utc)
        else:
            product.add_price_to_history(price, record_date)

        if product.price_history:
            product.price_history = PriceHistoryService.clean_old_history(product.price_history)

        product.calculate_health_score()
        self._commit_refresh_or_raise(product)
        logger.info(
            "Added price point for product id=%s price=%s live=%s",
            product_id,
            price,
            is_live_update,
        )
        return product

    def recalculate_health_score(self, product_id: int) -> Product:
        product = self.get_product_by_id(product_id)
        product.calculate_health_score()
        self._commit_refresh_or_raise(product)
        return product

    def recalculate_all_health_scores(self) -> int:
        products = self.db.query(Product).all()
        for product in products:
            product.calculate_health_score()
        self._commit_or_raise()
        logger.info("Recalculated health scores for %s products", len(products))
        return len(products)

    # ------------------------------------------------------------------
    # Kroger-driven price update operations
    # ------------------------------------------------------------------

    async def _resolve_kroger_product(self, product: Product, kroger: KrogerService) -> Dict[str, Any]:
        if product.kroger_product_id:
            return await kroger.get_product_details(product.kroger_product_id)

        match = await kroger.find_kroger_product(product.name)
        if not match:
            raise ExternalAPIError("Kroger", f"No product match found for '{product.name}'.")

        product.kroger_product_id = match["product_id"]
        if match.get("image_url"):
            product.image_url = match["image_url"]

        logger.info(
            "Mapped product id=%s to Kroger id=%s with confidence=%s",
            product.id,
            product.kroger_product_id,
            match.get("confidence"),
        )
        return await kroger.get_product_details(product.kroger_product_id)

    @staticmethod
    def _extract_price_from_kroger_payload(payload: Dict[str, Any]) -> Decimal:
        items = payload.get("items", [])
        if not items:
            raise ExternalAPIError("Kroger", "Product payload did not include item pricing data.")

        item = items[0]
        price_block = item.get("price") or {}
        national_block = item.get("nationalPrice") or {}

        raw_price = (
            price_block.get("regular")
            or price_block.get("promo")
            or national_block.get("regular")
            or national_block.get("promo")
        )
        if raw_price is None:
            raise ExternalAPIError("Kroger", "No regular/promo price found for product.")

        try:
            return Decimal(str(raw_price))
        except Exception as exc:  # pragma: no cover - defensive guard
            raise ExternalAPIError("Kroger", f"Invalid price value received: {raw_price}") from exc

    async def _fetch_price_with_retries(
        self,
        product: Product,
        kroger: KrogerService,
        retries: int = 3,
    ) -> Decimal:
        for attempt in range(retries):
            try:
                payload = await self._resolve_kroger_product(product, kroger)
                return self._extract_price_from_kroger_payload(payload)
            except (KrogerAPIError, KrogerRateLimitError, ExternalAPIError, ValueError) as exc:
                is_last_attempt = attempt == retries - 1
                if is_last_attempt:
                    raise ExternalAPIError("Kroger", str(exc)) from exc

                backoff = 2 ** attempt
                logger.warning(
                    "Retrying Kroger fetch for product id=%s in %ss after error: %s",
                    product.id,
                    backoff,
                    exc,
                )
                await asyncio.sleep(backoff)

        raise ExternalAPIError("Kroger", "Maximum retries exceeded while fetching price.")

    def _build_price_update_response(
        self,
        product: Product,
        old_price: Optional[Decimal],
        new_price: Decimal,
        old_health_score: Decimal,
    ) -> Dict[str, Any]:
        price_change: Optional[float] = None
        if old_price not in (None, Decimal("0")):
            price_change = round(((float(new_price) - float(old_price)) / float(old_price)) * 100, 2)

        return {
            "product_id": product.id,
            "product_name": product.name,
            "old_price": old_price,
            "new_price": new_price,
            "price_change": price_change,
            "old_health_score": old_health_score,
            "new_health_score": product.health_score,
            "updated_at": product.last_price_check or datetime.now(timezone.utc),
            "source": "kroger_api",
        }

    async def _update_single_product_price(
        self,
        product: Product,
        kroger: KrogerService,
    ) -> Dict[str, Any]:
        old_price = product.current_price
        old_health_score = product.health_score

        new_price = await self._fetch_price_with_retries(product, kroger, retries=3)

        if old_price is not None and old_price != new_price:
            product.add_price_to_history(old_price, datetime.now(timezone.utc).isoformat())

        product.current_price = new_price
        product.last_price_check = datetime.now(timezone.utc)
        product.calculate_health_score()

        self._commit_refresh_or_raise(product)
        logger.info(
            "Updated price for product id=%s old=%s new=%s",
            product.id,
            old_price,
            new_price,
        )
        return self._build_price_update_response(product, old_price, new_price, old_health_score)

    async def update_price_from_kroger(self, product_id: int) -> Dict[str, Any]:
        product = self.get_product_by_id(product_id)
        async with KrogerService(
            client_id=settings.KROGER_CLIENT_ID,
            client_secret=settings.KROGER_CLIENT_SECRET,
        ) as kroger:
            return await self._update_single_product_price(product, kroger)

    async def update_all_prices(self, limit: int = 50) -> Dict[str, Any]:
        if limit < 1 or limit > 50:
            raise ValidationError("Batch limit must be between 1 and 50.", details={"limit": limit})

        products = self.db.query(Product).order_by(Product.id.asc()).limit(limit).all()
        if not products:
            return {
                "processed": 0,
                "updated": 0,
                "failed": 0,
                "results": [],
                "errors": [],
            }

        results: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []

        async with KrogerService(
            client_id=settings.KROGER_CLIENT_ID,
            client_secret=settings.KROGER_CLIENT_SECRET,
        ) as kroger:
            for product in products:
                try:
                    response = await self._update_single_product_price(product, kroger)
                    results.append(response)
                except (ExternalAPIError, ValidationError) as exc:
                    self.db.rollback()
                    errors.append(
                        {
                            "product_id": product.id,
                            "product_name": product.name,
                            "detail": str(exc),
                        }
                    )
                    logger.warning("Failed batch update for product id=%s: %s", product.id, exc)

        return {
            "processed": len(products),
            "updated": len(results),
            "failed": len(errors),
            "results": results,
            "errors": errors,
        }
