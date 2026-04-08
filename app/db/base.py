"""
SQLAlchemy Base class for all models
Import all models here to ensure they're registered with Base
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
