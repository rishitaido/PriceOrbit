"""
Product SQLAlchemy model for database operations.
Represents grocery items tracked in PriceOrbit.
"""
import logging
import statistics
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from typing import List

from sqlalchemy import Column, Integer, String, DECIMAL, DateTime, JSON, Text
from sqlalchemy.sql import func

from app.db.base import Base

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
    
    # ------------------------------------------------------------------
    # Health Score constants
    # ------------------------------------------------------------------
    _MAX_TARIFF_RATE: float = 25.0   # Tariff % that maps to maximum penalty
    _MAX_TARIFF_PENALTY: float = 40.0
    _MAX_DEPENDENCY_PENALTY: float = 30.0
    _MAX_VOLATILITY_PENALTY: float = 30.0
    _MIN_HISTORY_FOR_VOLATILITY: int = 3  # Minimum price-history points needed
    _DEPENDENCY_PENALTIES = {
        "Low": 0.0,
        "Medium": 15.0,
        "High": 30.0,
        "Unknown": 10.0,
    }

    def _calculate_volatility_penalty(self) -> float:
        """
        Derive a price-volatility penalty (0–30) from price_history.

        Uses the coefficient of variation (CV = std_dev / mean) as a
        normalised measure of volatility.  A CV of 0 means perfectly
        stable prices (penalty = 0); a CV of ≥ 1 is treated as maximum
        volatility (penalty = 30).

        Returns 0 when fewer than ``_MIN_HISTORY_FOR_VOLATILITY`` data
        points are available, because a standard deviation from one or
        two points is statistically unreliable.

        Returns:
            Float in [0.0, 30.0].
        """
        history: List[dict] = self.price_history or []
        prices = [entry["price"] for entry in history if "price" in entry]

        if len(prices) < self._MIN_HISTORY_FOR_VOLATILITY:
            logger.debug(
                "Product id=%s: only %d price points — volatility penalty = 0",
                self.id,
                len(prices),
            )
            return 0.0

        mean_price = statistics.mean(prices)
        if mean_price == 0:
            return 0.0

        std_dev = statistics.stdev(prices)
        cv = std_dev / mean_price  # coefficient of variation

        # CV ≥ 1 → max penalty; CV of 0 → no penalty
        cv_clamped = min(cv, 1.0)
        penalty = cv_clamped * self._MAX_VOLATILITY_PENALTY

        logger.debug(
            "Product id=%s: volatility cv=%.4f penalty=%.2f",
            self.id,
            cv,
            penalty,
        )
        return penalty

    def calculate_health_score(self) -> Decimal:
        """
        Calculate and persist the supply-chain health score (0–100).

        A higher score means lower risk. Three factors contribute:

        **Tariff penalty (0–40 pts)**
            ``(tariff_rate / 25.0) * 40``
            Assumes 25 % is the practical maximum tariff rate.
            Clamped so rates above 25 % still yield at most 40 pts.

        **Import-dependency penalty (0–30 pts)**
            Mapped from the ``import_dependency`` field:
            Low → 0, Medium → 15, High → 30, Unknown → 10.

        **Price-volatility penalty (0–30 pts)**
            Derived from the coefficient of variation of ``price_history``.
            Requires at least 3 historical price points; otherwise 0.

        Final score: ``max(0, min(100, 100 − penalties))``

        The computed value is written to ``self.health_score`` so callers
        can flush it to the database with a single ``session.commit()``.

        Returns:
            Decimal: Health score rounded to 2 decimal places, in [0, 100].
        """
        logger.info("Calculating health score for product id=%s name='%s'", self.id, self.name)

        # ---- Tariff penalty (40 % weight) --------------------------------
        tariff_rate = float(self.tariff_rate or 0)
        tariff_penalty = min(
            (tariff_rate / self._MAX_TARIFF_RATE) * self._MAX_TARIFF_PENALTY,
            self._MAX_TARIFF_PENALTY,
        )

        # ---- Import-dependency penalty (30 % weight) ---------------------
        dependency_key = (self.import_dependency or "Unknown").strip().capitalize()
        # Normalise to title-case so "low", "LOW", "Low" all match
        dependency_key = dependency_key if dependency_key in self._DEPENDENCY_PENALTIES else "Unknown"
        dependency_penalty = self._DEPENDENCY_PENALTIES[dependency_key]

        # ---- Price-volatility penalty (30 % weight) ----------------------
        volatility_penalty = self._calculate_volatility_penalty()

        # ---- Combine and clamp -------------------------------------------
        raw_score = 100.0 - tariff_penalty - dependency_penalty - volatility_penalty
        final_score = max(0.0, min(100.0, raw_score))

        self.health_score = Decimal(str(final_score)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        logger.info(
            "Product id=%s health_score=%.2f "
            "(tariff_penalty=%.2f dependency_penalty=%.2f volatility_penalty=%.2f)",
            self.id,
            final_score,
            tariff_penalty,
            dependency_penalty,
            volatility_penalty,
        )
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