"""Admin routes for operational controls."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.user_model import User
from app.routers.auth_routes import get_current_user
from app.services.admin_service import AdminService
from app.tasks.price_updater import price_update_scheduler

router = APIRouter()


def verify_admin_pin(x_admin_pin: str = Header(..., description="Admin PIN required for access")) -> None:
    """Validate the X-Admin-Pin header against the configured ADMIN_PIN."""
    if x_admin_pin != settings.ADMIN_PIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin PIN.")


@router.post("/trigger-price-update", status_code=status.HTTP_202_ACCEPTED)
async def trigger_price_update(
    limit: int = Query(50, ge=1, le=50),
    delay_seconds: float = Query(2.0, ge=0, le=30),
    _: User = Depends(get_current_user),
    __: None = Depends(verify_admin_pin),
):
    """Trigger an asynchronous price update batch."""
    return await price_update_scheduler.trigger_manual_update(
        limit=limit,
        delay_seconds=delay_seconds,
    )


@router.get("/price-update-status")
def get_price_update_status(
    _: User = Depends(get_current_user),
    __: None = Depends(verify_admin_pin),
):
    """Return scheduler and last-run status."""
    return price_update_scheduler.get_status()


@router.get("/dashboard-metrics")
def get_dashboard_metrics(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    __: None = Depends(verify_admin_pin),
):
    """Return admin dashboard metrics and recent update activity."""
    service = AdminService(db)
    scheduler_snapshot = price_update_scheduler.get_status()
    return service.get_dashboard_metrics(scheduler_snapshot=scheduler_snapshot)
