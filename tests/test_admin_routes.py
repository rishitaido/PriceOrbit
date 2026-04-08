from fastapi.testclient import TestClient

from app.routers.auth_routes import get_current_user
from main import app
from app.tasks.price_updater import price_update_scheduler

client = TestClient(app)


def _install_auth_override():
    app.dependency_overrides[get_current_user] = lambda: type("User", (), {"id": 1})()


def _clear_overrides():
    app.dependency_overrides.clear()


def test_trigger_price_update_endpoint(monkeypatch):
    _install_auth_override()
    async def _fake_trigger_manual_update(*, limit: int, delay_seconds: float):
        return {
            "status": "started",
            "source": "manual",
            "limit": limit,
            "delay_seconds": delay_seconds,
        }

    try:
        monkeypatch.setattr(
            price_update_scheduler,
            "trigger_manual_update",
            _fake_trigger_manual_update,
        )

        response = client.post("/api/admin/trigger-price-update?limit=7&delay_seconds=1.5")
        assert response.status_code == 202
        payload = response.json()
        assert payload["status"] == "started"
        assert payload["limit"] == 7
        assert payload["delay_seconds"] == 1.5
    finally:
        _clear_overrides()


def test_price_update_status_endpoint(monkeypatch):
    _install_auth_override()
    try:
        monkeypatch.setattr(
            price_update_scheduler,
            "get_status",
            lambda: {"scheduler_enabled": True, "running": False},
        )

        response = client.get("/api/admin/price-update-status")
        assert response.status_code == 200
        assert response.json()["scheduler_enabled"] is True
    finally:
        _clear_overrides()
