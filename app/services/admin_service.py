"""
Admin dashboard service layer.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.product_model import Product
from app.models.store_model import Store


class AdminService:
    """Business logic for admin dashboard metrics."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _get_recent_price_updates(self, limit: int = 10) -> list[dict[str, Any]]:
        rows = (
            self.db.query(
                Product.id,
                Product.name,
                Product.current_price,
                Product.last_price_check,
            )
            .filter(Product.last_price_check.isnot(None))
            .order_by(Product.last_price_check.desc())
            .limit(max(1, min(limit, 50)))
            .all()
        )

        return [
            {
                "product_id": row.id,
                "product_name": row.name,
                "current_price": float(row.current_price) if row.current_price is not None else None,
                "last_price_check": row.last_price_check.isoformat()
                if row.last_price_check
                else None,
            }
            for row in rows
        ]

    def _get_stale_product_count(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, settings.PRICE_UPDATE_STALE_HOURS))
        return (
            self.db.query(func.count(Product.id))
            .filter(
                (Product.last_price_check.is_(None))
                | (Product.last_price_check < cutoff)
            )
            .scalar()
            or 0
        )

    def get_dashboard_metrics(self, *, scheduler_snapshot: dict[str, Any]) -> dict[str, Any]:
        total_products = self.db.query(func.count(Product.id)).scalar() or 0
        total_stores = self.db.query(func.count(Store.id)).scalar() or 0

        last_run_result = scheduler_snapshot.get("last_run_result") or {}
        failed_api_calls = int(last_run_result.get("failed") or 0)
        stale_products = self._get_stale_product_count()

        system_health = "healthy"
        if scheduler_snapshot.get("running"):
            system_health = "updating"
        elif failed_api_calls > 0 or stale_products > 0:
            system_health = "degraded"

        return {
            "total_products": int(total_products),
            "total_stores": int(total_stores),
            "failed_api_calls": failed_api_calls,
            "system_health": system_health,
            "stale_products": stale_products,
            "scheduler_enabled": bool(scheduler_snapshot.get("scheduler_enabled", False)),
            "scheduler_running": bool(scheduler_snapshot.get("running", False)),
            "next_run_utc": scheduler_snapshot.get("next_run_utc"),
            "last_run_started_at": scheduler_snapshot.get("last_run_started_at"),
            "last_run_finished_at": scheduler_snapshot.get("last_run_finished_at"),
            "recent_price_updates": self._get_recent_price_updates(limit=10),
        }

