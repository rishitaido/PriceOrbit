import pytest
import os
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import NotFoundError
from app.schemas.product import ProductCreate, ProductUpdate
from app.services.product_service import ProductService


pytestmark = pytest.mark.skipif(
    os.getenv("CI") == "true",
    reason="Requires MySQL database"
)


def make_service(db):
    return ProductService(db)


def test_create_product(db):
    service = make_service(db)
    product = service.create_product(
        ProductCreate(
            name="Test Milk",
            category="Dairy",
        )
    )

    assert product.id is not None
    assert product.name == "Test Milk"
    assert product.category == "Dairy"


def test_create_product_missing_name(db):
    service = make_service(db)
    with pytest.raises(PydanticValidationError):
        service.create_product(
            ProductCreate(
                category="Dairy",
            )
        )


def test_get_product(db):
    service = make_service(db)
    product = service.create_product(
        ProductCreate(
            name="Test Bread",
            category="Bakery",
        )
    )

    fetched = service.get_product_by_id(product.id)
    assert fetched.id == product.id


def test_get_product_not_found(db):
    service = make_service(db)
    with pytest.raises(NotFoundError):
        service.get_product_by_id(999999)


def test_get_all_products(db):
    service = make_service(db)
    service.create_product(
        ProductCreate(
            name="Apple",
            category="Produce",
        )
    )

    products = service.get_all_products()
    assert len(products) >= 1


def test_update_product(db):
    service = make_service(db)
    product = service.create_product(
        ProductCreate(
            name="Old Name",
            category="Produce",
        )
    )

    updated = service.update_product(
        product.id,
        ProductUpdate(name="New Name"),
    )

    assert updated.name == "New Name"


def test_delete_product(db):
    service = make_service(db)
    product = service.create_product(
        ProductCreate(
            name="To Be Deleted",
            category="Miscellaneous",
        )
    )

    service.delete_product(product.id)

    with pytest.raises(NotFoundError):
        service.get_product_by_id(product.id)
