"""
Pydantic schemas for Product model
Used for API validation and response serialization
"""
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, List, Dict, Any, Literal
from decimal import Decimal
from datetime import datetime


class PriceHistoryEntry(BaseModel):
    """Single entry in price history"""
    date: str = Field(..., description="ISO format date string")
    price: float = Field(..., ge=0, description="Price value")
    source: Optional[str] = Field(None, description="Origin of this point (e.g., kroger_api)")


class ProductBase(BaseModel):
    """
    Base product schema with common fields
    Shared between Create and Update operations
    """
    name: str = Field(..., min_length=1, max_length=200, description="Product name")
    category: str = Field(..., min_length=1, max_length=100, description="Product category")
    retailer: str = Field(default="Kroger", max_length=100, description="Retailer name")
    description: Optional[str] = Field(None, description="Product description")
    current_price: Optional[Decimal] = Field(None, ge=0, description="Current price in USD")
    tariff_rate: Decimal = Field(default=0.0, ge=0, le=100, description="Tariff rate percentage")
    import_dependency: str = Field(
        default="Unknown",
        description="Import dependency level: High, Medium, Low, Unknown"
    )
    hts_code: Optional[str] = Field(None, max_length=20, description="Harmonized Tariff Schedule code")
    origin_country: Optional[str] = Field(None, max_length=100, description="Primary import country")
    rate_type: Literal["ad_valorem", "specific", "mixed", "duty_free"] = Field(
        default="duty_free",
        description="Tariff rate type",
    )
    specific_duty_value: Optional[str] = Field(
        None,
        max_length=100,
        description="Specific duty value when rate_type is specific or mixed",
    )
    source_url: Optional[str] = Field(None, max_length=500, description="Tariff source URL")
    verification_source: Optional[str] = Field(None, max_length=100, description="Verification source label")
    verification_notes: Optional[str] = Field(None, description="Verification notes and rationale")
    verified_at: Optional[datetime] = Field(None, description="Timestamp when tariff metadata was verified")
    confidence_score: Decimal = Field(default=0.0, ge=0, le=100, description="Tariff confidence score")
    review_status: Literal["incomplete", "needs_review", "verified", "manual_override"] = Field(
        default="incomplete",
        description="Tariff review status",
    )
    manual_tariff_override: bool = Field(
        default=False,
        description="When true, automation will not overwrite tariff fields unless forced.",
    )
    kroger_product_id: Optional[str] = Field(None, max_length=100, description="Kroger API product ID")
    image_url: Optional[str] = Field(None, max_length=500, description="Product image URL")


class ProductCreate(ProductBase):
    """
    Schema for creating a new product
    Inherits all fields from ProductBase
    """
    pass


class ProductUpdate(BaseModel):
    """
    Schema for updating an existing product
    All fields are optional for partial updates
    """
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    category: Optional[str] = Field(None, min_length=1, max_length=100)
    retailer: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    current_price: Optional[Decimal] = Field(None, ge=0)
    tariff_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    import_dependency: Optional[str] = None
    hts_code: Optional[str] = Field(None, max_length=20)
    origin_country: Optional[str] = Field(None, max_length=100)
    rate_type: Optional[Literal["ad_valorem", "specific", "mixed", "duty_free"]] = None
    specific_duty_value: Optional[str] = Field(None, max_length=100)
    source_url: Optional[str] = Field(None, max_length=500)
    verification_source: Optional[str] = Field(None, max_length=100)
    verification_notes: Optional[str] = None
    verified_at: Optional[datetime] = None
    confidence_score: Optional[Decimal] = Field(None, ge=0, le=100)
    review_status: Optional[Literal["incomplete", "needs_review", "verified", "manual_override"]] = None
    manual_tariff_override: Optional[bool] = None
    kroger_product_id: Optional[str] = Field(None, max_length=100)
    image_url: Optional[str] = Field(None, max_length=500)


class ProductResponse(ProductBase):
    """
    Schema for product API responses
    Includes all fields plus computed/database-managed fields
    """
    id: int = Field(..., description="Product ID")
    health_score: Decimal = Field(..., ge=0, le=100, description="Health score (0-100)")
    price_history: List[PriceHistoryEntry] = Field(default_factory=list, description="Historical prices")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    last_price_check: Optional[datetime] = Field(None, description="Last price check timestamp")
    
    model_config = ConfigDict(from_attributes=True)  # Allows conversion from SQLAlchemy models

    @field_validator("price_history", mode="before")
    @classmethod
    def _coerce_price_history(cls, value: Any) -> List[dict]:
        # Legacy rows may store NULL; API contract always returns a list.
        return value or []


class ProductListResponse(BaseModel):
    """
    Schema for paginated product list responses
    """
    products: List[ProductResponse]
    total: int = Field(..., description="Total number of products")
    page: int = Field(default=1, ge=1, description="Current page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")
    
    model_config = ConfigDict(from_attributes=True)


class PricePointCreate(BaseModel):
    """
    Request body for POST /api/products/{id}/add-price-point.

    When ``date`` is omitted or equals today, the endpoint performs a
    full live-price update (archives old current_price, sets new
    current_price, updates last_price_check).

    When ``date`` is a past ISO-8601 date string (``YYYY-MM-DD``), the
    entry is back-filled into price_history without touching
    current_price — useful for importing historical data.
    """

    price: Decimal = Field(
        ...,
        gt=0,
        description="New price value (must be > 0).",
    )
    date: Optional[str] = Field(
        None,
        description="ISO-8601 date (YYYY-MM-DD). Defaults to today.",
        examples=["2025-03-15"],
    )


class PriceHistoryResponse(BaseModel):
    """Response schema for product price history endpoint."""

    product_id: int
    product_name: str
    current_price: Optional[float]
    history: List[PriceHistoryEntry] = Field(default_factory=list)
    statistics: Dict[str, Any]


class ProductStorePriceEntry(BaseModel):
    """Store-specific price entry for a single product."""

    store_id: int
    store_name: str
    kroger_location_id: Optional[str] = None
    price: Optional[Decimal] = None
    last_updated: Optional[datetime] = None
    source: str = Field(
        ...,
        description="Data source for the price value: kroger_api, database, or unavailable",
    )
    distance: Optional[float] = None


class ProductStorePriceListResponse(BaseModel):
    """Response schema for product prices across stores."""

    product_id: int
    product_name: str
    prices: List[ProductStorePriceEntry] = Field(default_factory=list)


class PriceUpdateResponse(BaseModel):
    """Response schema for single-product automated price updates."""

    product_id: int
    product_name: str
    old_price: Optional[Decimal]
    new_price: Decimal
    price_change: Optional[float]
    old_health_score: Decimal
    new_health_score: Decimal
    updated_at: datetime
    source: str = "kroger_api"


class BatchPriceUpdateResponse(BaseModel):
    """Response schema for batch automated price updates."""

    processed: int
    updated: int
    failed: int
    results: List[PriceUpdateResponse] = Field(default_factory=list)
    errors: List[Dict[str, Any]] = Field(default_factory=list)


class TariffResolutionResponse(BaseModel):
    """Response schema for single-product tariff automation runs."""

    product_id: int
    product_name: str
    matched: bool
    updated: bool
    skipped: bool = False
    reason: Optional[str] = None
    match_strategy: str
    tariff_rate: Optional[Decimal] = None
    rate_type: Optional[str] = None
    hts_code: Optional[str] = None
    origin_country: Optional[str] = None
    import_dependency: Optional[str] = None
    confidence_score: Decimal = Field(default=0, ge=0, le=100)
    review_status: str
    verification_source: Optional[str] = None
    verified_at: Optional[datetime] = None


class BatchTariffResolutionResponse(BaseModel):
    """Response schema for batch tariff automation runs."""

    processed: int
    updated: int
    matched: int
    unmatched: int
    skipped: int
    results: List[TariffResolutionResponse] = Field(default_factory=list)


class HealthScoreColor(BaseModel):
    """Helper schema for health score color coding"""
    score: Decimal
    color: str = Field(..., description="Color: green, yellow, or red")
    label: str = Field(..., description="Label: Good, Caution, or Risk")
    
    @classmethod
    def from_score(cls, score: Decimal):
        """
        Determine color and label based on health score
        
        Args:
            score: Health score (0-100)
        
        Returns:
            HealthScoreColor instance
        """
        if score >= 70:
            return cls(score=score, color="green", label="Good")
        elif score >= 40:
            return cls(score=score, color="yellow", label="Caution")
        else:
            return cls(score=score, color="red", label="Risk")
