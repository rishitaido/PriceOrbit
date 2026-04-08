import os
from decimal import Decimal
from typing import Optional

import pytest

from app.models.product_store_price_model import ProductStorePrice
from app.models.store_model import Store
from app.schemas.product_schemas import ProductCreate
from app.services.product_service import ProductService


pytestmark = pytest.mark.skipif(
    os.getenv("CI") == "true",
    reason="Requires MySQL database",
)


def make_service(db):
    return ProductService(db)


def test_parse_store_ids_csv():
    assert ProductService.parse_store_ids_csv(None) is None
    assert ProductService.parse_store_ids_csv("") is None
    assert ProductService.parse_store_ids_csv("1,2,3") == [1, 2, 3]
    assert ProductService.parse_store_ids_csv(" 1, 2,2 , 3 ") == [1, 2, 3]


@pytest.mark.asyncio
async def test_get_product_prices_by_store_persists_records(db, monkeypatch):
    service = make_service(db)

    store_one = Store(
        name="Kroger Midtown",
        address="123 Main St",
        city="Baton Rouge",
        state="LA",
        zip_code="70808",
        kroger_location_id="01400943",
        latitude=30.406,
        longitude=-91.179,
    )
    store_two = Store(
        name="Kroger Highland",
        address="456 Highland Rd",
        city="Baton Rouge",
        state="LA",
        zip_code="70810",
        kroger_location_id="01400944",
        latitude=30.378,
        longitude=-91.122,
    )
    db.add(store_one)
    db.add(store_two)
    db.commit()
    db.refresh(store_one)
    db.refresh(store_two)

    product = service.create_product(
        ProductCreate(
            name="Store Price Milk",
            category="Dairy & Eggs",
            current_price=Decimal("2.50"),
            kroger_product_id="0001111060903",
        )
    )

    class FakeKrogerService:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get_product_details(self, kroger_product_id: str, location_id: Optional[str] = None):
            assert kroger_product_id == "0001111060903"
            if location_id == "01400943":
                return {"items": [{"price": {"regular": 3.10}}]}
            if location_id == "01400944":
                return {"items": [{"price": {"regular": 3.35}}]}
            return {"items": [{"price": {"regular": 2.99}}]}

        async def get_product_price_by_location(self, product_id: str, location_id: str):
            assert product_id == "0001111060903"
            if location_id == "01400943":
                return {"price": {"regular": 3.10}, "nationalPrice": {}}
            if location_id == "01400944":
                return {"price": {"regular": 3.35}, "nationalPrice": {}}
            return {"price": {"regular": 2.99}, "nationalPrice": {}}

        async def find_kroger_product(self, product_name: str, **kwargs):
            return None

    monkeypatch.setattr("app.services.product_service.KrogerService", FakeKrogerService)

    payload = await service.get_product_prices_by_store(
        product_id=product.id,
        store_ids=[store_one.id, store_two.id],
        refresh_from_api=True,
    )

    assert payload["product_id"] == product.id
    assert len(payload["prices"]) == 2

    rows = (
        db.query(ProductStorePrice)
        .filter(ProductStorePrice.product_id == product.id)
        .order_by(ProductStorePrice.store_id.asc())
        .all()
    )
    assert len(rows) == 2
    assert rows[0].price == Decimal("3.10")
    assert rows[1].price == Decimal("3.35")
