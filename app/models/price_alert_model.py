"""
Price alert SQLAlchemy model.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DECIMAL, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base import Base


class PriceAlert(Base):
    """
    ORM model storing a user's target price alert for a product.
    """

    __tablename__ = "price_alerts"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_price_alert_user_product"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    target_price = Column(DECIMAL(10, 2), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<PriceAlert(id={self.id}, user_id={self.user_id}, product_id={self.product_id}, "
            f"target_price={self.target_price}, is_active={self.is_active})>"
        )

