"""Price alert REST API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user_model import User
from app.routers.auth_routes import get_current_user
from app.schemas.alert_schemas import (
    PriceAlertCreate,
    PriceAlertListResponse,
    PriceAlertResponse,
)
from app.services.price_alert_service import PriceAlertService

router = APIRouter()


def get_alert_service(db: Session = Depends(get_db)) -> PriceAlertService:
    return PriceAlertService(db)


@router.post("/", response_model=PriceAlertResponse)
def create_alert(
    payload: PriceAlertCreate,
    current_user: User = Depends(get_current_user),
    service: PriceAlertService = Depends(get_alert_service),
):
    return service.create_or_update_alert(user_id=current_user.id, payload=payload)


@router.get("/", response_model=PriceAlertListResponse)
def list_alerts(
    active_only: bool | None = Query(
        None,
        description="Filter by active status when provided.",
    ),
    current_user: User = Depends(get_current_user),
    service: PriceAlertService = Depends(get_alert_service),
):
    alerts = service.list_alerts_for_user(user_id=current_user.id, active_only=active_only)
    return PriceAlertListResponse(alerts=alerts, total=len(alerts))


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert(
    alert_id: int,
    current_user: User = Depends(get_current_user),
    service: PriceAlertService = Depends(get_alert_service),
):
    service.delete_alert(user_id=current_user.id, alert_id=alert_id)
    return None

