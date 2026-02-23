from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from app.core.config import settings 
from app.routers.main import router as main_router 
from app.routers.products import router as products_router
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    print(f"{settings.APP_NAME} v{settings.VERSION}")
    print(f"Database: {settings.MYSQL_DATABASE}")
    print(f"Debug Mode: {settings.DEBUG}")
    print(f"API Docs: http://localhost:{settings.PORT}/docs")
    yield  # app runs here

    # --- shutdown ---
    print("\n👋 Shutting down PriceOrbit API...")


# Create FastAPI application instance
app = FastAPI(
    title=settings.APP_NAME,
    version= settings.VERSION,
    description= "Grocery price prediction system monitoring tariffs, supply chain, and retail prices",
    docs_url= "/docs", 
    redoc_url = "/redoc",
    lifespan=lifespan
    
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins = settings.CORS_ORIGINS,  # Fixed: was 'allow_origin' (typo)
    allow_credentials = True,
    allow_methods = ["*"],
    allow_headers = ["*"],
)

#Static files 
app.mount("/static", StaticFiles(directory="app/static"), name="static")

#Include Routers 
app.include_router(main_router, tags=["main"])
app.include_router(products_router, prefix= "/api/products", tags = ["products"])

@app.get("/health", tags = ["health"])
def health_check(): 
    '''
    Health check endpoint 
    Sends API status and config info 
    '''
    return {
        "status" : "healthy",
        "service" : settings.APP_NAME, 
        "version" : settings.VERSION, 
        "debug" : settings.DEBUG
    }

@app.get("/product/{product_id}", response_class=HTMLResponse)
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