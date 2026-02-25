"""Router exports."""

from app.routers.main import router as main_router
from app.routers.product_routes import router as product_routes_router

__all__ = ["main_router", "product_routes_router"]
