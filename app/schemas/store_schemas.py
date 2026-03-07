"""
Pydantic schemas for Store model.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class StoreBase(BaseModel):
    """Base schema shared by store responses."""

    name: str = Field(..., min_length=1, max_length=200, description="Store name")
    address: str = Field(..., min_length=1, max_length=255, description="Street address")
    city: str = Field(..., min_length=1, max_length=100, description="City name")
    state: str = Field(..., min_length=2, max_length=2, description="Two-letter state code")
    zip_code: str = Field(..., min_length=5, max_length=10, description="ZIP code")
    kroger_location_id: Optional[str] = Field(
        None,
        max_length=20,
        description="Kroger location ID used for store-specific price queries",
    )
    latitude: float = Field(..., ge=-90, le=90, description="Latitude")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude")
    phone: Optional[str] = Field(None, max_length=25, description="Store phone number")
    hours: Optional[str] = Field(None, description="Store operating hours")


class StoreResponse(StoreBase):
    """Store schema used for API responses."""

    id: int = Field(..., description="Store ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = ConfigDict(from_attributes=True)


class StoreListResponse(BaseModel):
    """Schema for store list responses."""

    stores: List[StoreResponse]
    total: int = Field(..., description="Total number of stores")
    page: int = Field(default=1, ge=1, description="Current page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")


class NearbyStoreResponse(StoreResponse):
    """Store response that includes distance from query point."""

    distance_miles: float = Field(..., ge=0, description="Distance in miles from query point")
