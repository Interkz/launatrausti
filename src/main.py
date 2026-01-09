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
from . import hagstofa

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

    # Get industry benchmark based on company's ISAT code
    company = data["company"]
    reports = data["reports"]

    benchmark = None
    national_avg = None
    industry_name = None

    if reports:
        latest_year = reports[0]["year"]
        isat_code = company.get("isat_code")

        if isat_code:
            benchmark = hagstofa.get_industry_benchmark(isat_code, latest_year)
            industry_name = hagstofa.isat_to_industry_name(isat_code, english=True)

        national_avg = hagstofa.get_national_average(latest_year)

    return templates.TemplateResponse(
        "company.html",
        {
            "request": request,
            "company": company,
            "reports": reports,
            "benchmark": benchmark,
            "national_avg": national_avg,
            "industry_name": industry_name,
        }
    )


@app.get("/benchmarks", response_class=HTMLResponse)
async def benchmarks_page(request: Request, year: int = 2023):
    """Industry wage benchmarks page."""
    benchmarks = hagstofa.get_all_benchmarks(year)
    national_avg = hagstofa.get_national_average(year)

    # Add English names to benchmark objects
    benchmarks_with_names = []
    for bm in benchmarks:
        benchmarks_with_names.append({
            "industry_code": bm.industry_code,
            "industry_name": bm.industry_name,
            "industry_name_en": hagstofa.INDUSTRY_NAMES_EN.get(bm.industry_code, bm.industry_code),
            "monthly_wage": bm.monthly_wage,
            "annual_wage": bm.annual_wage,
        })

    return templates.TemplateResponse(
        "benchmarks.html",
        {
            "request": request,
            "benchmarks": benchmarks_with_names,
            "national_avg": national_avg,
            "year": year,
            "years": [2024, 2023, 2022, 2021, 2020],
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


@app.get("/api/benchmarks")
async def api_benchmarks(year: int = 2023):
    """JSON API endpoint for industry wage benchmarks from Hagstofa."""
    benchmarks = hagstofa.get_all_benchmarks(year)
    national_avg = hagstofa.get_national_average(year)

    return {
        "year": year,
        "national_average": {
            "monthly": national_avg.monthly_wage if national_avg else None,
            "annual": national_avg.annual_wage if national_avg else None,
        } if national_avg else None,
        "industries": [
            {
                "code": b.industry_code,
                "name": b.industry_name,
                "name_en": hagstofa.INDUSTRY_NAMES_EN.get(b.industry_code, b.industry_code),
                "monthly_wage": b.monthly_wage,
                "annual_wage": b.annual_wage,
            }
            for b in benchmarks
        ],
        "source": "Hagstofa Íslands (Statistics Iceland)",
    }


# Health check endpoint
@app.get("/health")
async def health():
    return {"status": "ok"}
