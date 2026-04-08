"""Router exports."""

from app.routers.auth_routes import router as auth_routes_router
from app.routers.alert_routes import router as alert_routes_router
from app.routers.admin_routes import router as admin_routes_router
from app.routers.main import router as main_router
from app.routers.product_routes import router as product_routes_router
from app.routers.store_routes import router as store_routes_router

__all__ = [
    "admin_routes_router",
    "alert_routes_router",
    "auth_routes_router",
    "main_router",
    "product_routes_router",
    "store_routes_router",
]
