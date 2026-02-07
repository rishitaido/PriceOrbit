"""
SQLAlchemy Base class for all models
Import all models here to ensure they're registered with Base
"""
from sqlalchemy.ext.declarative import declarative_base

# Create Base class for all models
Base = declarative_base()