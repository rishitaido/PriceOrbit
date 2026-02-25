import os
from decimal import Decimal

import pytest

from app.core.exceptions import ExternalAPIError, ValidationError
from app.schemas.product_schemas import ProductCreate
from app.services.kroger_service import KrogerAPIError
from app.services.product_service import ProductService


pytestmark = pytest.mark.skipif(
    os.getenv("CI") == "true",
    reason="Requires MySQL database",
)


def make_service(db):
    return ProductService(db)


@pytest.mark.asyncio
async def test_update_price_from_kroger_success(db, monkeypatch):
    service = make_service(db)
    product = service.create_product(
        ProductCreate(
            name="Kroger Milk Test",
            category="Dairy & Eggs",
            current_price=Decimal("2.00"),
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

        async def get_product_details(self, kroger_product_id: str):
            assert kroger_product_id == "0001111060903"
            return {"items": [{"price": {"regular": 3.25}}]}

        async def find_kroger_product(self, product_name: str):
            return None

    monkeypatch.setattr("app.services.product_service.KrogerService", FakeKrogerService)

    payload = await service.update_price_from_kroger(product.id)

    refreshed = service.get_product_by_id(product.id)
    assert payload["old_price"] == Decimal("2.00")
    assert payload["new_price"] == Decimal("3.25")
    assert refreshed.current_price == Decimal("3.25")
    assert len(refreshed.price_history or []) == 1
    assert refreshed.last_price_check is not None


@pytest.mark.asyncio
async def test_update_price_finds_kroger_match_when_missing_id(db, monkeypatch):
    service = make_service(db)
    product = service.create_product(
        ProductCreate(
            name="Bananas Mapping Test",
            category="Fresh Produce",
            current_price=Decimal("0.59"),
        )
    )

    class FakeKrogerService:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get_product_details(self, kroger_product_id: str):
            assert kroger_product_id == "0001111060903"
            return {"items": [{"price": {"regular": 0.69}}]}

        async def find_kroger_product(self, product_name: str):
            return {
                "product_id": "0001111060903",
                "confidence": 98.2,
                "image_url": "https://example.com/banana.jpg",
                "ambiguous": False,
                "suggestions": [],
            }

    monkeypatch.setattr("app.services.product_service.KrogerService", FakeKrogerService)

    payload = await service.update_price_from_kroger(product.id)
    refreshed = service.get_product_by_id(product.id)

    assert payload["new_price"] == Decimal("0.69")
    assert refreshed.kroger_product_id == "0001111060903"
    assert refreshed.image_url == "https://example.com/banana.jpg"


@pytest.mark.asyncio
async def test_update_price_raises_external_error_on_api_failure(db, monkeypatch):
    service = make_service(db)
    product = service.create_product(
        ProductCreate(
            name="Kroger API Failure Test",
            category="Pantry Staples",
            current_price=Decimal("3.10"),
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

        async def get_product_details(self, kroger_product_id: str):
            raise KrogerAPIError("Kroger unavailable")

        async def find_kroger_product(self, product_name: str):
            return None

    monkeypatch.setattr("app.services.product_service.KrogerService", FakeKrogerService)

    with pytest.raises(ExternalAPIError):
        await service.update_price_from_kroger(product.id)


@pytest.mark.asyncio
async def test_update_all_prices_limit_validation(db):
    service = make_service(db)
    with pytest.raises(ValidationError):
        await service.update_all_prices(limit=51)


@pytest.mark.asyncio
async def test_update_all_prices_respects_limit(db, monkeypatch):
    service = make_service(db)
    service.create_product(
        ProductCreate(
            name="Batch One",
            category="Dairy & Eggs",
            current_price=Decimal("1.00"),
            kroger_product_id="0001111060903",
        )
    )
    service.create_product(
        ProductCreate(
            name="Batch Two",
            category="Dairy & Eggs",
            current_price=Decimal("2.00"),
            kroger_product_id="0001111060904",
        )
    )

    class FakeKrogerService:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get_product_details(self, kroger_product_id: str):
            if kroger_product_id == "0001111060903":
                return {"items": [{"price": {"regular": 1.50}}]}
            if kroger_product_id == "0001111060904":
                return {"items": [{"price": {"regular": 2.50}}]}
            return {"items": [{"price": {"regular": 1.99}}]}

        async def find_kroger_product(self, product_name: str):
            return {
                "product_id": "9999999999999",
                "confidence": 90.0,
                "image_url": None,
                "ambiguous": False,
                "suggestions": [],
            }

    monkeypatch.setattr("app.services.product_service.KrogerService", FakeKrogerService)

    summary = await service.update_all_prices(limit=1)
    assert summary["processed"] == 1
    assert summary["updated"] == 1
    assert summary["failed"] == 0
    assert len(summary["results"]) == 1
