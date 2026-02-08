from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.models.product import Product

def create_product(db: Session, data: dict):
    if not data.get("name"):
        raise ValueError("Product name is required")

    if not data.get("category"):
        raise ValueError("Product category is required")

    product = Product(
        name=data["name"],
        category=data["category"],
        import_dependency=data.get("import_dependency", "Unknown"),
        retailer=data.get("retailer", "Kroger"),
    )

    try:
        db.add(product)
        db.commit()
        db.refresh(product)
        return product
    except SQLAlchemyError as e:
        db.rollback()
        raise RuntimeError("Failed to create product") from e

def get_product(db: Session, product_id: int):
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise ValueError("Product not found")

    return product

def get_all_products(db: Session):
    return db.query(Product).all()

def update_product(db: Session, product_id: int, data: dict):
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise ValueError("Product not found")

    for field, value in data.items():
        if hasattr(product, field):
            setattr(product, field, value)

    try:
        db.commit()
        db.refresh(product)
        return product
    except SQLAlchemyError as e:
        db.rollback()
        raise RuntimeError("Failed to update product") from e

def delete_product(db: Session, product_id: int):
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise ValueError("Product not found")

    try:
        db.delete(product)
        db.commit()
        return True
    except SQLAlchemyError as e:
        db.rollback()
        raise RuntimeError("Failed to delete product") from e