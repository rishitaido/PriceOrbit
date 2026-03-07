"""Router exports."""

from app.routers.auth_routes import router as auth_routes_router
from app.routers.main import router as main_router
from app.routers.product_routes import router as product_routes_router
from app.routers.store_routes import router as store_routes_router

__all__ = ["auth_routes_router", "main_router", "product_routes_router", "store_routes_router"]
