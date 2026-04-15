import logging
import os

from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from app.core.config import settings 
from app.core.exceptions import (
    AuthenticationError,
    DuplicateError,
    ExternalAPIError,
    NotFoundError,
    PriceOrbitError,
    ValidationError,
)
from app.routers.main import router as main_router 
from app.routers.auth_routes import router as auth_routes_router
from app.routers.alert_routes import router as alert_routes_router
from app.routers.admin_routes import router as admin_routes_router
from app.routers.product_routes import router as product_routes_router
from app.routers.store_routes import router as store_routes_router
from app.tasks.price_updater import price_update_scheduler
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)


def _is_production_runtime() -> bool:
    deploy_env = (settings.DEPLOY_ENV or "").strip().lower()
    return (
        deploy_env in {"prod", "production"}
        or bool(os.getenv("RENDER"))
        or bool(os.getenv("RENDER_SERVICE_ID"))
    )


def _api_docs_enabled() -> bool:
    if _is_production_runtime():
        return False
    return bool(settings.ENABLE_API_DOCS and settings.DEBUG)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    if _is_production_runtime():
        if settings.DEBUG:
            raise RuntimeError("DEBUG must be False in production.")
        if settings.SECRET_KEY == "change-me-in-production" or len(settings.SECRET_KEY) < 32:
            raise RuntimeError("SECRET_KEY must be set to a secure value (min 32 chars) in production.")
        if settings.ENABLE_API_DOCS:
            raise RuntimeError("ENABLE_API_DOCS must be False in production.")
        if settings.ADMIN_PIN == "3030":
            logger.warning("Using default ADMIN_PIN in production runtime.")
    logger.info("%s v%s", settings.APP_NAME, settings.VERSION)
    logger.info("Database: %s", settings.MYSQL_DATABASE)
    logger.info("Debug Mode: %s", settings.DEBUG)
    await price_update_scheduler.start()
    yield  # app runs here

    # --- shutdown ---
    await price_update_scheduler.shutdown()
    logger.info("Shutting down PriceOrbit API...")


# Create FastAPI application instance
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="Grocery price prediction system monitoring tariffs, supply chain, and retail prices",
    docs_url="/docs" if _api_docs_enabled() else None,
    redoc_url="/redoc" if _api_docs_enabled() else None,
    openapi_url="/openapi.json" if _api_docs_enabled() else None,
    lifespan=lifespan,
)


def _error_response(status_code: int, code: str, exc: PriceOrbitError) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": {
                "code": code,
                "message": exc.message,
                "context": exc.details,
            }
        },
    )


@app.exception_handler(NotFoundError)
async def handle_not_found(_: Request, exc: NotFoundError):
    return _error_response(404, "NOT_FOUND", exc)


@app.exception_handler(DuplicateError)
async def handle_duplicate(_: Request, exc: DuplicateError):
    return _error_response(409, "DUPLICATE", exc)


@app.exception_handler(ValidationError)
async def handle_validation(_: Request, exc: ValidationError):
    return _error_response(422, "VALIDATION_ERROR", exc)


@app.exception_handler(ExternalAPIError)
async def handle_external(_: Request, exc: ExternalAPIError):
    return _error_response(502, "EXTERNAL_API_ERROR", exc)


@app.exception_handler(AuthenticationError)
async def handle_auth(_: Request, exc: AuthenticationError):
    return _error_response(401, "AUTHENTICATION_ERROR", exc)


@app.exception_handler(PriceOrbitError)
async def handle_domain_error(_: Request, exc: PriceOrbitError):
    return _error_response(400, "DOMAIN_ERROR", exc)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins = settings.CORS_ORIGINS,  # Fixed: was 'allow_origin' (typo)
    allow_credentials = True,
    allow_methods = ["*"],
    allow_headers = ["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(self)"
    if _is_production_runtime():
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'; base-uri 'self'"
    return response

#Static files 
app.mount("/static", StaticFiles(directory="app/static"), name="static")

#Include Routers 
app.include_router(main_router, tags=["main"])
app.include_router(auth_routes_router, prefix="/api/auth", tags=["auth"])
app.include_router(alert_routes_router, prefix="/api/alerts", tags=["alerts"])
app.include_router(admin_routes_router, prefix="/api/admin", tags=["admin"])
app.include_router(product_routes_router, prefix= "/api/products", tags = ["products"])
app.include_router(store_routes_router, prefix="/api/stores", tags=["stores"])

@app.get("/health", tags = ["health"])
def health_check(): 
    '''
    Health check endpoint 
    Sends API status and config info 
    '''
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.VERSION,
    }

@app.get("/products/{product_id}", response_class=HTMLResponse)
async def product_detail_page(request: Request,product_id: int):
    '''
    Renders the product detail page for a given product ID.
    '''
    return templates.TemplateResponse("product_details.html", {"request": request, "product_id": product_id})


if __name__ == "__main__": 
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG
    )
