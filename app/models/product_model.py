"""
Product SQLAlchemy model for database operations.
Represents grocery items tracked in PriceOrbit.
"""
import logging
from decimal import Decimal
from datetime import datetime

from sqlalchemy import Column, Integer, String, DECIMAL, DateTime, JSON, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.services.health_score_service import HealthScoreService

logger = logging.getLogger(__name__)

class Product(Base):
    """
    ORM model representing a tracked grocery item in PriceOrbit.

    Health Score (0–100) reflects supply-chain risk derived from three
    weighted factors: tariff rate (40%), import dependency (30%), and
    price volatility (30%).  Call ``calculate_health_score()`` and then
    commit the session to persist an updated value.
    """
    __tablename__ = "products"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    # Basic Product Information
    name = Column(String(200), nullable=False, index=True)
    category = Column(String(100), nullable=False, index=True)
    retailer = Column(String(100), default="Kroger", nullable=False)
    description = Column(Text, nullable=True)
    
    # Pricing Information
    current_price = Column(DECIMAL(10, 2), nullable=True)
    price_history = Column(JSON, default=list)  # Store as JSON array: [{"date": "2025-01-27", "price": 3.99}, ...]
    
    # Supply Chain Factors
    tariff_rate = Column(DECIMAL(5, 2), default=0.0, nullable=False)  # Percentage (e.g., 15.5 = 15.5%)
    import_dependency = Column(
        String(50), 
        default="Unknown",
        nullable=False
    )  # Values: "High", "Medium", "Low", "Unknown"
    
    hts_code = Column(String(20), nullable=True)  # Harmonized Tariff Schedule code
    origin_country = Column(String(100), nullable=True)  # Primary import country
    
    # Health Score (0-100)
    health_score = Column(DECIMAL(5, 2), default=50.0, nullable=False)
    
    # Metadata
    kroger_product_id = Column(String(100), nullable=True, unique=True)  # Kroger API product ID
    image_url = Column(String(500), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        onupdate=func.now(),
        nullable=False
    )
    last_price_check = Column(DateTime(timezone=True), nullable=True)
    store_prices = relationship(
        "ProductStorePrice",
        back_populates="product",
        cascade="all, delete-orphan",
    )
    
    def __repr__(self):
        """String representation for debugging"""
        price_str = f"${self.current_price}" if self.current_price else "N/A"
        return f"<Product(id={self.id}, name='{self.name}', price={price_str}, health_score={self.health_score})>"
    
    def to_dict(self):
        """
        Convert model to dictionary for JSON serialization
        
        Returns:
            Dictionary with all product fields
        """
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "retailer": self.retailer,
            "description": self.description,
            "current_price": float(self.current_price) if self.current_price else None,
            "price_history": self.price_history or [],
            "tariff_rate": float(self.tariff_rate),
            "import_dependency": self.import_dependency,
            "hts_code": self.hts_code,
            "origin_country": self.origin_country,
            "health_score": float(self.health_score),
            "kroger_product_id": self.kroger_product_id,
            "image_url": self.image_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_price_check": self.last_price_check.isoformat() if self.last_price_check else None,
        }
    
    def calculate_health_score(self) -> Decimal:
        """
        Calculate and store product health score using HealthScoreService.

        Returns:
            Decimal: Health score rounded to 2 decimal places, in [0, 100].
        """
        logger.info("Calculating health score for product id=%s name='%s'", self.id, self.name)
        self.health_score = HealthScoreService.calculate_health_score(self)
        logger.info("Product id=%s health_score=%.2f", self.id, float(self.health_score))
        return self.health_score
    
    def add_price_to_history(self, price: Decimal, date: str = None):
        """
        Add a price point to price history
        
        Args:
            price: Price value
            date: Date string (ISO format), defaults to now
        """
        if date is None:
            date = datetime.now().isoformat()
        
        # Initialize price_history if None
        if self.price_history is None:
            self.price_history = []
        
        price_entry = {
            "date": date,
            "price": float(price)
        }
        
        # Avoid duplicate entries for same date
        # Remove existing entry for this date if it exists
        self.price_history = [
            entry for entry in self.price_history 
            if entry.get("date", "").split("T")[0] != date.split("T")[0]
        ]
        
        # Add new entry
        self.price_history.append(price_entry)
        
        # Keep only last 365 days of history (optional)
        # Sort by date and keep most recent
        self.price_history.sort(key=lambda x: x["date"], reverse=True)
        if len(self.price_history) > 365:
            self.price_history = self.price_history[:365]
