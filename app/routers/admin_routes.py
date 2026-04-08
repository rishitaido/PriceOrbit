"""Admin routes for operational controls."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.models.user_model import User
from app.routers.auth_routes import get_current_user
from app.tasks.price_updater import price_update_scheduler

router = APIRouter()


@router.post("/trigger-price-update", status_code=status.HTTP_202_ACCEPTED)
async def trigger_price_update(
    limit: int = Query(50, ge=1, le=50),
    delay_seconds: float = Query(2.0, ge=0, le=30),
    _: User = Depends(get_current_user),
):
    """Trigger an asynchronous price update batch."""
    return await price_update_scheduler.trigger_manual_update(
        limit=limit,
        delay_seconds=delay_seconds,
    )


@router.get("/price-update-status")
def get_price_update_status(
    _: User = Depends(get_current_user),
):
    """Return scheduler and last-run status."""
    return price_update_scheduler.get_status()
