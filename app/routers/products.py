"""
Product API Router - PriceOrbit.

Defines all HTTP endpoints for product management.
Follows REST conventions:

    GET    /api/products               List products (paginated)
    GET    /api/products/categories    List all distinct categories
    GET    /api/products/search        Search products by name
    GET    /api/products/{id}          Get single product
    POST   /api/products               Create product
    PATCH  /api/products/{id}          Partial update
    DELETE /api/products/{id}          Delete product
    GET    /api/products/{id}/price-history   Full price history + stats
    POST   /api/products/{id}/price    Record a manual price entry

Error responses always use this shape:
    {"detail": {"code": "NOT_FOUND", "message": "...", "context": {...}}}

This makes it trivial for the frontend to parse errors programmatically.
"""

import logging
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.exceptions import DuplicateError, NotFoundError, ValidationError
from app.db.session import get_db
from app.schemas.product import PricePointCreate, ProductCreate, ProductResponse, ProductUpdate
from app.services.product_service import ProductService

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependency helper
# ---------------------------------------------------------------------------

def get_product_service(db: Session = Depends(get_db)) -> ProductService:
    """
    FastAPI dependency that constructs a ProductService with an active session.

    Injected into every route via Depends(get_product_service).
    This pattern means routes never instantiate services directly,
    which makes unit-testing trivial (just swap the dependency).
    """
    return ProductService(db)


# ---------------------------------------------------------------------------
# Error mapping helper
# ---------------------------------------------------------------------------

def _handle_domain_error(exc: Exception) -> None:
    """
    Map domain exceptions to FastAPI HTTPException with consistent shape.

    Args:
        exc: The domain exception to translate.

    Raises:
        HTTPException: Always - never returns normally.
    """
    if isinstance(exc, NotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": exc.message, "context": exc.details},
        )
    if isinstance(exc, DuplicateError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONFLICT", "message": exc.message, "context": exc.details},
        )
    if isinstance(exc, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "VALIDATION_ERROR", "message": exc.message, "context": exc.details},
        )
    # Fallback for any unhandled domain error
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"code": "INTERNAL_ERROR", "message": "An unexpected error occurred."},
    )


# ---------------------------------------------------------------------------
# LIST & SEARCH
# ---------------------------------------------------------------------------

@router.get(
    "/",
    response_model=List[ProductResponse],
    summary="List all products",
    description="Returns a paginated list of products. Filter by category using the `category` query param.",
)
def list_products(
    skip: int = Query(default=0, ge=0, description="Records to skip"),
    limit: int = Query(default=20, ge=1, le=100, description="Max records to return"),
    category: Optional[str] = Query(default=None, description="Filter by category name"),
    service: ProductService = Depends(get_product_service),
) -> List[ProductResponse]:
    """
    List products with optional pagination and category filter.

    Args:
        skip: Offset for pagination.
        limit: Page size (max 100).
        category: Optional category name to filter results.
        service: Injected ProductService instance.

    Returns:
        List of ProductResponse objects.
    """
    logger.info("GET /products skip=%d limit=%d category=%s", skip, limit, category)

    try:
        products = service.get_all_products(skip=skip, limit=limit, category=category)
        total = service.get_product_count(category=category)

        logger.info("Returning %d/%d products", len(products), total)
        return products

    except Exception as exc:
        logger.error("Unexpected error listing products: %s", exc, exc_info=True)
        _handle_domain_error(exc)


@router.get(
    "/categories",
    response_model=List[str],
    summary="List all categories",
    description="Returns all distinct product category names, sorted alphabetically.",
)
def list_categories(
    service: ProductService = Depends(get_product_service),
) -> List[str]:
    """
    Return all unique category names.

    Args:
        service: Injected ProductService.

    Returns:
        Sorted list of category strings.
    """
    logger.info("GET /products/categories")
    return service.get_all_categories()


@router.get(
    "/search",
    response_model=List[ProductResponse],
    summary="Search products",
    description="Case-insensitive search across product name and category. Minimum 2 characters.",
)
def search_products(
    q: str = Query(..., min_length=2, description="Search query (min 2 chars)"),
    service: ProductService = Depends(get_product_service),
) -> List[ProductResponse]:
    """
    Search products by name or category.

    Args:
        q: Query string, at least 2 characters.
        service: Injected ProductService.

    Returns:
        List of matching ProductResponse objects.
    """
    logger.info("GET /products/search q='%s'", q)

    try:
        return service.search_products(q)
    except ValidationError as exc:
        _handle_domain_error(exc)


# ---------------------------------------------------------------------------
# ADMIN: bulk recalculate
# ---------------------------------------------------------------------------

@router.post(
    "/recalculate-all-scores",
    summary="Recalculate health scores for all products (admin)",
    description=(
        "Recomputes and persists the health score for every product using the "
        "current algorithm. Use this after algorithm changes or bulk data imports."
    ),
)
def recalculate_all_scores(
    service: ProductService = Depends(get_product_service),
) -> dict:
    """
    Trigger a bulk health-score recalculation across all products.

    Args:
        service: Injected ProductService instance.

    Returns:
        Dict with ``updated`` (count of products recalculated) and a
        ``message`` confirming success.
    """
    logger.info("POST /products/recalculate-all-scores triggered")
    updated = service.recalculate_all_health_scores()
    logger.info("Recalculated health scores for %d products", updated)
    return {"updated": updated, "message": f"Health scores recalculated for {updated} products."}


# ---------------------------------------------------------------------------
# SINGLE PRODUCT
# ---------------------------------------------------------------------------

@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Get product by ID",
)
def get_product(
    product_id: int,
    service: ProductService = Depends(get_product_service),
) -> ProductResponse:
    """
    Fetch a single product by its primary key.

    Args:
        product_id: Integer product ID.
        service: Injected ProductService.

    Returns:
        ProductResponse if found.

    Raises:
        HTTPException 404: If product does not exist.
    """
    logger.info("GET /products/%d", product_id)

    try:
        return service.get_product_by_id(product_id)
    except NotFoundError as exc:
        _handle_domain_error(exc)


@router.post(
    "/",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a product",
)
def create_product(
    product_data: ProductCreate,
    service: ProductService = Depends(get_product_service),
) -> ProductResponse:
    """
    Create a new product.

    The health score is calculated automatically on creation.

    Args:
        product_data: Validated ProductCreate body.
        service: Injected ProductService.

    Returns:
        Created ProductResponse with assigned ID.

    Raises:
        HTTPException 409: If a product with the same name already exists.
    """
    logger.info("POST /products name='%s'", product_data.name)

    try:
        return service.create_product(product_data)
    except DuplicateError as exc:
        _handle_domain_error(exc)


@router.patch(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Partially update a product",
)
def update_product(
    product_id: int,
    product_data: ProductUpdate,
    service: ProductService = Depends(get_product_service),
) -> ProductResponse:
    """
    Partially update a product. Only fields included in the request body are changed.

    Automatically recalculates health score if tariff_rate,
    import_dependency, or current_price is updated.

    Args:
        product_id: ID of the product to update.
        product_data: ProductUpdate body (all fields optional).
        service: Injected ProductService.

    Returns:
        Updated ProductResponse.

    Raises:
        HTTPException 404: If product does not exist.
    """
    logger.info("PATCH /products/%d", product_id)

    try:
        return service.update_product(product_id, product_data)
    except NotFoundError as exc:
        _handle_domain_error(exc)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a product",
)
def delete_product(
    product_id: int,
    service: ProductService = Depends(get_product_service),
) -> None:
    """
    Permanently delete a product.

    Args:
        product_id: ID of the product to delete.
        service: Injected ProductService.

    Returns:
        204 No Content on success.

    Raises:
        HTTPException 404: If product does not exist.
    """
    logger.info("DELETE /products/%d", product_id)

    try:
        service.delete_product(product_id)
    except NotFoundError as exc:
        _handle_domain_error(exc)


# ---------------------------------------------------------------------------
# PRICE HISTORY
# ---------------------------------------------------------------------------

@router.get(
    "/{product_id}/price-history",
    summary="Get price history and statistics",
    description="Returns full price history with computed min, max, average, and trend.",
)
def get_price_history(
    product_id: int,
    service: ProductService = Depends(get_product_service),
) -> dict:
    """
    Retrieve price history and statistics for a product.

    Args:
        product_id: Target product ID.
        service: Injected ProductService.

    Returns:
        Dict with product_id, product_name, current_price, history, statistics.

    Raises:
        HTTPException 404: If product does not exist.
    """
    logger.info("GET /products/%d/price-history", product_id)

    try:
        return service.get_price_history(product_id)
    except NotFoundError as exc:
        _handle_domain_error(exc)


@router.post(
    "/{product_id}/price",
    response_model=ProductResponse,
    summary="Record a manual price",
    description="Manually record a price for a product. Adds to price history and recalculates health score.",
)
def add_manual_price(
    product_id: int,
    price: Decimal = Query(..., gt=0, description="Price value (must be > 0)"),
    service: ProductService = Depends(get_product_service),
) -> ProductResponse:
    """
    Record a manual price entry for a product.

    Args:
        product_id: Target product ID.
        price: New price value.
        service: Injected ProductService.

    Returns:
        Updated ProductResponse.

    Raises:
        HTTPException 404: Product not found.
        HTTPException 422: Price is invalid.
    """
    logger.info("POST /products/%d/price price=%.2f", product_id, price)

    try:
        return service.add_manual_price(product_id, price)
    except (NotFoundError, ValidationError) as exc:
        _handle_domain_error(exc)


@router.post(
    "/{product_id}/add-price-point",
    response_model=ProductResponse,
    summary="Add a price point (live update or back-fill)",
    description=(
        "Record a new price for a product. "
        "When **date** is omitted or equals today, the product's ``current_price`` "
        "is updated and the old price is archived to history. "
        "When **date** is a past ISO-8601 date, the entry is back-filled into "
        "price history without changing ``current_price`` — useful for importing "
        "historical data. Health score is recalculated in both cases."
    ),
)
def add_price_point(
    product_id: int,
    body: PricePointCreate,
    service: ProductService = Depends(get_product_service),
) -> ProductResponse:
    """
    Add a structured price data point to a product.

    Unlike ``POST /{id}/price`` (which takes a query-param price only),
    this endpoint accepts a JSON body so callers can also supply an
    explicit date for back-filling historical records.

    Args:
        product_id: Target product ID.
        body: JSON body with ``price`` (required) and ``date`` (optional).
        service: Injected ProductService.

    Returns:
        Updated ProductResponse.

    Raises:
        HTTPException 404: Product not found.
        HTTPException 422: Price is invalid or date format is wrong.
    """
    logger.info(
        "POST /products/%d/add-price-point price=%.2f date=%s",
        product_id,
        body.price,
        body.date or "today",
    )

    try:
        return service.add_price_point(product_id, body.price, body.date)
    except (NotFoundError, ValidationError) as exc:
        _handle_domain_error(exc)