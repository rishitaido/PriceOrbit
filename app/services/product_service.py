"""
Product Service Layer - PriceOrbit.

Contains business logic for product CRUD, health scoring, price history,
and automated Kroger price updates.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path
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
from app.models.product_store_price_model import ProductStorePrice
from app.models.store_model import Store
from app.schemas.product_schemas import ProductCreate, ProductUpdate
from app.services.kroger_service import KrogerAPIError, KrogerRateLimitError, KrogerService
from app.services.price_alert_service import PriceAlertService
from app.services.price_history_service import PriceHistoryService

logger = logging.getLogger(__name__)


class ProductService:
    """Service class for Product CRUD and product-domain workflows."""

    CATEGORY_COMPATIBILITY_KEYWORDS = {
        "Fresh Produce": {"produce"},
        "Dairy & Eggs": {"dairy", "egg"},
        "Meat & Seafood": {"meat", "seafood"},
        "Pantry Staples": {"pantry", "grocery", "baking", "canned", "pasta", "rice"},
        "Frozen Foods": {"frozen"},
    }

    def __init__(self, db: Session) -> None:
        self.db = db
        self._override_by_name: Dict[str, str] = {}
        self._override_by_product_id: Dict[int, str] = {}
        self._aliases_by_name: Dict[str, List[str]] = {}
        self._load_kroger_mapping_controls()

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

    @staticmethod
    def _is_certification_environment() -> bool:
        return "api-ce.kroger.com" in (settings.KROGER_BASE_URL or "")

    def _effective_min_match_confidence(self) -> float:
        if self._is_certification_environment():
            return settings.KROGER_CERT_MIN_MATCH_CONFIDENCE
        return settings.KROGER_MIN_MATCH_CONFIDENCE

    @staticmethod
    def _is_unmatched_product_error(exc: Exception) -> bool:
        return "No product match found for" in str(exc)

    @staticmethod
    def _normalize_lookup_key(value: str) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def _resolve_file_path(raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        return candidate

    @classmethod
    def _load_json_file(cls, raw_path: str, label: str) -> Dict[str, Any]:
        path = cls._resolve_file_path(raw_path)
        if not path.exists():
            logger.info("%s file not found at %s; continuing without it", label, path)
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.warning("Invalid JSON in %s file %s: %s", label, path, exc)
            return {}
        except OSError as exc:
            logger.warning("Unable to read %s file %s: %s", label, path, exc)
            return {}

        if not isinstance(payload, dict):
            logger.warning("%s file %s must contain a top-level JSON object", label, path)
            return {}
        return payload

    def _load_kroger_mapping_controls(self) -> None:
        overrides_payload = self._load_json_file(
            settings.KROGER_OVERRIDE_FILE,
            label="Kroger override",
        )
        aliases_payload = self._load_json_file(
            settings.KROGER_ALIAS_FILE,
            label="Kroger alias",
        )

        by_name_raw: Dict[str, Any] = {}
        by_product_id_raw: Dict[str, Any] = {}
        if "by_name" in overrides_payload or "by_product_id" in overrides_payload:
            if isinstance(overrides_payload.get("by_name"), dict):
                by_name_raw = overrides_payload.get("by_name", {})
            if isinstance(overrides_payload.get("by_product_id"), dict):
                by_product_id_raw = overrides_payload.get("by_product_id", {})
        else:
            by_name_raw = overrides_payload

        normalized_by_name: Dict[str, str] = {}
        for product_name, kroger_id in by_name_raw.items():
            normalized_name = self._normalize_lookup_key(str(product_name))
            normalized_kroger_id = str(kroger_id).strip()
            if normalized_name and normalized_kroger_id:
                normalized_by_name[normalized_name] = normalized_kroger_id

        normalized_by_product_id: Dict[int, str] = {}
        for product_id_key, kroger_id in by_product_id_raw.items():
            normalized_kroger_id = str(kroger_id).strip()
            if not normalized_kroger_id:
                continue
            try:
                normalized_product_id = int(str(product_id_key).strip())
            except ValueError:
                continue
            normalized_by_product_id[normalized_product_id] = normalized_kroger_id

        normalized_aliases: Dict[str, List[str]] = {}
        for product_name, alias_values in aliases_payload.items():
            normalized_name = self._normalize_lookup_key(str(product_name))
            if not normalized_name:
                continue

            alias_list: List[str]
            if isinstance(alias_values, str):
                alias_list = [alias_values]
            elif isinstance(alias_values, list):
                alias_list = [str(alias) for alias in alias_values]
            else:
                continue

            deduped: List[str] = []
            seen: set[str] = set()
            for alias in alias_list:
                normalized_alias = alias.strip()
                normalized_alias_key = self._normalize_lookup_key(normalized_alias)
                if not normalized_alias or normalized_alias_key in seen:
                    continue
                seen.add(normalized_alias_key)
                deduped.append(normalized_alias)
            if deduped:
                normalized_aliases[normalized_name] = deduped

        self._override_by_name = normalized_by_name
        self._override_by_product_id = normalized_by_product_id
        self._aliases_by_name = normalized_aliases

    def _get_override_kroger_id(self, product: Product) -> Optional[str]:
        if product.id in self._override_by_product_id:
            return self._override_by_product_id[product.id]

        normalized_name = self._normalize_lookup_key(product.name)
        return self._override_by_name.get(normalized_name)

    def _get_search_terms(self, product_name: str) -> List[str]:
        primary = (product_name or "").strip()
        if not primary:
            return []

        base_primary = re.sub(r"\s*\([^)]*\)\s*$", "", primary).strip() or primary
        normalized_base = self._normalize_lookup_key(base_primary)
        normalized_primary = self._normalize_lookup_key(primary)

        terms = [base_primary]
        seen = {normalized_base}

        if normalized_primary and normalized_primary not in seen:
            terms.append(primary)
            seen.add(normalized_primary)

        for lookup_key in (normalized_primary, normalized_base):
            for alias in self._aliases_by_name.get(lookup_key, []):
                normalized_alias = self._normalize_lookup_key(alias)
                if not normalized_alias or normalized_alias in seen:
                    continue
                seen.add(normalized_alias)
                terms.append(alias)

        return terms

    @staticmethod
    def _derive_size_label(raw_size: Optional[str]) -> Optional[str]:
        size = str(raw_size or "").strip()
        if not size:
            return None
        return re.sub(r"\s+", " ", size)

    @classmethod
    def _build_size_aware_name(cls, existing_name: str, raw_size: Optional[str]) -> str:
        base_name = re.sub(r"\s*\([^)]*\)\s*$", "", (existing_name or "").strip()).strip()
        if not base_name:
            base_name = (existing_name or "").strip()
        if not base_name:
            return existing_name

        size_label = cls._derive_size_label(raw_size)
        if not size_label:
            return base_name
        return f"{base_name} ({size_label})"

    def _apply_kroger_metadata_labels(self, product: Product, payload: Dict[str, Any]) -> None:
        items = payload.get("items") or []
        item = items[0] if items else {}

        candidate_name = self._build_size_aware_name(product.name, item.get("size"))
        existing = (
            self.db.query(Product)
            .filter(Product.name == candidate_name, Product.id != product.id)
            .first()
        )
        if existing is None:
            product.name = candidate_name
        else:
            product.name = f"{candidate_name} [{product.id}]"

        description = str(payload.get("description") or "").strip()
        if description:
            product.description = description

    @staticmethod
    def parse_store_ids_csv(store_ids: Optional[str]) -> Optional[List[int]]:
        """
        Parse comma-separated store IDs into a unique ordered integer list.
        """
        if store_ids is None:
            return None

        raw_values = [value.strip() for value in store_ids.split(",")]
        filtered_values = [value for value in raw_values if value]
        if not filtered_values:
            return None

        parsed_ids: List[int] = []
        seen: set[int] = set()
        for raw_value in filtered_values:
            if not raw_value.isdigit():
                raise ValidationError(
                    "store_ids must be a comma-separated list of positive integers.",
                    details={"store_ids": store_ids},
                )
            parsed_id = int(raw_value)
            if parsed_id <= 0:
                raise ValidationError(
                    "store_ids must contain positive integers.",
                    details={"store_ids": store_ids},
                )
            if parsed_id not in seen:
                seen.add(parsed_id)
                parsed_ids.append(parsed_id)
        return parsed_ids

    def _get_stores_for_price_lookup(self, store_ids: Optional[List[int]]) -> List[Store]:
        query = self.db.query(Store)
        if store_ids:
            stores = query.filter(Store.id.in_(store_ids)).order_by(Store.id.asc()).all()
            found_ids = {store.id for store in stores}
            missing_ids = [store_id for store_id in store_ids if store_id not in found_ids]
            if missing_ids:
                raise NotFoundError("Store", ",".join(str(item) for item in missing_ids))
            return stores

        return query.order_by(Store.id.asc()).all()

    def _upsert_product_store_price(
        self,
        product_id: int,
        store_id: int,
        price: Decimal,
        records_by_store_id: Optional[Dict[int, ProductStorePrice]] = None,
    ) -> ProductStorePrice:
        record = None
        if records_by_store_id is not None:
            record = records_by_store_id.get(store_id)
        else:
            record = (
                self.db.query(ProductStorePrice)
                .filter(
                    ProductStorePrice.product_id == product_id,
                    ProductStorePrice.store_id == store_id,
                )
                .first()
            )

        if record is None:
            record = ProductStorePrice(
                product_id=product_id,
                store_id=store_id,
                price=price,
                last_updated=datetime.now(timezone.utc),
            )
            self.db.add(record)
        else:
            record.price = price
            record.last_updated = datetime.now(timezone.utc)

        if records_by_store_id is not None:
            records_by_store_id[store_id] = record

        return record

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

    async def get_product_prices_by_store(
        self,
        product_id: int,
        store_ids: Optional[List[int]] = None,
        refresh_from_api: bool = True,
    ) -> Dict[str, Any]:
        """
        Return store-specific prices for a product.

        If ``refresh_from_api`` is true, the service attempts to fetch current
        prices from Kroger for each requested store that has a
        ``kroger_location_id`` configured, then persists those prices in
        ``product_store_prices``.
        """
        product = self.get_product_by_id(product_id)
        stores = self._get_stores_for_price_lookup(store_ids)

        if not stores:
            return {"product_id": product.id, "product_name": product.name, "prices": []}

        records = (
            self.db.query(ProductStorePrice)
            .filter(
                ProductStorePrice.product_id == product.id,
                ProductStorePrice.store_id.in_([store.id for store in stores]),
            )
            .all()
        )
        records_by_store_id = {record.store_id: record for record in records}

        fetched_store_ids: set[int] = set()
        product_updated = False

        if refresh_from_api:
            async with KrogerService(
                client_id=settings.KROGER_CLIENT_ID,
                client_secret=settings.KROGER_CLIENT_SECRET,
            ) as kroger:
                if not product.kroger_product_id:
                    try:
                        await self._resolve_kroger_product(product, kroger)
                        product_updated = True
                    except ExternalAPIError as exc:
                        logger.warning(
                            "Unable to map product id=%s to Kroger before store pricing lookup: %s",
                            product.id,
                            exc,
                        )

                if product.kroger_product_id:
                    concurrency_limit = 5
                    semaphore = asyncio.Semaphore(concurrency_limit)

                    async def fetch_one_store_price(store: Store) -> tuple[int, Decimal] | None:
                        if not store.kroger_location_id:
                            return None

                        try:
                            async with semaphore:
                                payload = await kroger.get_product_price_by_location(
                                    product_id=product.kroger_product_id,
                                    location_id=store.kroger_location_id,
                                )
                            price = self._extract_price_from_kroger_price_result(payload)
                            return store.id, price
                        except (ExternalAPIError, KrogerAPIError, KrogerRateLimitError, ValueError) as exc:
                            logger.warning(
                                "Store price lookup failed product_id=%s store_id=%s location=%s: %s",
                                product.id,
                                store.id,
                                store.kroger_location_id,
                                exc,
                            )
                            return None

                    results = await asyncio.gather(
                        *(fetch_one_store_price(store) for store in stores if store.kroger_location_id),
                    )
                    for result in results:
                        if result is None:
                            continue
                        store_id, price = result
                        self._upsert_product_store_price(
                            product.id,
                            store_id,
                            price,
                            records_by_store_id=records_by_store_id,
                        )
                        fetched_store_ids.add(store_id)

            if product_updated or fetched_store_ids:
                self._commit_or_raise()

        prices: List[Dict[str, Any]] = []
        for store in stores:
            record = records_by_store_id.get(store.id)
            if store.id in fetched_store_ids:
                source = "kroger_api"
            elif record is not None:
                source = "database"
            else:
                source = "unavailable"

            prices.append(
                {
                    "store_id": store.id,
                    "store_name": store.name,
                    "kroger_location_id": store.kroger_location_id,
                    "price": record.price if record is not None else None,
                    "last_updated": record.last_updated if record is not None else None,
                    "source": source,
                    "distance": None,
                }
            )

        return {
            "product_id": product.id,
            "product_name": product.name,
            "prices": prices,
        }

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
                    source="manual_update",
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
                    source="manual_price_point",
                )
            product.current_price = price
            product.last_price_check = datetime.now(timezone.utc)
        else:
            product.add_price_to_history(price, record_date, source="manual_price_point")

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
        override_kroger_id = self._get_override_kroger_id(product)
        if override_kroger_id:
            try:
                payload = await kroger.get_product_details(override_kroger_id)
            except (KrogerAPIError, KrogerRateLimitError, ValueError) as exc:
                logger.warning(
                    "Override Kroger ID failed for product id=%s id=%s: %s",
                    product.id,
                    override_kroger_id,
                    exc,
                )
            else:
                if self._is_category_compatible(product.category, payload):
                    if product.kroger_product_id != override_kroger_id:
                        product.kroger_product_id = override_kroger_id
                        logger.info(
                            "Applied manual Kroger override for product id=%s: %s",
                            product.id,
                            override_kroger_id,
                        )

                    override_image = self._extract_image_from_search_candidate(payload)
                    if override_image:
                        product.image_url = override_image
                    self._apply_kroger_metadata_labels(product, payload)
                    return payload

                logger.warning(
                    "Rejected override Kroger ID for product id=%s name='%s' category='%s' id=%s",
                    product.id,
                    product.name,
                    product.category,
                    override_kroger_id,
                )

            if product.kroger_product_id == override_kroger_id:
                product.kroger_product_id = None

        if product.kroger_product_id:
            mapped_id = str(product.kroger_product_id).strip()
            try:
                payload = await kroger.get_product_details(mapped_id)
            except (KrogerAPIError, KrogerRateLimitError, ValueError) as exc:
                logger.warning(
                    "Stored Kroger mapping failed for product id=%s mapped_id=%s: %s",
                    product.id,
                    mapped_id,
                    exc,
                )
                product.kroger_product_id = None
            else:
                if self._is_category_compatible(product.category, payload):
                    self._apply_kroger_metadata_labels(product, payload)
                    return payload

                logger.warning(
                    "Stored Kroger mapping category mismatch for product id=%s name='%s' mapped_id=%s; remapping",
                    product.id,
                    product.name,
                    mapped_id,
                )
                product.kroger_product_id = None

        search_terms = self._get_search_terms(product.name)
        for index, search_term in enumerate(search_terms):
            min_confidence = self._effective_min_match_confidence()
            if index > 0:
                min_confidence = min(min_confidence, settings.KROGER_ALIAS_MIN_MATCH_CONFIDENCE)

            match = await kroger.find_kroger_product(
                search_term,
                min_confidence=min_confidence,
            )
            if not match:
                continue

            product.kroger_product_id = match["product_id"]
            if match.get("image_url"):
                product.image_url = match["image_url"]

            logger.info(
                "Mapped product id=%s to Kroger id=%s using term='%s' confidence=%s",
                product.id,
                product.kroger_product_id,
                search_term,
                match.get("confidence"),
            )
            try:
                payload = await kroger.get_product_details(product.kroger_product_id)
            except (KrogerAPIError, KrogerRateLimitError, ValueError) as exc:
                logger.warning(
                    "Mapped Kroger ID lookup failed for product id=%s term='%s' id=%s: %s",
                    product.id,
                    search_term,
                    product.kroger_product_id,
                    exc,
                )
                product.kroger_product_id = None
                continue

            if not self._is_category_compatible(product.category, payload):
                logger.warning(
                    "Rejected mapped Kroger ID for product id=%s term='%s' id=%s due to category mismatch",
                    product.id,
                    search_term,
                    product.kroger_product_id,
                )
                product.kroger_product_id = None
                continue

            self._apply_kroger_metadata_labels(product, payload)
            return payload

        raise ExternalAPIError("Kroger", f"No product match found for '{product.name}'.")

    @staticmethod
    def _extract_price_from_kroger_payload(payload: Dict[str, Any]) -> Decimal:
        items = payload.get("items", [])
        if not items:
            raise ExternalAPIError("Kroger", "Product payload did not include item pricing data.")

        for item in items:
            price_block = item.get("price") or {}
            national_block = item.get("nationalPrice") or {}
            raw_price = (
                price_block.get("regular")
                or price_block.get("promo")
                or national_block.get("regular")
                or national_block.get("promo")
            )
            if raw_price is None:
                continue
            try:
                return Decimal(str(raw_price))
            except Exception as exc:  # pragma: no cover - defensive guard
                raise ExternalAPIError("Kroger", f"Invalid price value received: {raw_price}") from exc

        raise ExternalAPIError("Kroger", "No regular/promo price found for product.")

    @staticmethod
    def _extract_price_from_kroger_price_result(payload: Dict[str, Any]) -> Decimal:
        price_block = payload.get("price") or {}
        national_block = payload.get("nationalPrice") or {}
        raw_price = (
            price_block.get("regular")
            or price_block.get("promo")
            or national_block.get("regular")
            or national_block.get("promo")
        )
        if raw_price is None:
            raise ExternalAPIError("Kroger", "No regular/promo price found in store price response.")

        try:
            return Decimal(str(raw_price))
        except Exception as exc:  # pragma: no cover - defensive guard
            raise ExternalAPIError("Kroger", f"Invalid price value received: {raw_price}") from exc

    @staticmethod
    def _confidence(search_term: str, description: str) -> float:
        return SequenceMatcher(None, search_term.lower(), description.lower()).ratio()

    @staticmethod
    def _extract_image_from_search_candidate(candidate: Dict[str, Any]) -> Optional[str]:
        images = candidate.get("images") or []
        if not images:
            return None
        sizes = (images[0] or {}).get("sizes") or []
        if not sizes:
            return None
        return sizes[-1].get("url")

    @classmethod
    def _is_category_compatible(cls, product_category: str, candidate: Dict[str, Any]) -> bool:
        expected_keywords = cls.CATEGORY_COMPATIBILITY_KEYWORDS.get(product_category)
        if not expected_keywords:
            return True

        categories = candidate.get("categories") or []
        if not categories:
            return True

        candidate_categories = {str(value).strip().lower() for value in categories if value}
        for candidate_category in candidate_categories:
            if any(keyword in candidate_category for keyword in expected_keywords):
                return True
        return False

    async def _fallback_price_from_search_candidates(
        self,
        product: Product,
        kroger: KrogerService,
        limit: int = 10,
    ) -> Optional[Decimal]:
        locked_override_id = self._get_override_kroger_id(product)
        candidates: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()
        for search_term in self._get_search_terms(product.name):
            term_candidates = await kroger.search_products(search_term, limit=limit)
            for candidate in term_candidates:
                candidate_id = str(candidate.get("productId") or "").strip()
                if not candidate_id:
                    continue
                if candidate_id in seen_ids:
                    continue
                seen_ids.add(candidate_id)
                candidates.append(candidate)

        if not candidates:
            return None

        product_label = re.sub(r"\s*\([^)]*\)\s*$", "", (product.name or "").strip()).strip() or product.name
        ranked = sorted(
            candidates,
            key=lambda item: self._confidence(product_label, item.get("description") or ""),
            reverse=True,
        )

        compatible_ranked = [
            candidate
            for candidate in ranked
            if self._is_category_compatible(product.category, candidate)
        ]

        # Prefer category-compatible candidates first; then fall back to all.
        candidate_groups = [compatible_ranked, ranked] if compatible_ranked else [ranked]
        seen: set[str] = set()

        for group in candidate_groups:
            for candidate in group:
                candidate_id = candidate.get("productId")
                if candidate_id in seen:
                    continue
                seen.add(candidate_id)

                candidate_confidence = self._confidence(
                    product_label,
                    candidate.get("description") or "",
                )
                if candidate_confidence < settings.KROGER_FALLBACK_MIN_SIMILARITY:
                    continue

                try:
                    price = self._extract_price_from_kroger_payload(candidate)
                except ExternalAPIError:
                    continue

                remapped = False
                if (
                    not locked_override_id
                    and candidate_id
                    and candidate_id != product.kroger_product_id
                ):
                    product.kroger_product_id = candidate_id
                    image_url = self._extract_image_from_search_candidate(candidate)
                    if image_url:
                        product.image_url = image_url
                    logger.info(
                        "Fallback mapped product id=%s to Kroger id=%s using priced candidate",
                        product.id,
                        candidate_id,
                    )
                    remapped = True

                if remapped or (candidate_id and candidate_id == product.kroger_product_id):
                    self._apply_kroger_metadata_labels(product, candidate)
                return price
        return None

    async def _fetch_price_with_retries(
        self,
        product: Product,
        kroger: KrogerService,
        retries: int = 3,
    ) -> Decimal:
        for attempt in range(retries):
            try:
                payload = await self._resolve_kroger_product(product, kroger)
                try:
                    return self._extract_price_from_kroger_payload(payload)
                except ExternalAPIError:
                    fallback_price = await self._fallback_price_from_search_candidates(product, kroger)
                    if fallback_price is not None:
                        return fallback_price
                    raise
            except (KrogerAPIError, KrogerRateLimitError, ExternalAPIError, ValueError) as exc:
                if self._is_unmatched_product_error(exc) and hasattr(kroger, "search_products"):
                    try:
                        fallback_price = await self._fallback_price_from_search_candidates(product, kroger)
                    except (AttributeError, KrogerAPIError, KrogerRateLimitError, ValueError) as fallback_exc:
                        logger.warning(
                            "Fallback search failed for product id=%s after unmatched error: %s",
                            product.id,
                            fallback_exc,
                        )
                    else:
                        if fallback_price is not None:
                            return fallback_price

                is_last_attempt = attempt == retries - 1
                skip_unmatched_retries = (
                    settings.KROGER_SKIP_UNMATCHED_RETRIES and self._is_unmatched_product_error(exc)
                )
                if is_last_attempt or skip_unmatched_retries:
                    if isinstance(exc, ExternalAPIError):
                        raise exc
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

        # Always persist a daily snapshot point so 7/30-day history can build
        # even when today's fetched price matches yesterday's.
        product.add_price_to_history(
            new_price,
            datetime.now(timezone.utc).isoformat(),
            source="kroger_api",
        )

        product.current_price = new_price
        product.last_price_check = datetime.now(timezone.utc)
        product.calculate_health_score()

        self._commit_refresh_or_raise(product)
        try:
            PriceAlertService(self.db).check_and_log_triggered_alerts(
                product_id=product.id,
                current_price=new_price,
            )
        except Exception as exc:  # pragma: no cover - alert checks should not fail price updates
            logger.warning("Alert check failed for product id=%s: %s", product.id, exc)
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
