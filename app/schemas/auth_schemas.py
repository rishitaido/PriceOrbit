"""
Pydantic schemas for authentication endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserRegister(BaseModel):
    """Schema for user registration requests."""

    email: str
    password: str = Field(..., min_length=8, max_length=128)
    full_name: Optional[str] = Field(None, max_length=200)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("email must be a valid address")
        return normalized


class UserLogin(BaseModel):
    """Schema for user login requests."""

    email: str
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("email must be a valid address")
        return normalized


class UserResponse(BaseModel):
    """Schema for user responses."""

    id: int
    email: str
    full_name: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    """Schema for successful authentication responses."""

    access_token: str
    token_type: str = "bearer"


class AuthSuccessResponse(BaseModel):
    """Login response including access token and user details."""

    token: TokenResponse
    user: UserResponse
