"""
Database session management with dependency injection
Provides database session to FastAPI routes
"""

from sqlalchemy import create_engine 
from sqlalchemy.orm import sessionmaker, Session 
from app.core.config import settings 
from typing import Generator 

#Create SQL engine 
# echo=True logs all SQL statements (useful for debugging)

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True, #Verify connections before using them 
    pool_size= 10,
    max_overflow= 20
)

SessionLocal = sessionmaker(
    autocommit = False, 
    autoflush=False,
    bind=engine
)

def get_db() -> Generator[Session, None, None]: 
    """
    Dependency function that yields database sessions
    
    Usage in routes:
        @router.get("/products")
        def get_products(db: Session = Depends(get_db)):
            ...
    
    Yields:
        Database session that automatically closes after use
    """
    db = SessionLocal()
    try: 
        yield db
    finally: 
        db.close

        
    