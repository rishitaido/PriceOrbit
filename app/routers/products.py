from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.product import Product
from app.schemas.product import ProductResponse

router = APIRouter()

@router.get("/", response_model=list[ProductResponse])
def get_products(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    """
    Fetch products from the database for the frontend dashboard.
    """
    products = db.query(Product).offset(skip).limit(limit).all()
    return products