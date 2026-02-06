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

@router.get("/about", response_class=HTMLResponse, tags=["pages"])
async def about(request: Request):
    """
    About page explaining PriceOrbit
    """
    return {
        "message": "About page - to be implemented",
        "description": "PriceOrbit predicts grocery price increases using tariff data and supply chain analysis"
    }
