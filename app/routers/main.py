"""
Main app routes for Pages n endpoint 
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates 

router = APIRouter() 

templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse, tags=["pages"])
async def home(request: Request):
    """
    Request to get to home page
    """
    return templates.TemplateResponse(
        'index.html',
        {"request": request, "title" : "PriceOrbit - Grocery Price Predictions"}
    )

@router.get("/products.html", response_class=HTMLResponse, tags=["pages"])
async def products(request: Request): 
    return templates.TemplateResponse(
        'products.html', 
        {"request": request, 'title' : "Products page"}
    )


@router.get("/register", response_class=HTMLResponse, tags=["pages"])
async def register(request: Request):
    """User registration page"""
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "title": "PriceOrbit - Sign Up"}
    )


@router.get("/admin", response_class=HTMLResponse, tags=["pages"])
async def admin(request: Request):
    """Admin dashboard page"""
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "title": "PriceOrbit - Admin"}
    )


@router.get("/stores", response_class=HTMLResponse, tags=["pages"])
async def stores(request: Request):
    """Store locator map page"""
    return templates.TemplateResponse(
        "stores.html",
        {"request": request, "title": "PriceOrbit - Store Locator"}
    )


@router.get("/about.html", response_class=HTMLResponse, tags=["pages"])
async def about(request: Request):
    """
    About page explaining PriceOrbit
    """
    return {
        "message": "About page - to be implemented",
        "description": "PriceOrbit predicts grocery price increases using tariff data and supply chain analysis"
    }