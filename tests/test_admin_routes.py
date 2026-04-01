from fastapi.testclient import TestClient

from main import app
from app.tasks.price_updater import price_update_scheduler

client = TestClient(app)


def test_trigger_price_update_endpoint(monkeypatch):
    async def _fake_trigger_manual_update(*, limit: int, delay_seconds: float):
        return {
            "status": "started",
            "source": "manual",
            "limit": limit,
            "delay_seconds": delay_seconds,
        }

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


def test_price_update_status_endpoint(monkeypatch):
    monkeypatch.setattr(
        price_update_scheduler,
        "get_status",
        lambda: {"scheduler_enabled": True, "running": False},
    )

    response = client.get("/api/admin/price-update-status")
    assert response.status_code == 200
    assert response.json()["scheduler_enabled"] is True

