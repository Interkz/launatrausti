"""
Launatrausti - Icelandic Salary Transparency Platform

FastAPI web application for viewing company salary rankings.
"""

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from . import database
from . import hagstofa
from .models import (
    ErrorDetail,
    CompanyRankingsResponse,
    CompanyDetailResponse,
    BenchmarksResponse,
    NationalAverage,
    IndustryBenchmark,
    SalariesResponse,
    CompanyFinancialsResponse,
    SalaryComparisonResponse,
    PlatformStatsResponse,
    HealthResponse,
)

API_DESCRIPTION = """\
**Launatrausti** (Icelandic for *wage trust*) is an open salary transparency
platform for Iceland. It calculates estimated average salaries per company from
publicly filed annual reports (*ársreikningar*) using the formula:

> **Average Salary = Launakostnaður ÷ Meðalfjöldi starfsmanna**

## Data Sources

| Source | Description |
|--------|-------------|
| **Skatturinn** | Company metadata (name, kennitala, ISAT code) |
| **Hagstofa Íslands** | Industry wage benchmarks by ISAT category |
| **Annual Reports (PDFs)** | Company-specific financials (wage costs, employees, revenue) |
| **VR Union Surveys** | Job-title-level salary survey data |

## Endpoint Groups

- **Companies** — browse and search company salary data
- **Salaries** — VR union salary survey data by job title
- **Benchmarks** — Hagstofa industry-level wage benchmarks
- **Admin** — platform health and statistics

All monetary values are in **Icelandic króna (ISK)**.
"""

RESPONSES_404 = {404: {"model": ErrorDetail, "description": "Resource not found"}}
RESPONSES_500 = {500: {"description": "Internal server error"}}

tags_metadata = [
    {"name": "Pages", "description": "Server-rendered HTML pages (not intended for API consumers)"},
    {"name": "Companies", "description": "Company salary rankings, detailed profiles, and financial data"},
    {"name": "Salaries", "description": "VR union salary survey data filtered by job title and date"},
    {"name": "Benchmarks", "description": "Industry-level wage benchmarks from Hagstofa Íslands (Statistics Iceland)"},
    {"name": "Admin", "description": "Platform health checks and aggregate statistics"},
]

app = FastAPI(
    title="Launatrausti",
    description=API_DESCRIPTION,
    version="0.1.0",
    openapi_tags=tags_metadata,
    responses={
        422: {"description": "Validation error — invalid query parameters or path values"},
        500: {"description": "Internal server error"},
    },
)

# Set up templates
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@app.get("/", response_class=HTMLResponse, tags=["Pages"], summary="Rankings page")
async def index(
    request: Request,
    year: Optional[int] = None,
    sector: Optional[str] = None,
):
    """Renders the home page with companies ranked by average salary.

    Supports optional filtering by report year and business sector.
    Returns server-rendered HTML.
    """
    companies = database.get_ranked_companies(
        year=year, sector=sector, exclude_sample=True
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
            "selected_year": year,
            "selected_sector": sector,
            "has_real_data": has_real_data,
        }
    )


@app.get("/company/{company_id}", response_class=HTMLResponse, tags=["Pages"], summary="Company detail page")
async def company_detail(request: Request, company_id: int):
    """Renders the company detail page showing all annual reports,
    industry benchmark comparison, and salary analysis.

    Returns 404 if the company ID does not exist.
    """
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


@app.get("/benchmarks", response_class=HTMLResponse, tags=["Pages"], summary="Industry benchmarks page")
async def benchmarks_page(request: Request, year: int = 2023):
    """Renders the industry wage benchmarks page with data from Hagstofa Íslands.

    Shows average wages by industry sector for the selected year, with
    both Icelandic and English industry names.
    """
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


@app.get("/salaries", response_class=HTMLResponse, tags=["Pages"], summary="VR salary survey page")
async def salaries_page(
    request: Request,
    category: Optional[str] = None,
    survey_date: Optional[str] = None,
):
    """Renders the VR union salary survey page with job-title-level salary data.

    Supports filtering by job category (starfsstétt) and survey date.
    """
    surveys = database.get_vr_surveys(category=category, survey_date=survey_date)
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
            "selected_category": category,
            "dates": dates,
            "selected_date": survey_date,
        }
    )


@app.get("/company/{company_id}/financials", response_class=HTMLResponse, tags=["Pages"], summary="Company financials page")
async def company_financials_page(request: Request, company_id: int):
    """Renders the company financials page with detailed annual report data
    and computed trend metrics (salary CAGR, revenue CAGR).

    Returns 404 if the company ID does not exist.
    """
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


@app.get("/launaleynd", response_class=HTMLResponse, tags=["Pages"], summary="Salary secrecy gap analysis page")
async def launaleynd_page(request: Request):
    """Renders the launaleynd (salary secrecy) page comparing company average
    salaries against VR survey benchmarks to identify pay gaps.

    Companies paying significantly below the VR survey average are highlighted.
    """
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


@app.get(
    "/api/companies",
    response_model=CompanyRankingsResponse,
    tags=["Companies"],
    summary="List company salary rankings",
    description=(
        "Returns companies ranked by average salary in descending order. "
        "By default returns the latest available year for each company. "
        "Use the `year` parameter to filter to a specific report year. "
        "All salary and revenue values are in ISK."
    ),
)
async def api_companies(
    year: Optional[int] = None,
    limit: int = 100,
):
    companies = database.get_ranked_companies(year=year, limit=limit)
    return {"companies": companies, "year": year}


@app.get(
    "/api/company/{company_id}",
    response_model=CompanyDetailResponse,
    tags=["Companies"],
    summary="Get company detail",
    description=(
        "Returns full company metadata and all annual reports. "
        "Reports are ordered by year descending (most recent first). "
        "Includes financial fields like profit, operating costs, and equity ratio "
        "when available from the source annual report."
    ),
    responses=RESPONSES_404,
)
async def api_company(company_id: int):
    data = database.get_company_detail(company_id)
    if not data:
        raise HTTPException(status_code=404, detail="Company not found")
    return data


@app.get(
    "/api/benchmarks",
    response_model=BenchmarksResponse,
    tags=["Benchmarks"],
    summary="Get industry wage benchmarks",
    description=(
        "Returns average wages by industry from Hagstofa Íslands (Statistics Iceland) "
        "table VIN02003. Includes national average and per-industry breakdowns. "
        "Industry codes follow the ISAT/NACE classification system. "
        "Data is cached for 24 hours to avoid excessive API calls to Hagstofa."
    ),
)
async def api_benchmarks(year: int = 2023):
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


@app.get(
    "/api/salaries",
    response_model=SalariesResponse,
    tags=["Salaries"],
    summary="List VR salary survey data",
    description=(
        "Returns salary data from VR union surveys, with job-title-level detail "
        "including mean, median, 25th/75th percentile wages, and response counts. "
        "Filter by job category (starfsstétt) or survey date. "
        "Also returns available filter options for categories and dates."
    ),
)
async def api_salaries(
    category: Optional[str] = None,
    survey_date: Optional[str] = None,
):
    surveys = database.get_vr_surveys(category=category, survey_date=survey_date)
    categories = database.get_vr_categories()

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT DISTINCT survey_date FROM vr_salary_surveys ORDER BY survey_date DESC"
    )
    dates = [row["survey_date"] for row in cursor.fetchall()]
    conn.close()

    return {"surveys": surveys, "categories": categories, "dates": dates}


@app.get(
    "/api/company/{company_id}/financials",
    response_model=CompanyFinancialsResponse,
    tags=["Companies"],
    summary="Get company financials",
    description=(
        "Returns the full financial profile for a company including all annual reports "
        "and computed trend metrics. Reports are ordered by year ascending to support "
        "time-series analysis. Trends include compound annual growth rates (CAGR) for "
        "salary and revenue when at least 2 years of data are available."
    ),
    responses=RESPONSES_404,
)
async def api_company_financials(company_id: int):
    financials = database.get_company_financials(company_id)
    if not financials or not financials.get("company"):
        raise HTTPException(status_code=404, detail="Company not found")
    return financials


@app.get(
    "/api/company/{company_id}/salary-comparison",
    response_model=SalaryComparisonResponse,
    tags=["Salaries"],
    summary="Compare company salary to VR survey",
    description=(
        "Compares a company's calculated average salary from its most recent annual report "
        "against the VR union salary survey average. Returns the percentage difference "
        "and VR survey statistics (min, max, count). A positive `diff_pct` means the "
        "company pays above the VR average."
    ),
    responses=RESPONSES_404,
)
async def api_salary_comparison(company_id: int):
    comparison = database.get_salary_comparison(company_id)
    if not comparison:
        raise HTTPException(status_code=404, detail="Company not found")
    return comparison


@app.get(
    "/api/stats",
    response_model=PlatformStatsResponse,
    tags=["Admin"],
    summary="Get platform statistics",
    description=(
        "Returns aggregate statistics about the Launatrausti platform including "
        "total companies, annual reports, VR survey entries, scrape log entries, "
        "and the year range of available data."
    ),
)
async def api_stats():
    return database.get_platform_stats()


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Admin"],
    summary="Health check",
    description="Returns a simple health status. Use this endpoint for uptime monitoring and load balancer checks.",
)
async def health():
    return {"status": "ok"}
