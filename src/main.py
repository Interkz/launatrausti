"""
Launatrausti - Icelandic Salary Transparency Platform

FastAPI web application for viewing company salary rankings.
"""

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from . import database

app = FastAPI(
    title="Launatrausti",
    description="Icelandic Salary Transparency Platform",
    version="0.1.0"
)

# Set up templates
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, year: Optional[int] = None):
    """Home page with ranked list of companies by average salary."""
    companies = database.get_ranked_companies(year=year)
    years = database.get_available_years()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "companies": companies,
            "years": years,
            "selected_year": year
        }
    )


@app.get("/company/{company_id}", response_class=HTMLResponse)
async def company_detail(request: Request, company_id: int):
    """Company detail page with all annual reports."""
    data = database.get_company_detail(company_id)

    if not data:
        raise HTTPException(status_code=404, detail="Company not found")

    return templates.TemplateResponse(
        "company.html",
        {
            "request": request,
            "company": data["company"],
            "reports": data["reports"]
        }
    )


@app.get("/api/companies")
async def api_companies(year: Optional[int] = None, limit: int = 100):
    """JSON API endpoint for company rankings."""
    companies = database.get_ranked_companies(year=year, limit=limit)
    return {"companies": companies, "year": year}


@app.get("/api/company/{company_id}")
async def api_company(company_id: int):
    """JSON API endpoint for company detail."""
    data = database.get_company_detail(company_id)
    if not data:
        raise HTTPException(status_code=404, detail="Company not found")
    return data


# Health check endpoint
@app.get("/health")
async def health():
    return {"status": "ok"}
