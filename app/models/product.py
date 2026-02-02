"""
Product SQLAlchemy model for database operations
Represents grocery items tracked in PriceOrbit
"""
from sqlalchemy import Column, Integer, String, DECIMAL, DateTime, JSON, Text
from sqlalchemy.sql import func
from app.db.base import Base
from decimal import Decimal


class Product(Base):
    """
    Product model representing tracked grocery items
    
    Health Score Calculation (Sprint 1 - Stub):
    - Returns fixed value of 50.0
    - Full algorithm to be implemented in Sprint 2
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
        Calculate health score based on multiple factors
        
        Sprint 1 Implementation: Returns stub value of 50.0
        
        Sprint 2+ Full Algorithm (TODO):
        Factors to consider:
        - Tariff exposure (higher tariff = lower score)
        - Price volatility (more volatile = lower score)
        - Import dependency (higher dependency = lower score)
        - Recent price trends (upward trend = lower score)
        
        Formula (future):
        health_score = 100 - (
            (tariff_weight * tariff_factor) +
            (volatility_weight * volatility_factor) +
            (dependency_weight * dependency_factor) +
            (trend_weight * trend_factor)
        )
        
        Returns:
            Decimal: Health score between 0-100
        """
        # Sprint 1: Stub implementation
        self.health_score = Decimal("50.0")
        return self.health_score
    
    def add_price_to_history(self, price: Decimal, date: str = None):
        """
        Add a price point to price history
        
        Args:
            price: Price value
            date: Date string (ISO format), defaults to now
        """
        from datetime import datetime
        
        if date is None:
            date = datetime.now().isoformat()
        
        if self.price_history is None:
            self.price_history = []
        
        price_entry = {
            "date": date,
            "price": float(price)
        }
        
        self.price_history.append(price_entry)