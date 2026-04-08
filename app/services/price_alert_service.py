"""
Price alert service layer.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.models.price_alert_model import PriceAlert
from app.models.product_model import Product
from app.schemas.alert_schemas import PriceAlertCreate

logger = logging.getLogger(__name__)


class PriceAlertService:
    """Business logic for user price alerts."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _commit_or_raise(self) -> None:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ValidationError(
                "Database integrity error while saving alert.",
                details={"error": str(exc.orig) if exc.orig else str(exc)},
            ) from exc
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise ValidationError(
                "Database operation failed while saving alert.",
                details={"error": str(exc)},
            ) from exc

    def _get_product_or_raise(self, product_id: int) -> Product:
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise NotFoundError("Product", product_id)
        return product

    @staticmethod
    def _is_triggered(*, current_price: Decimal | None, target_price: Decimal) -> bool:
        if current_price is None:
            return False
        return Decimal(current_price) <= Decimal(target_price)

    def _serialize_alert(self, alert: PriceAlert, product: Product) -> dict[str, Any]:
        current_price = product.current_price
        return {
            "id": alert.id,
            "user_id": alert.user_id,
            "product_id": alert.product_id,
            "product_name": product.name,
            "target_price": alert.target_price,
            "current_price": current_price,
            "is_active": alert.is_active,
            "triggered": bool(
                alert.is_active
                and self._is_triggered(current_price=current_price, target_price=alert.target_price)
            ),
            "created_at": alert.created_at,
            "updated_at": alert.updated_at,
        }

    def create_or_update_alert(self, *, user_id: int, payload: PriceAlertCreate) -> dict[str, Any]:
        product = self._get_product_or_raise(payload.product_id)

        alert = (
            self.db.query(PriceAlert)
            .filter(
                PriceAlert.user_id == user_id,
                PriceAlert.product_id == payload.product_id,
            )
            .first()
        )

        if alert is None:
            alert = PriceAlert(
                user_id=user_id,
                product_id=payload.product_id,
                target_price=payload.target_price,
                is_active=payload.is_active,
            )
            self.db.add(alert)
        else:
            alert.target_price = payload.target_price
            alert.is_active = payload.is_active

        self._commit_or_raise()
        self.db.refresh(alert)
        return self._serialize_alert(alert, product)

    def list_alerts_for_user(self, *, user_id: int, active_only: bool | None = None) -> list[dict[str, Any]]:
        query = (
            self.db.query(PriceAlert, Product)
            .join(Product, Product.id == PriceAlert.product_id)
            .filter(PriceAlert.user_id == user_id)
        )
        if active_only is True:
            query = query.filter(PriceAlert.is_active.is_(True))
        elif active_only is False:
            query = query.filter(PriceAlert.is_active.is_(False))

        rows = query.order_by(PriceAlert.created_at.desc()).all()
        return [self._serialize_alert(alert, product) for alert, product in rows]

    def delete_alert(self, *, user_id: int, alert_id: int) -> None:
        alert = (
            self.db.query(PriceAlert)
            .filter(
                PriceAlert.id == alert_id,
                PriceAlert.user_id == user_id,
            )
            .first()
        )
        if alert is None:
            raise NotFoundError("PriceAlert", alert_id)

        self.db.delete(alert)
        self._commit_or_raise()

    def check_and_log_triggered_alerts(
        self,
        *,
        product_id: int,
        current_price: Decimal,
    ) -> list[dict[str, Any]]:
        """
        Return and log all active alerts triggered by a fresh product price.
        """
        alerts = (
            self.db.query(PriceAlert)
            .filter(
                PriceAlert.product_id == product_id,
                PriceAlert.is_active.is_(True),
                PriceAlert.target_price >= current_price,
            )
            .all()
        )

        triggered: list[dict[str, Any]] = []
        for alert in alerts:
            payload = {
                "alert_id": alert.id,
                "user_id": alert.user_id,
                "product_id": alert.product_id,
                "target_price": str(alert.target_price),
                "current_price": str(current_price),
            }
            triggered.append(payload)
            logger.info(
                "PRICE ALERT TRIGGERED user_id=%s alert_id=%s product_id=%s target=%s current=%s",
                alert.user_id,
                alert.id,
                alert.product_id,
                alert.target_price,
                current_price,
            )
        return triggered

