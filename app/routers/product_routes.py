"""Product REST API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.db.session import get_db
from app.schemas.product_schemas import (
    BatchPriceUpdateResponse,
    PriceHistoryResponse,
    PricePointCreate,
    ProductStorePriceListResponse,
    PriceUpdateResponse,
    ProductCreate,
    ProductListResponse,
    ProductResponse,
    ProductUpdate,
)
from app.services.product_service import ProductService

router = APIRouter()


# Dependency injection factory for ProductService.
def get_product_service(db: Session = Depends(get_db)) -> ProductService:
    return ProductService(db)


@router.get("/", response_model=ProductListResponse)
def get_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    service: ProductService = Depends(get_product_service),
):
    products = service.get_all_products(skip=skip, limit=limit)
    total = service.get_product_count()
    page = (skip // limit) + 1
    return ProductListResponse(products=products, total=total, page=page, page_size=limit)


@router.get("/category/{category}", response_model=ProductListResponse)
def get_products_by_category(
    category: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    service: ProductService = Depends(get_product_service),
):
    products = service.get_products_by_category(category=category, skip=skip, limit=limit)
    total = service.get_product_count(category=category)
    page = (skip // limit) + 1
    return ProductListResponse(products=products, total=total, page=page, page_size=limit)


@router.get("/search", response_model=ProductListResponse)
def search_products(
    q: str = Query(..., min_length=2),
    category: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    service: ProductService = Depends(get_product_service),
):
    matches = service.search_products(q)
    if category:
        matches = [product for product in matches if product.category == category]

    total = len(matches)
    paginated = matches[skip: skip + limit]
    page = (skip // limit) + 1
    return ProductListResponse(products=paginated, total=total, page=page, page_size=limit)


@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    product_data: ProductCreate,
    service: ProductService = Depends(get_product_service),
):
    return service.create_product(product_data)


@router.post("/update-all-prices", response_model=BatchPriceUpdateResponse)
async def update_all_prices(
    limit: int = Query(50, ge=1, le=50),
    service: ProductService = Depends(get_product_service),
):
    summary = await service.update_all_prices(limit=limit)
    return BatchPriceUpdateResponse(**summary)


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: int,
    service: ProductService = Depends(get_product_service),
):
    return service.get_product_by_id(product_id)


@router.patch("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    product_data: ProductUpdate,
    service: ProductService = Depends(get_product_service),
):
    return service.update_product(product_id, product_data)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: int,
    confirm: bool = Query(False, description="Must be true to confirm hard delete"),
    service: ProductService = Depends(get_product_service),
):
    if not confirm:
        raise ValidationError("Deletion requires confirm=true.")
    service.delete_product(product_id)
    return None


@router.get("/{product_id}/price-history", response_model=PriceHistoryResponse)
def get_product_price_history(
    product_id: int,
    service: ProductService = Depends(get_product_service),
):
    payload = service.get_price_history(product_id)
    return PriceHistoryResponse(**payload)


@router.get("/{product_id}/prices", response_model=ProductStorePriceListResponse)
async def get_product_prices_by_store(
    product_id: int,
    store_ids: str | None = Query(
        None,
        description="Optional comma-separated store IDs, for example: 1,2,3",
    ),
    refresh: bool = Query(
        True,
        description="When true, fetch fresh store-specific prices from Kroger and persist them.",
    ),
    service: ProductService = Depends(get_product_service),
):
    parsed_store_ids = ProductService.parse_store_ids_csv(store_ids)
    payload = await service.get_product_prices_by_store(
        product_id=product_id,
        store_ids=parsed_store_ids,
        refresh_from_api=refresh,
    )
    return ProductStorePriceListResponse(**payload)


@router.post("/{product_id}/add-price-point", response_model=ProductResponse)
def add_price_point(
    product_id: int,
    payload: PricePointCreate,
    service: ProductService = Depends(get_product_service),
):
    return service.add_price_point(product_id=product_id, price=payload.price, record_date=payload.date)


@router.post("/{product_id}/recalculate-health-score", response_model=ProductResponse)
def recalculate_health_score(
    product_id: int,
    service: ProductService = Depends(get_product_service),
):
    return service.recalculate_health_score(product_id)


@router.post("/{product_id}/update-price", response_model=PriceUpdateResponse)
async def update_product_price(
    product_id: int,
    service: ProductService = Depends(get_product_service),
):
    payload = await service.update_price_from_kroger(product_id)
    return PriceUpdateResponse(**payload)
