import os
from decimal import Decimal

import pytest

from app.models.user_model import User
from app.schemas.alert_schemas import PriceAlertCreate
from app.schemas.product_schemas import ProductCreate
from app.services.price_alert_service import PriceAlertService
from app.services.product_service import ProductService


pytestmark = pytest.mark.skipif(
    os.getenv("CI") == "true",
    reason="Requires MySQL database",
)


def _create_user(db, email: str = "alerts-test@example.com") -> User:
    user = User(
        email=email,
        full_name="Alerts Tester",
        hashed_password="hashed-password-placeholder",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_product(db, name: str = "Alerts Test Bananas"):
    product_service = ProductService(db)
    return product_service.create_product(
        ProductCreate(
            name=name,
            category="Fresh Produce",
            current_price=Decimal("0.79"),
        )
    )


def test_create_and_list_alert(db):
    user = _create_user(db, email="alerts-list@example.com")
    product = _create_product(db, name="Alerts Product A")
    service = PriceAlertService(db)

    created = service.create_or_update_alert(
        user_id=user.id,
        payload=PriceAlertCreate(
            product_id=product.id,
            target_price=Decimal("0.60"),
            is_active=True,
        ),
    )
    assert created["product_id"] == product.id
    assert created["is_active"] is True
    assert created["triggered"] is False

    alerts = service.list_alerts_for_user(user_id=user.id)
    assert len(alerts) == 1
    assert alerts[0]["target_price"] == Decimal("0.60")


def test_delete_alert(db):
    user = _create_user(db, email="alerts-delete@example.com")
    product = _create_product(db, name="Alerts Product B")
    service = PriceAlertService(db)

    created = service.create_or_update_alert(
        user_id=user.id,
        payload=PriceAlertCreate(
            product_id=product.id,
            target_price=Decimal("0.55"),
            is_active=True,
        ),
    )
    service.delete_alert(user_id=user.id, alert_id=created["id"])

    alerts = service.list_alerts_for_user(user_id=user.id)
    assert alerts == []


def test_check_and_log_triggered_alerts(db):
    user = _create_user(db, email="alerts-trigger@example.com")
    product = _create_product(db, name="Alerts Product C")
    service = PriceAlertService(db)

    service.create_or_update_alert(
        user_id=user.id,
        payload=PriceAlertCreate(
            product_id=product.id,
            target_price=Decimal("0.90"),
            is_active=True,
        ),
    )

    triggered = service.check_and_log_triggered_alerts(
        product_id=product.id,
        current_price=Decimal("0.79"),
    )
    assert len(triggered) == 1
    assert triggered[0]["user_id"] == user.id
    assert triggered[0]["product_id"] == product.id

