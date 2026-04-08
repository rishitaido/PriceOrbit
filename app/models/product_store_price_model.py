"""
Product-store price join model for location-specific pricing.
"""

from __future__ import annotations

from sqlalchemy import DECIMAL, Column, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class ProductStorePrice(Base):
    """
    ORM model storing the latest known product price for a specific store.
    """

    __tablename__ = "product_store_prices"
    __table_args__ = (UniqueConstraint("product_id", "store_id", name="uq_product_store_price"),)

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True)
    price = Column(DECIMAL(10, 2), nullable=False)
    last_updated = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True,
    )
    product = relationship("Product", back_populates="store_prices")
    store = relationship("Store", back_populates="product_prices")

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<ProductStorePrice(id={self.id}, product_id={self.product_id}, "
            f"store_id={self.store_id}, price={self.price})>"
        )
