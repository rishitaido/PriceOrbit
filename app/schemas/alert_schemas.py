"""
Pydantic schemas for price alert endpoints.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PriceAlertCreate(BaseModel):
    """Request body for creating/updating a price alert."""

    product_id: int = Field(..., ge=1)
    target_price: Decimal = Field(..., gt=0)
    is_active: bool = True


class PriceAlertResponse(BaseModel):
    """API response payload for a user price alert."""

    id: int
    user_id: int
    product_id: int
    product_name: str
    target_price: Decimal
    current_price: Optional[Decimal] = None
    is_active: bool
    triggered: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PriceAlertListResponse(BaseModel):
    """Paginated-like list response for user alerts."""

    alerts: list[PriceAlertResponse]
    total: int

