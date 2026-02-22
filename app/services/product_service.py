"""
Product Service Layer - PriceOrbit.

Contains all business logic for product operations.
Services raise domain exceptions (NotFoundError, DuplicateError, etc.);
the router layer is responsible for mapping those to HTTP responses.
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.exceptions import DuplicateError, NotFoundError, ValidationError
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductUpdate
from app.services.price_history_service import PriceHistoryService

logger = logging.getLogger(__name__)


class ProductService:
    """
    Service class for Product CRUD and business logic.

    All public methods raise domain-specific exceptions rather than
    HTTPException so that business logic stays framework-agnostic.
    """

    def __init__(self, db: Session) -> None:
        """
        Args:
            db: Active SQLAlchemy session injected by FastAPI dependency.
        """
        self.db = db

    # ------------------------------------------------------------------
    # READ
    # ------------------------------------------------------------------

    def get_all_products(
        self,
        skip: int = 0,
        limit: int = 100,
        category: Optional[str] = None,
    ) -> List[Product]:
        """
        Return a paginated list of products, optionally filtered by category.

        Args:
            skip: Number of records to skip (pagination offset).
            limit: Maximum records to return (page size).
            category: If provided, only return products in this category.

        Returns:
            List of Product ORM objects.
        """
        logger.debug("Fetching products skip=%d limit=%d category=%s", skip, limit, category)
        query = self.db.query(Product)
        if category:
            query = query.filter(Product.category == category)
        return query.offset(skip).limit(limit).all()

    def get_product_count(self, category: Optional[str] = None) -> int:
        """
        Count products, optionally scoped to a category.

        Args:
            category: Optional category filter.

        Returns:
            Integer count of matching products.
        """
        query = self.db.query(Product)
        if category:
            query = query.filter(Product.category == category)
        return query.count()

    def get_product_by_id(self, product_id: int) -> Product:
        """
        Fetch a single product by primary key.

        Args:
            product_id: Primary key of the product.

        Returns:
            Product ORM object.

        Raises:
            NotFoundError: If no product exists with that ID.
        """
        logger.debug("Looking up product id=%d", product_id)
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise NotFoundError("Product", product_id)
        return product

    def get_all_categories(self) -> List[str]:
        """
        Return all distinct category names, sorted alphabetically.

        Returns:
            Sorted list of category name strings.
        """
        rows = self.db.query(Product.category).distinct().all()
        return sorted(row[0] for row in rows)

    def search_products(self, query: str) -> List[Product]:
        """
        Case-insensitive search across product name and category.

        Args:
            query: Search string (minimum 2 characters).

        Returns:
            List of matching Product ORM objects.

        Raises:
            ValidationError: If query is shorter than 2 characters.
        """
        if len(query) < 2:
            raise ValidationError(
                "Search query must be at least 2 characters.",
                details={"query": query, "min_length": 2},
            )
        pattern = f"%{query}%"
        logger.debug("Searching products query='%s'", query)
        return (
            self.db.query(Product)
            .filter(or_(Product.name.ilike(pattern), Product.category.ilike(pattern)))
            .all()
        )

    def get_price_history(self, product_id: int) -> Dict[str, Any]:
        """
        Return the full price history for a product plus computed statistics.

        Statistics include min, max, average, and a simple trend label
        ("rising", "falling", or "stable") derived from the first and
        last recorded prices.

        Args:
            product_id: Target product's primary key.

        Returns:
            Dict with keys: product_id, product_name, current_price,
            history (list), statistics (dict).

        Raises:
            NotFoundError: If the product does not exist.
        """
        logger.info("Fetching price history for product id=%d", product_id)
        product = self.get_product_by_id(product_id)

        history: List[Dict] = product.price_history or []
        current_price = float(product.current_price) if product.current_price else None

        stats = PriceHistoryService.calculate_statistics(history, current_price)

        logger.debug(
            "Price history for product id=%d: %d entries trend=%s",
            product_id,
            stats["count"],
            stats["trend"],
        )

        return PriceHistoryService.format_response(
            product_id=product.id,
            product_name=product.name,
            current_price=current_price,
            history=history,
            stats=stats,
        )

    # ------------------------------------------------------------------
    # WRITE
    # ------------------------------------------------------------------

    def create_product(self, product_data: ProductCreate) -> Product:
        """
        Create and persist a new product.

        Health score is calculated automatically before saving.

        Args:
            product_data: Validated ProductCreate schema.

        Returns:
            Newly created Product ORM object with assigned ID.

        Raises:
            DuplicateError: If a product with the same name already exists.
        """
        logger.info("Creating product name='%s'", product_data.name)

        existing = self.db.query(Product).filter(Product.name == product_data.name).first()
        if existing:
            raise DuplicateError("Product", "name", product_data.name)

        product = Product(**product_data.model_dump())
        product.calculate_health_score()

        self.db.add(product)
        self.db.commit()
        self.db.refresh(product)

        logger.info("Product created id=%d health_score=%s", product.id, product.health_score)
        return product

    def update_product(self, product_id: int, product_data: ProductUpdate) -> Product:
        """
        Partially update a product. Only fields included in the request body change.

        If current_price changes, the old price is automatically appended to
        price_history. Health score is recalculated whenever tariff_rate,
        import_dependency, or current_price is modified.

        Args:
            product_id: Primary key of the product to update.
            product_data: ProductUpdate schema (all fields optional).

        Returns:
            Updated Product ORM object.

        Raises:
            NotFoundError: If the product does not exist.
        """
        logger.info("Updating product id=%d", product_id)
        product = self.get_product_by_id(product_id)
        update_data = product_data.model_dump(exclude_unset=True)

        # Record old price in history before overwriting
        if "current_price" in update_data and update_data["current_price"] is not None:
            if product.current_price is not None and product.current_price != update_data["current_price"]:
                product.add_price_to_history(product.current_price, datetime.now().isoformat())

        for field, value in update_data.items():
            setattr(product, field, value)

        # Recalculate health score when supply-chain fields change
        if any(key in update_data for key in ("tariff_rate", "import_dependency", "current_price")):
            product.calculate_health_score()

        product.updated_at = datetime.now()
        self.db.commit()
        self.db.refresh(product)

        logger.info("Product id=%d updated successfully", product_id)
        return product

    def delete_product(self, product_id: int) -> None:
        """
        Permanently delete a product.

        Args:
            product_id: Primary key of the product to delete.

        Raises:
            NotFoundError: If the product does not exist.
        """
        logger.info("Deleting product id=%d", product_id)
        product = self.get_product_by_id(product_id)
        self.db.delete(product)
        self.db.commit()
        logger.info("Product id=%d deleted", product_id)

    def add_manual_price(self, product_id: int, price: Decimal) -> Product:
        """
        Record a manually supplied price for a product.

        Appends the previous current_price to price_history, sets the new
        current_price, updates last_price_check, and recalculates the
        health score.

        Args:
            product_id: Target product's primary key.
            price: New price value (must be > 0).

        Returns:
            Updated Product ORM object.

        Raises:
            NotFoundError: If the product does not exist.
            ValidationError: If the price is not positive.
        """
        logger.info("Recording manual price product id=%d price=%.2f", product_id, price)

        if price <= 0:
            raise ValidationError(
                "Price must be greater than zero.",
                details={"product_id": product_id, "price": str(price)},
            )

        product = self.get_product_by_id(product_id)

        # Archive the current price before overwriting
        if product.current_price is not None:
            product.add_price_to_history(product.current_price, datetime.now().isoformat())

        product.current_price = price
        product.last_price_check = datetime.now()
        product.calculate_health_score()

        self.db.commit()
        self.db.refresh(product)

        logger.info("Manual price recorded product id=%d new_price=%.2f", product_id, price)
        return product

    def add_price_point(
        self,
        product_id: int,
        price: Decimal,
        record_date: Optional[str] = None,
    ) -> Product:
        """
        Record a new price data point for a product.

        Behaviour depends on whether ``record_date`` is today or in the past:

        **Live update** (``record_date`` is ``None`` or today's date):

        1. Archive ``current_price`` → ``price_history`` (timestamped now).
        2. Set ``current_price = price``.
        3. Update ``last_price_check``.
        4. Recalculate health score.

        **Back-fill** (``record_date`` is a past ISO-8601 date string):

        1. Insert a historical entry at the given date without touching
           ``current_price`` — useful for importing historical data.
        2. Recalculate health score (volatility may change).

        In both cases, ``price_history`` is pruned to entries within the
        last 365 days via :class:`PriceHistoryService`.

        Args:
            product_id: Target product's primary key.
            price: Price value to record (must be > 0).
            record_date: ISO-8601 date string (``YYYY-MM-DD``). Defaults
                to today, triggering a live update.

        Returns:
            Updated Product ORM object.

        Raises:
            NotFoundError: If the product does not exist.
            ValidationError: If ``price`` is not positive, or if
                ``record_date`` is not a valid ISO-8601 date.
        """
        logger.info(
            "Adding price point product id=%d price=%.2f date=%s",
            product_id,
            price,
            record_date or "today",
        )

        if price <= 0:
            raise ValidationError(
                "Price must be greater than zero.",
                details={"product_id": product_id, "price": str(price)},
            )

        # Validate date format when explicitly supplied
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
            # Archive existing current_price into history before overwriting
            if product.current_price is not None:
                product.add_price_to_history(
                    product.current_price, datetime.now().isoformat()
                )
            product.current_price = price
            product.last_price_check = datetime.now()
            logger.debug("Live update: current_price set to %.2f for product id=%d", price, product_id)
        else:
            # Back-fill: add a historical entry without changing current_price
            product.add_price_to_history(price, record_date)
            logger.debug(
                "Back-fill: inserted historical entry %.2f on %s for product id=%d",
                price,
                record_date,
                product_id,
            )

        # Prune history to last 365 days
        if product.price_history:
            product.price_history = PriceHistoryService.clean_old_history(
                product.price_history
            )

        product.calculate_health_score()

        self.db.commit()
        self.db.refresh(product)

        logger.info(
            "Price point recorded product id=%d price=%.2f live=%s new_health=%.2f",
            product_id,
            price,
            is_live_update,
            float(product.health_score),
        )
        return product

    # ------------------------------------------------------------------
    # ADMIN / BULK
    # ------------------------------------------------------------------

    def recalculate_all_health_scores(self) -> int:
        """
        Recalculate and persist health scores for every product.

        Useful after the algorithm changes. Commits once after all updates
        to minimise round-trips.

        Returns:
            Number of products updated.
        """
        logger.info("Recalculating health scores for all products")
        products = self.db.query(Product).all()
        for product in products:
            product.calculate_health_score()
        self.db.commit()
        logger.info("Recalculated health scores for %d products", len(products))
        return len(products)
