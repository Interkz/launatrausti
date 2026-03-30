"""
Launatrausti - Icelandic Salary Transparency Platform

FastAPI web application for viewing company salary rankings.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from . import database
from . import hagstofa
from .startup import run_startup_checks, StartupError
from .security import SecurityHeadersMiddleware

logger = logging.getLogger("launatrausti")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup checks before the app begins serving requests."""
    try:
        results = run_startup_checks()
        app.state.startup_results = results
    except StartupError as e:
        logger.error("Startup check failed: %s", e)
        raise
    yield


app = FastAPI(
    title="Launatrausti",
    description="Icelandic Salary Transparency Platform",
    version="0.1.0",
    lifespan=lifespan,
)

# Security headers on all responses
app.add_middleware(SecurityHeadersMiddleware)

# Set up templates
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@app.get("/", response_class=HTMLResponse)
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

    # Calculate average monthly salary for color coding
    monthly_salaries = [c["avg_salary"] // 12 for c in companies if c.get("avg_salary")]
    avg_monthly = sum(monthly_salaries) // len(monthly_salaries) if monthly_salaries else 0

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "companies": companies,
            "years": years,
            "selected_year": year,
            "selected_sector": sector,
            "has_real_data": has_real_data,
            "avg_monthly": avg_monthly,
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

    # Load financials, salary comparison, and open jobs
    financials = database.get_company_financials(company_id)
    salary_comparison = database.get_salary_comparison(company_id)
    jobs = database.get_company_jobs(company_id)

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
            "jobs": jobs,
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


@app.get("/salaries", response_class=HTMLResponse)
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


@app.get("/company/{company_id}/financials", response_class=HTMLResponse)
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


@app.get("/samanburdur", response_class=HTMLResponse)
async def samanburdur_page(
    request: Request,
    q: Optional[str] = None,
    isco: Optional[str] = None,
    group: Optional[str] = None,
    sort: str = "median",
    year: int = 2024,
    my_salary: Optional[int] = None,
):
    """Salary comparison page — aurbjörg-style leaderboard sorted by salary."""
    selected = None
    time_series = []
    search_results = []

    if isco:
        time_series = database.get_occupation_detail(isco)
        if time_series:
            selected = next((r for r in time_series if r["year"] == year), time_series[0])

    if q:
        search_results = database.search_occupations(q, year=year, limit=50)

    # Always load grouped data for the leaderboard view
    grouped = database.get_all_occupations_grouped(year=year, sort_by=sort)
    available_years = database.get_occupation_years()

    # National median: use Hagstofa published figure (845K for 2024 full-time)
    # This is the actual national median, not a derived mean-of-medians
    national_median = 845_000

    # Salary percentile calculation
    percentile = None
    salary_context = None
    if my_salary and my_salary > 0:
        all_medians = []
        for grp_list in grouped.values():
            for occ in grp_list:
                if occ.get("median"):
                    all_medians.append(occ["median"])
        if all_medians:
            below = sum(1 for m in all_medians if m < my_salary)
            percentile = round(below / len(all_medians) * 100)
            # Find closest occupations
            closest_above = None
            closest_below = None
            for grp_list in grouped.values():
                for occ in grp_list:
                    med = occ.get("median", 0)
                    if med and med >= my_salary and (closest_above is None or med < closest_above["median"]):
                        closest_above = occ
                    if med and med < my_salary and (closest_below is None or med > closest_below["median"]):
                        closest_below = occ
            salary_context = {
                "percentile": percentile,
                "above": closest_above,
                "below": closest_below,
                "total_occupations": len(all_medians),
            }

    return templates.TemplateResponse(
        "samanburdur.html",
        {
            "request": request,
            "q": q or "",
            "isco": isco,
            "group": group,
            "sort": sort,
            "year": year,
            "my_salary": my_salary,
            "selected": selected,
            "time_series": time_series,
            "search_results": search_results,
            "grouped": grouped,
            "isco_groups": database.ISCO_MAJOR_GROUPS,
            "isco_groups_en": database.ISCO_MAJOR_GROUPS_EN,
            "available_years": available_years,
            "national_median": national_median,
            "percentile": percentile,
            "salary_context": salary_context,
        }
    )


@app.get("/api/occupations")
async def api_occupations(q: str = "", year: int = 2024, limit: int = 20):
    """JSON API for occupation search — powers autocomplete."""
    results = database.search_occupations(q, year=year, limit=limit)
    return {"occupations": results, "query": q, "year": year}


@app.get("/api/occupation/{isco_code}")
async def api_occupation_detail(isco_code: str):
    """JSON API for single occupation with all years."""
    data = database.get_occupation_detail(isco_code)
    if not data:
        raise HTTPException(status_code=404, detail="Occupation not found")
    return {"occupation": data}


@app.get("/stettarfelog", response_class=HTMLResponse)
async def stettarfelog_page(
    request: Request,
    my_salary: Optional[int] = None,
    sort: str = "members",
):
    """Union comparison page."""
    unions = database.get_all_unions()

    # Sort options
    if sort == "fee":
        unions.sort(key=lambda u: u.get("fee_pct") or 0)
    elif sort == "sick":
        unions.sort(key=lambda u: u.get("sick_pay_days") or 0, reverse=True)
    # default: members (already sorted from DB)

    return templates.TemplateResponse(
        "stettarfelog.html",
        {
            "request": request,
            "unions": unions,
            "my_salary": my_salary,
            "sort": sort,
        },
    )


@app.get("/api/unions")
async def api_unions():
    """JSON API for union data."""
    unions = database.get_all_unions()
    return {"unions": unions, "count": len(unions)}


@app.get("/jobs", response_class=HTMLResponse)
async def jobs_page(
    request: Request,
    q: Optional[str] = None,
    salary_min: Optional[int] = None,
    salary_max: Optional[int] = None,
    location: Optional[str] = None,
    employment_type: Optional[str] = None,
    remote_policy: Optional[str] = None,
    source: Optional[str] = None,
    sort: str = "salary",
    limit: int = 50,
    offset: int = 0,
):
    """Job listings page with search, filtering, and cross-referencing."""
    jobs = database.get_active_jobs(
        q=q,
        salary_min=salary_min,
        salary_max=salary_max,
        location=location,
        employment_type=employment_type,
        remote_policy=remote_policy,
        source=source,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    stats = database.get_job_stats()
    filter_options = database.get_job_filter_options()
    total_count = database.get_job_count(
        q=q, salary_min=salary_min, salary_max=salary_max,
        location=location, employment_type=employment_type, source=source,
    )

    return templates.TemplateResponse(
        "jobs.html",
        {
            "request": request,
            "jobs": jobs,
            "stats": stats,
            "filter_options": filter_options,
            "total_count": total_count,
            "q": q,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "location": location,
            "employment_type": employment_type,
            "remote_policy": remote_policy,
            "source": source,
            "sort": sort,
            "limit": limit,
            "offset": offset,
        },
    )


@app.get("/api/jobs")
async def api_jobs(
    q: Optional[str] = None,
    salary_min: Optional[int] = None,
    salary_max: Optional[int] = None,
    location: Optional[str] = None,
    employment_type: Optional[str] = None,
    remote_policy: Optional[str] = None,
    source: Optional[str] = None,
    sort: str = "salary",
    limit: int = 50,
    offset: int = 0,
):
    """JSON API for job listings with search and cross-referencing."""
    jobs = database.get_active_jobs(
        q=q,
        salary_min=salary_min,
        salary_max=salary_max,
        location=location,
        employment_type=employment_type,
        remote_policy=remote_policy,
        source=source,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    stats = database.get_job_stats()
    total = database.get_job_count(
        q=q, salary_min=salary_min, salary_max=salary_max,
        location=location, employment_type=employment_type, source=source,
    )
    return {"jobs": jobs, "stats": stats, "total": total, "limit": limit, "offset": offset}


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


@app.get("/api/salaries")
async def api_salaries(
    category: Optional[str] = None,
    survey_date: Optional[str] = None,
):
    """JSON API endpoint for VR salary survey data."""
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


@app.get("/api/company/{company_id}/financials")
async def api_company_financials(company_id: int):
    """JSON API endpoint for company financials."""
    financials = database.get_company_financials(company_id)
    if not financials or not financials.get("company"):
        raise HTTPException(status_code=404, detail="Company not found")
    return financials


@app.get("/api/company/{company_id}/salary-comparison")
async def api_salary_comparison(company_id: int):
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
    """Basic health check — returns startup check results if available."""
    result = {"status": "ok"}
    if hasattr(app.state, "startup_results"):
        result["startup"] = app.state.startup_results
    return result
