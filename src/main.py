"""
Launatrausti - Icelandic Salary Transparency Platform

FastAPI web application for viewing company salary rankings.
"""

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from . import database
from . import hagstofa
from .schemas import (
    BenchmarksResponse,
    CompaniesResponse,
    CompanyDetailResponse,
    FinancialsResponse,
    HealthResponse,
    PlatformStatsResponse,
    SalariesResponse,
    SalaryComparisonResponse,
)

tags_metadata = [
    {
        "name": "Pages",
        "description": "Server-rendered HTML pages. Not intended for programmatic use.",
    },
    {
        "name": "Companies",
        "description": "Company salary rankings, details, and financial data derived from annual reports (ársreikningar).",
    },
    {
        "name": "Benchmarks",
        "description": "Industry wage benchmarks from Hagstofa Íslands (Statistics Iceland).",
    },
    {
        "name": "Salaries",
        "description": "VR union salary survey data by job title and category.",
    },
    {
        "name": "Platform",
        "description": "Platform health and statistics.",
    },
]

app = FastAPI(
    title="Launatrausti",
    summary="Icelandic Salary Transparency Platform",
    description=(
        "Launatrausti calculates estimated average salaries per company using public data:\n\n"
        "**Average Salary = Launakostnaður (wage costs) ÷ Meðalfjöldi starfsmanna (employee count)**\n\n"
        "Data comes from mandatory annual reports (ársreikningar), "
        "Hagstofa Íslands industry benchmarks, and VR union salary surveys.\n\n"
        "### Data Sources\n"
        "| Source | Description |\n"
        "|--------|-------------|\n"
        "| **Skatturinn** | Company metadata (kennitala, ISAT code, status) |\n"
        "| **Hagstofa Íslands** | Industry average wages by ISAT category |\n"
        "| **VR Salary Surveys** | Job-level salary distributions |\n"
        "| **Annual Reports (PDFs)** | Company-specific wage costs and employee counts |\n"
    ),
    version="0.1.0",
    openapi_tags=tags_metadata,
)

# Set up templates
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@app.get("/", response_class=HTMLResponse, tags=["Pages"], include_in_schema=False)
async def index(
    request: Request,
    year: Optional[int] = None,
    sector: Optional[str] = None,
):
    """Home page with ranked list of companies by average salary."""
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


@app.get("/company/{company_id}", response_class=HTMLResponse, tags=["Pages"], include_in_schema=False)
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


@app.get("/benchmarks", response_class=HTMLResponse, tags=["Pages"], include_in_schema=False)
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


@app.get("/salaries", response_class=HTMLResponse, tags=["Pages"], include_in_schema=False)
async def salaries_page(
    request: Request,
    category: Optional[str] = None,
    survey_date: Optional[str] = None,
):
    """VR salary survey data page."""
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


@app.get("/company/{company_id}/financials", response_class=HTMLResponse, tags=["Pages"], include_in_schema=False)
async def company_financials_page(request: Request, company_id: int):
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


@app.get("/launaleynd", response_class=HTMLResponse, tags=["Pages"], include_in_schema=False)
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


@app.get("/api/companies", response_model=CompaniesResponse, tags=["Companies"])
async def api_companies(
    year: Optional[int] = Query(None, description="Filter by report year. Omit to get latest year per company."),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of companies to return"),
):
    """List companies ranked by average salary (highest first).

    Returns company metadata and salary figures from annual reports.
    Each company's average salary is calculated as: launakostnaður ÷ starfsmenn.
    """
    companies = database.get_ranked_companies(year=year, limit=limit)
    return {"companies": companies, "year": year}


@app.get("/api/company/{company_id}", response_model=CompanyDetailResponse, tags=["Companies"])
async def api_company(company_id: int):
    """Get detailed information for a single company.

    Returns company metadata and all available annual reports sorted by year (newest first).
    """
    data = database.get_company_detail(company_id)
    if not data:
        raise HTTPException(status_code=404, detail="Company not found")
    return data


@app.get("/api/benchmarks", response_model=BenchmarksResponse, tags=["Benchmarks"])
async def api_benchmarks(
    year: int = Query(2023, ge=2014, le=2025, description="Year for benchmark data (available: 2014-2024)"),
):
    """Get industry wage benchmarks from Hagstofa Íslands.

    Returns average wages by ISAT industry category and the national average.
    Data is sourced from Hagstofa table VIN02003 (wages by industry).
    """
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


@app.get("/api/salaries", response_model=SalariesResponse, tags=["Salaries"])
async def api_salaries(
    category: Optional[str] = Query(None, description="Filter by job category (starfsstett)"),
    survey_date: Optional[str] = Query(None, description="Filter by survey date (YYYY-MM format)"),
):
    """Get VR union salary survey data.

    Returns salary distributions by job title, including mean, median, and percentiles.
    Can be filtered by job category and survey date.
    """
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


@app.get("/api/company/{company_id}/financials", response_model=FinancialsResponse, tags=["Companies"])
async def api_company_financials(company_id: int):
    """Get company financial history and growth trends.

    Returns all annual reports with extended financial fields (profit, operating costs,
    equity ratio, wage-to-revenue ratio) and computed CAGR trends when multiple years exist.
    """
    financials = database.get_company_financials(company_id)
    if not financials or not financials.get("company"):
        raise HTTPException(status_code=404, detail="Company not found")
    return financials


@app.get("/api/company/{company_id}/salary-comparison", response_model=SalaryComparisonResponse, tags=["Companies"])
async def api_salary_comparison(company_id: int):
    """Compare a company's average salary to VR survey averages.

    Shows how much a company's computed average salary deviates from the VR union
    survey average, with the percentage difference and survey range.
    """
    comparison = database.get_salary_comparison(company_id)
    if not comparison:
        raise HTTPException(status_code=404, detail="Company not found")
    return comparison


@app.get("/api/stats", response_model=PlatformStatsResponse, tags=["Platform"])
async def api_stats():
    """Get platform-wide statistics.

    Returns counts of companies, reports, survey entries, and the year range of available data.
    """
    return database.get_platform_stats()


@app.get("/health", response_model=HealthResponse, tags=["Platform"])
async def health():
    """Health check endpoint.

    Returns `{"status": "ok"}` when the service is running.
    """
    return {"status": "ok"}
