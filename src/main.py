"""
Launatrausti - Icelandic Salary Transparency Platform

FastAPI web application for viewing company salary rankings.
"""

import logging
import re
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
    salary: Optional[int] = None,
    year: Optional[int] = None,
    sector: Optional[str] = None,
    education: Optional[str] = None,
):
    """Home page: salary search hero + company rankings below the fold."""
    # Always load rankings for below-the-fold section
    companies = database.get_ranked_companies(
        year=year, sector=sector, exclude_sample=True
    )
    years = database.get_available_years()

    has_real_data = any(
        c.get("source_pdf") != "sample_data"
        for c in companies
        if c.get("source_pdf")
    )

    monthly_salaries = [c["avg_salary"] // 12 for c in companies if c.get("avg_salary")]
    avg_monthly = sum(monthly_salaries) // len(monthly_salaries) if monthly_salaries else 0

    # Salary search results
    percentile = None
    nearby_occupations = []
    next_tier = []
    matching_jobs = []
    matching_companies = []

    all_occ_flat = database.get_all_occupations_flat(year=2024, salary_type="heildarlaun")
    total_occupations = len(all_occ_flat)

    if salary and salary > 0:
        # Percentile: what % of occupation medians are below this salary
        all_medians = [occ.get("median") for occ in all_occ_flat if occ.get("median")]
        if all_medians:
            below = sum(1 for m in all_medians if m < salary)
            percentile = round(below / len(all_medians) * 100)

        # Nearby occupations: 5 above, 5 below
        sorted_occ = sorted(all_occ_flat, key=lambda x: x.get("median") or 0)
        above = [o for o in sorted_occ if (o.get("median") or 0) >= salary]
        below_list = [o for o in sorted_occ if (o.get("median") or 0) < salary]
        nearby_above = above[:5]
        nearby_below = list(reversed(below_list[-5:]))
        for occ in nearby_above + nearby_below:
            occ["display_name"] = re.sub(r'^\d[\d\s*]*\s+', '', occ.get("occupation_name", ""))
        nearby_occupations = nearby_below + nearby_above

        # "Næsta stig" — occupations paying 50-150k more than you
        next_tier = [
            o for o in sorted_occ
            if (o.get("median") or 0) > salary and (o.get("median") or 0) <= salary + 150000
        ][:6]
        for occ in next_tier:
            occ["display_name"] = re.sub(r'^\d[\d\s*]*\s+', '', occ.get("occupation_name", ""))
            occ["gap"] = (occ.get("median") or 0) - salary

        # Matching jobs: salary within ±100k of target
        matching_jobs = database.get_active_jobs(
            salary_min=salary - 100000,
            salary_max=salary + 100000,
            sort="salary",
            limit=10,
        )

        # Matching companies: avg monthly salary near target
        matching_companies = database.get_companies_near_salary(salary)

    # Stats for hero section
    stats = database.get_platform_stats()
    job_count = database.get_job_count()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "salary": salary,
            "education": education or "all",
            "percentile": percentile,
            "nearby_occupations": nearby_occupations,
            "next_tier": next_tier if salary else [],
            "matching_jobs": matching_jobs,
            "matching_companies": matching_companies,
            "companies": companies,
            "years": years,
            "selected_year": year,
            "selected_sector": sector,
            "has_real_data": has_real_data,
            "avg_monthly": avg_monthly,
            "total_companies": stats["total_companies"],
            "total_jobs": job_count,
            "total_occupations": total_occupations,
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
async def benchmarks_page(request: Request, year: int = 2024):
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
    order: str = "desc",
    year: int = 2024,
    my_salary: Optional[int] = None,
    salary_type: str = "heildarlaun",
):
    """Salary comparison page — aurbjörg-style leaderboard sorted by salary."""
    selected = None
    time_series = []
    search_results = []

    if isco:
        time_series = database.get_occupation_detail(isco, salary_type=salary_type)
        if time_series:
            selected = next((r for r in time_series if r["year"] == year), time_series[0])
            selected["display_name"] = re.sub(r'^\d[\d\s*]*\s+', '', selected.get("occupation_name", ""))
            selected["isco_code_clean"] = re.sub(r'[*\s]', '', selected.get("isco_code", ""))

    if q:
        search_results = database.search_occupations(q, year=year, limit=50, salary_type=salary_type)

    # Always load grouped data for the leaderboard view
    grouped = database.get_all_occupations_grouped(year=year, sort_by=sort, salary_type=salary_type)
    available_years = database.get_occupation_years()

    # Flat sorted list for the leaderboard
    all_occupations = []
    for grp_list in grouped.values():
        all_occupations.extend(grp_list)
    all_occupations.sort(key=lambda x: x.get(sort) or 0, reverse=(order != "asc"))
    total_occupations = len(all_occupations)

    # Add display_name (strip ISCO codes) and isco_group (first digit) for each occupation
    for occ in all_occupations:
        occ["display_name"] = re.sub(r'^\d[\d\s*]*\s+', '', occ.get("occupation_name", ""))
        occ["isco_group"] = occ.get("isco_code", "0")[0] if occ.get("isco_code") else "0"
    for occ in search_results:
        occ["display_name"] = re.sub(r'^\d[\d\s*]*\s+', '', occ.get("occupation_name", ""))
        occ["isco_group"] = occ.get("isco_code", "0")[0] if occ.get("isco_code") else "0"

    # Max salary for mini-bar width calculation
    max_salary = max((occ.get(sort) or 0) for occ in all_occupations) if all_occupations else 1
    if max_salary == 0:
        max_salary = 1

    # National median: use Hagstofa published figure (845K for 2024 full-time)
    national_median = 845_000

    # Salary percentile calculation + nearby occupations
    percentile = None
    nearby_above = []
    nearby_below = []
    if my_salary and my_salary > 0:
        all_medians = [occ.get("median") for occ in all_occupations if occ.get("median")]
        if all_medians:
            below = sum(1 for m in all_medians if m < my_salary)
            percentile = round(below / len(all_medians) * 100)
            # Find 3 occupations above and 3 below
            above = [occ for occ in all_occupations if (occ.get("median") or 0) >= my_salary]
            below_list = [occ for occ in all_occupations if (occ.get("median") or 0) < my_salary]
            nearby_above = above[-10:] if above else []  # closest 10 above
            nearby_above.reverse()  # highest first
            nearby_below = below_list[:10] if below_list else []  # closest 10 below

    # 2025 estimates for occupation detail
    estimated_2025 = None
    if isco and time_series and len(time_series) >= 2:
        # time_series is newest-first; compute avg YoY growth from last 3 years
        growth_rates = []
        for i in range(min(3, len(time_series) - 1)):
            curr = time_series[i]
            prev = time_series[i + 1]
            if curr.get("median") and prev.get("median") and prev["median"] > 0:
                rate = (curr["median"] - prev["median"]) / prev["median"]
                growth_rates.append(rate)
        if growth_rates:
            avg_growth = sum(growth_rates) / len(growth_rates)
            avg_growth = max(-0.15, min(0.15, avg_growth))  # cap at ±15%
            latest = time_series[0]
            if latest.get("median") and latest["year"] < 2025:
                estimated_2025 = {
                    "year": 2025,
                    "median": round(latest["median"] * (1 + avg_growth)),
                    "mean": round(latest["mean"] * (1 + avg_growth)) if latest.get("mean") else None,
                    "p25": round(latest["p25"] * (1 + avg_growth)) if latest.get("p25") else None,
                    "p75": round(latest["p75"] * (1 + avg_growth)) if latest.get("p75") else None,
                    "growth_rate": avg_growth,
                    "estimated": True,
                }

    return templates.TemplateResponse(
        "samanburdur.html",
        {
            "request": request,
            "q": q or "",
            "isco": isco,
            "group": group,
            "sort": sort,
            "order": order,
            "salary_type": salary_type,
            "year": year,
            "my_salary": my_salary,
            "selected": selected,
            "time_series": time_series,
            "search_results": search_results,
            "grouped": grouped,
            "all_occupations": all_occupations,
            "total_occupations": total_occupations,
            "max_salary": max_salary,
            "isco_groups": database.ISCO_MAJOR_GROUPS,
            "isco_groups_en": database.ISCO_MAJOR_GROUPS_EN,
            "available_years": available_years,
            "national_median": national_median,
            "percentile": percentile,
            "nearby_above": nearby_above,
            "nearby_below": nearby_below,
            "estimated_2025": estimated_2025,
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


@app.get("/job/{job_id}", response_class=HTMLResponse)
async def job_detail(request: Request, job_id: int):
    """Job detail page with full description, salary breakdown, company cross-reference."""
    job = database.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    related = database.get_related_jobs(job["employer_name"], job_id)

    # Get industry benchmark if company is matched
    benchmark = None
    if job.get("company_id") and job.get("isat_code"):
        benchmark = hagstofa.get_industry_benchmark(
            job["isat_code"], job.get("company_report_year") or 2024
        )

    return templates.TemplateResponse(
        "job_detail.html",
        {
            "request": request,
            "job": job,
            "related": related,
            "benchmark": benchmark,
        },
    )


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
