from fastapi.testclient import TestClient

from app.db.session import get_db
from app.routers.auth_routes import get_current_user
from main import app
from app.tasks.price_updater import price_update_scheduler

client = TestClient(app)


def _install_auth_override():
    app.dependency_overrides[get_current_user] = lambda: type("User", (), {"id": 1})()


def _clear_overrides():
    app.dependency_overrides.clear()


def _install_db_override():
    def _fake_get_db():
        yield None

    app.dependency_overrides[get_db] = _fake_get_db


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

        response = client.post("/api/admin/trigger-price-update?limit=7&delay_seconds=1.5", headers={"X-Admin-Pin": "3030"})
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

        response = client.get("/api/admin/price-update-status", headers={"X-Admin-Pin": "3030"})
        assert response.status_code == 200
        assert response.json()["scheduler_enabled"] is True
    finally:
        _clear_overrides()


def test_dashboard_metrics_endpoint(monkeypatch):
    _install_auth_override()
    _install_db_override()

    class FakeAdminService:
        def __init__(self, _db):
            pass

        def get_dashboard_metrics(self, *, scheduler_snapshot):
            assert scheduler_snapshot["scheduler_enabled"] is True
            return {
                "total_products": 50,
                "total_stores": 20,
                "failed_api_calls": 0,
                "system_health": "healthy",
                "stale_products": 0,
                "scheduler_enabled": True,
                "scheduler_running": False,
                "next_run_utc": None,
                "last_run_started_at": None,
                "last_run_finished_at": None,
                "recent_price_updates": [],
            }

    try:
        monkeypatch.setattr(
            "app.routers.admin_routes.AdminService",
            FakeAdminService,
        )
        monkeypatch.setattr(
            price_update_scheduler,
            "get_status",
            lambda: {"scheduler_enabled": True, "running": False},
        )

        response = client.get("/api/admin/dashboard-metrics", headers={"X-Admin-Pin": "3030"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["total_products"] == 50
        assert payload["total_stores"] == 20
        assert payload["system_health"] == "healthy"
        assert payload["recent_price_updates"] == []
    finally:
        _clear_overrides()
