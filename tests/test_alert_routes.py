from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.routers.alert_routes import get_alert_service
from app.routers.auth_routes import get_current_user
from main import app

client = TestClient(app)


class FakeAlertService:
    def __init__(self):
        self.created_payload = None
        self.deleted_alert_id = None
        self.deleted_user_id = None

    def create_or_update_alert(self, *, user_id: int, payload):
        self.created_payload = {"user_id": user_id, "payload": payload.model_dump()}
        return {
            "id": 7,
            "user_id": user_id,
            "product_id": payload.product_id,
            "product_name": "Bananas",
            "target_price": payload.target_price,
            "current_price": "0.79",
            "is_active": payload.is_active,
            "triggered": False,
            "created_at": "2026-04-08T00:00:00Z",
            "updated_at": "2026-04-08T00:00:00Z",
        }

    def list_alerts_for_user(self, *, user_id: int, active_only=None):
        return [
            {
                "id": 7,
                "user_id": user_id,
                "product_id": 3,
                "product_name": "Bananas",
                "target_price": "0.50",
                "current_price": "0.79",
                "is_active": True,
                "triggered": False,
                "created_at": "2026-04-08T00:00:00Z",
                "updated_at": "2026-04-08T00:00:00Z",
            }
        ]

    def delete_alert(self, *, user_id: int, alert_id: int):
        self.deleted_alert_id = alert_id
        self.deleted_user_id = user_id


def _install_overrides(fake_service: FakeAlertService):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=42)
    app.dependency_overrides[get_alert_service] = lambda: fake_service


def _clear_overrides():
    app.dependency_overrides.clear()


def test_create_alert_endpoint():
    fake_service = FakeAlertService()
    _install_overrides(fake_service)
    try:
        response = client.post(
            "/api/alerts/",
            json={"product_id": 3, "target_price": 0.50, "is_active": True},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == 7
        assert payload["product_id"] == 3
        assert fake_service.created_payload["user_id"] == 42
    finally:
        _clear_overrides()


def test_list_alerts_endpoint():
    fake_service = FakeAlertService()
    _install_overrides(fake_service)
    try:
        response = client.get("/api/alerts/")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["alerts"][0]["product_name"] == "Bananas"
    finally:
        _clear_overrides()


def test_delete_alert_endpoint():
    fake_service = FakeAlertService()
    _install_overrides(fake_service)
    try:
        response = client.delete("/api/alerts/7")
        assert response.status_code == 204
        assert fake_service.deleted_alert_id == 7
        assert fake_service.deleted_user_id == 42
    finally:
        _clear_overrides()

