"""
Store SQLAlchemy model for grocery store locations.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Store(Base):
    """
    ORM model representing a physical store location.
    """

    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(200), nullable=False, index=True)
    address = Column(String(255), nullable=False)
    city = Column(String(100), nullable=False, index=True)
    state = Column(String(2), nullable=False, index=True)
    zip_code = Column(String(10), nullable=False, index=True)
    kroger_location_id = Column(String(20), nullable=True, unique=True, index=True)
    latitude = Column(Float, nullable=False, index=True)
    longitude = Column(Float, nullable=False, index=True)
    phone = Column(String(25), nullable=True)
    hours = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    product_prices = relationship(
        "ProductStorePrice",
        back_populates="store",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<Store(id={self.id}, name='{self.name}', city='{self.city}', "
            f"state='{self.state}', zip='{self.zip_code}')>"
        )

    def to_dict(self) -> dict:
        """
        Convert model to dictionary for JSON serialization.
        """
        return {
            "id": self.id,
            "name": self.name,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "zip_code": self.zip_code,
            "kroger_location_id": self.kroger_location_id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "phone": self.phone,
            "hours": self.hours,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
