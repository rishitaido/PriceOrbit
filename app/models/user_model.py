"""
User SQLAlchemy model for authentication.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.db.base import Base


class User(Base):
    """
    ORM model representing an application user.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    full_name = Column(String(200), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<User(id={self.id}, email='{self.email}', is_active={self.is_active})>"
