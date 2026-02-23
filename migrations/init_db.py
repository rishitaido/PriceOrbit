"""
Database initialization script
Creates all tables defined in SQLAlchemy models
Run this script to set up the database schema
FOR DEV / TEST ONLY

This script force-resets the database and bypasses Alembic migrations.
After running this script, you MUST run:

    alembic stamp head
"""
import sys
from pathlib import Path
# importlib was previously included but isn't needed anymore
# from app.models import product  # models are imported below when needed

# Add parent directory to path to import app modules
sys.path.append(str(Path(__file__).parent.parent))

from app.db.base import Base
from app.db.session import engine
from app.core.config import settings

# explicit import so `init_database` can reference Product
from app.models.product import Product


def init_database():
    """
    Initialize database by creating all tables
    WARNING: This will drop all existing tables first!
    """
    print("=" * 60)
    print("PriceOrbit Database Initialization")
    print("=" * 60)
    _ = Product  # Ensure model is loaded for Base metadata registration
    print(f"\nDatabase: {settings.MYSQL_DATABASE}")
    print(f"Host: {settings.MYSQL_HOST}:{settings.MYSQL_PORT}")
    print(f"User: {settings.MYSQL_USER}")
    
    # Confirm before proceeding
    response = input("\n⚠️  This will DROP all existing tables. Continue? (yes/no): ")
    if response.lower() != "yes":
        print("❌ Initialization cancelled.")
        return
    
    print("\n🗑️  Dropping existing tables...")
    Base.metadata.drop_all(bind=engine)
    print("✅ Existing tables dropped")
    
    print("\n🔨 Creating all tables...")
    Base.metadata.create_all(bind=engine)
    print("✅ All tables created successfully!")
    
    print(f"\n📊 Tables created: {list(Base.metadata.tables.keys())}")
    print("\n" + "=" * 60)
    print("✨ Database initialization complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Run seed script to populate products: python migrations/seed_products.py")
    print("2. Start the application: uvicorn main:app --reload")
    print("3. View API docs: http://localhost:8000/docs")


if __name__ == "__main__":
    init_database()
