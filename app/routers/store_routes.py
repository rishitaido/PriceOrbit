"""Store REST API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.store_schemas import (
    NearbyStoreResponse,
    StoreListResponse,
    StoreResponse,
)
from app.services.store_service import StoreService

router = APIRouter()


def get_store_service(db: Session = Depends(get_db)) -> StoreService:
    """Dependency injection factory for StoreService."""
    return StoreService(db)


@router.get("/", response_model=StoreListResponse)
def get_stores(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    service: StoreService = Depends(get_store_service),
):
    stores = service.get_all_stores(skip=skip, limit=limit)
    total = service.get_store_count()
    page = (skip // limit) + 1
    return StoreListResponse(stores=stores, total=total, page=page, page_size=limit)


@router.get("/nearby", response_model=list[NearbyStoreResponse])
def get_nearby_stores(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius: float = Query(10.0, gt=0, le=100),
    limit: int = Query(20, ge=1, le=100),
    service: StoreService = Depends(get_store_service),
):
    results = service.get_nearby_stores(
        latitude=lat,
        longitude=lng,
        radius_miles=radius,
        limit=limit,
    )

    response: list[NearbyStoreResponse] = []
    for store, distance_miles in results:
        payload = StoreResponse.model_validate(store).model_dump()
        payload["distance_miles"] = distance_miles
        response.append(NearbyStoreResponse(**payload))
    return response


@router.get("/{store_id}", response_model=StoreResponse)
def get_store(
    store_id: int,
    service: StoreService = Depends(get_store_service),
):
    return service.get_store_by_id(store_id)
