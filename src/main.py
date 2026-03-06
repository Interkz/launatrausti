"""
Launatrausti - Icelandic Salary Transparency Platform

FastAPI web application for viewing company salary rankings.
"""

from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from . import database
from . import hagstofa
from .validation import (
    FIELD_MESSAGES_IS,
    IndexParams,
    BenchmarksParams,
    SalariesParams,
    CompaniesApiParams,
    CompanyIdPath,
)

app = FastAPI(
    title="Launatrausti",
    description="Icelandic Salary Transparency Platform",
    version="0.1.0"
)

# Set up templates
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """Return structured validation errors with field-level details and Icelandic messages."""
    details = []
    for err in exc.errors():
        loc = err.get("loc", ())
        # Extract field name from location tuple (e.g. ("query", "year") -> "year")
        field = loc[-1] if loc else "unknown"
        message = err.get("msg", "Validation error")
        message_is = FIELD_MESSAGES_IS.get(str(field), "Villa í inntaki")
        details.append({
            "field": str(field),
            "message": message,
            "message_is": message_is,
            "type": err.get("type", ""),
        })
    return JSONResponse(status_code=422, content={"detail": details})


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    params: IndexParams = Depends(),
):
    """Home page with ranked list of companies by average salary."""
    companies = database.get_ranked_companies(
        year=params.year, sector=params.sector, exclude_sample=True
    )
    years = database.get_available_years()

    has_real_data = any(
        c.get("source_pdf") != "sample_data"
        for c in companies
        if c.get("source_pdf")
    )

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "companies": companies,
            "years": years,
            "selected_year": params.year,
            "selected_sector": params.sector,
            "has_real_data": has_real_data,
        }
    )


@app.get("/company/{company_id}", response_class=HTMLResponse)
async def company_detail(request: Request, company_id: CompanyIdPath):
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

    # Load financials and salary comparison
    financials = database.get_company_financials(company_id)
    salary_comparison = database.get_salary_comparison(company_id)

    return templates.TemplateResponse(
        "company.html",
        {
            "request": request,
            "company": company,
            "reports": reports,
            "benchmark": benchmark,
            "national_avg": national_avg,
            "industry_name": industry_name,
            "financials": financials,
            "salary_comparison": salary_comparison,
        }
    )


@app.get("/benchmarks", response_class=HTMLResponse)
async def benchmarks_page(request: Request, params: BenchmarksParams = Depends()):
    """Industry wage benchmarks page."""
    benchmarks = hagstofa.get_all_benchmarks(params.year)
    national_avg = hagstofa.get_national_average(params.year)

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
            "year": params.year,
            "years": [2024, 2023, 2022, 2021, 2020],
        }
    )


@app.get("/salaries", response_class=HTMLResponse)
async def salaries_page(
    request: Request,
    params: SalariesParams = Depends(),
):
    """VR salary survey data page."""
    surveys = database.get_vr_surveys(category=params.category, survey_date=params.survey_date)
    categories = database.get_vr_categories()

    # Get distinct survey dates
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT DISTINCT survey_date FROM vr_salary_surveys ORDER BY survey_date DESC"
    )
    dates = [row["survey_date"] for row in cursor.fetchall()]
    conn.close()

    return templates.TemplateResponse(
        "salaries.html",
        {
            "request": request,
            "surveys": surveys,
            "categories": categories,
            "selected_category": params.category,
            "dates": dates,
            "selected_date": params.survey_date,
        }
    )


@app.get("/company/{company_id}/financials", response_class=HTMLResponse)
async def company_financials_page(request: Request, company_id: CompanyIdPath):
    """Company financials detail page."""
    financials = database.get_company_financials(company_id)

    if not financials or not financials.get("company"):
        raise HTTPException(status_code=404, detail="Company not found")

    return templates.TemplateResponse(
        "financials.html",
        {
            "request": request,
            "company": financials["company"],
            "reports": financials["reports"],
            "trends": financials["trends"],
        }
    )


@app.get("/launaleynd", response_class=HTMLResponse)
async def launaleynd_page(request: Request):
    """Salary secrecy gap analysis page."""
    # Compare company avg salaries to VR survey averages
    conn = database.get_connection()
    cursor = conn.cursor()

    # Get VR survey overall average (latest survey date)
    cursor.execute("""
        SELECT survey_date, AVG(medaltal) as vr_avg
        FROM vr_salary_surveys
        GROUP BY survey_date
        ORDER BY survey_date DESC
        LIMIT 1
    """)
    vr_row = cursor.fetchone()

    gaps = []
    if vr_row:
        vr_avg = vr_row["vr_avg"]
        vr_date = vr_row["survey_date"]

        # Get companies with their latest avg salary
        cursor.execute("""
            SELECT
                c.id, c.name, c.kennitala, c.sector,
                ar.avg_salary, ar.year, ar.source_pdf
            FROM companies c
            JOIN annual_reports ar ON c.id = ar.company_id
            WHERE ar.year = (
                SELECT MAX(ar2.year) FROM annual_reports ar2
                WHERE ar2.company_id = c.id
            )
            AND (ar.is_sample = 0 OR ar.is_sample IS NULL)
            ORDER BY ar.avg_salary ASC
        """)

        for row in cursor.fetchall():
            company_annual = row["avg_salary"]
            # VR survey data is monthly, company avg_salary is annual
            vr_annual = vr_avg * 12
            gap = company_annual - vr_annual
            gap_pct = round((gap / vr_annual) * 100, 1) if vr_annual else 0

            gaps.append({
                "id": row["id"],
                "name": row["name"],
                "kennitala": row["kennitala"],
                "sector": row["sector"],
                "avg_salary": company_annual,
                "year": row["year"],
                "vr_expected": round(vr_annual),
                "gap": round(gap),
                "gap_pct": gap_pct,
                "source_pdf": row["source_pdf"],
            })

        # Sort by gap ascending (largest negative gap first = most underpaying)
        gaps.sort(key=lambda x: x["gap"])
    else:
        vr_date = None

    conn.close()

    return templates.TemplateResponse(
        "launaleynd.html",
        {
            "request": request,
            "gaps": gaps,
            "vr_date": vr_date,
        }
    )


@app.get("/api/companies")
async def api_companies(params: CompaniesApiParams = Depends()):
    """JSON API endpoint for company rankings."""
    companies = database.get_ranked_companies(year=params.year, limit=params.limit)
    return {"companies": companies, "year": params.year}


@app.get("/api/company/{company_id}")
async def api_company(company_id: CompanyIdPath):
    """JSON API endpoint for company detail."""
    data = database.get_company_detail(company_id)
    if not data:
        raise HTTPException(status_code=404, detail="Company not found")
    return data


@app.get("/api/benchmarks")
async def api_benchmarks(params: BenchmarksParams = Depends()):
    """JSON API endpoint for industry wage benchmarks from Hagstofa."""
    benchmarks = hagstofa.get_all_benchmarks(params.year)
    national_avg = hagstofa.get_national_average(params.year)

    return {
        "year": params.year,
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


@app.get("/api/salaries")
async def api_salaries(params: SalariesParams = Depends()):
    """JSON API endpoint for VR salary survey data."""
    surveys = database.get_vr_surveys(category=params.category, survey_date=params.survey_date)
    categories = database.get_vr_categories()

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT DISTINCT survey_date FROM vr_salary_surveys ORDER BY survey_date DESC"
    )
    dates = [row["survey_date"] for row in cursor.fetchall()]
    conn.close()

    return {"surveys": surveys, "categories": categories, "dates": dates}


@app.get("/api/company/{company_id}/financials")
async def api_company_financials(company_id: CompanyIdPath):
    """JSON API endpoint for company financials."""
    financials = database.get_company_financials(company_id)
    if not financials or not financials.get("company"):
        raise HTTPException(status_code=404, detail="Company not found")
    return financials


@app.get("/api/company/{company_id}/salary-comparison")
async def api_salary_comparison(company_id: CompanyIdPath):
    """JSON API endpoint for company salary comparison with VR survey data."""
    comparison = database.get_salary_comparison(company_id)
    if not comparison:
        raise HTTPException(status_code=404, detail="Company not found")
    return comparison


@app.get("/api/stats")
async def api_stats():
    """JSON API endpoint for platform statistics."""
    return database.get_platform_stats()


# Health check endpoint
@app.get("/health")
async def health():
    return {"status": "ok"}
