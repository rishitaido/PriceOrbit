import pytest
import os
from app.services.product_service import (
    create_product,
    get_product,
    get_all_products,
    update_product,
    delete_product,
)


pytestmark = pytest.mark.skipif(
    os.getenv("CI") == "true",
    reason="Requires MySQL database"
)

def test_create_product(db):
    product = create_product(db, {
        "name": "Test Milk",
        "category": "Dairy",
    })

    assert product.id is not None
    assert product.name == "Test Milk"
    assert product.category == "Dairy"


def test_create_product_missing_name(db):
    with pytest.raises(ValueError):
        create_product(db, {
            "category": "Dairy",
        })


def test_get_product(db):
    product = create_product(db, {
        "name": "Test Bread",
        "category": "Bakery",
    })

    fetched = get_product(db, product.id)
    assert fetched.id == product.id


def test_get_product_not_found(db):
    with pytest.raises(ValueError):
        get_product(db, 999999)


def test_get_all_products(db):
    create_product(db, {
        "name": "Apple",
        "category": "Produce",
    })

    products = get_all_products(db)
    assert len(products) >= 1


def test_update_product(db):
    product = create_product(db, {
        "name": "Old Name",
        "category": "Produce",
    })

    updated = update_product(db, product.id, {
        "name": "New Name"
    })

    assert updated.name == "New Name"


def test_delete_product(db):
    product = create_product(db, {
        "name": "To Be Deleted",
        "category": "Miscellaneous",
    })

    result = delete_product(db, product.id)
    assert result is True

    with pytest.raises(ValueError):
        get_product(db, product.id)