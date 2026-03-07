"""
API v1 — all JSON endpoints for Launatrausti.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException

from .. import database
from .. import hagstofa

router = APIRouter(tags=["v1"])


@router.get("/companies")
async def api_companies(year: Optional[int] = None, limit: int = 100):
    """JSON API endpoint for company rankings."""
    companies = database.get_ranked_companies(year=year, limit=limit)
    return {"companies": companies, "year": year}


@router.get("/company/{company_id}")
async def api_company(company_id: int):
    """JSON API endpoint for company detail."""
    data = database.get_company_detail(company_id)
    if not data:
        raise HTTPException(status_code=404, detail="Company not found")
    return data


@router.get("/benchmarks")
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


@router.get("/salaries")
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


@router.get("/company/{company_id}/financials")
async def api_company_financials(company_id: int):
    """JSON API endpoint for company financials."""
    financials = database.get_company_financials(company_id)
    if not financials or not financials.get("company"):
        raise HTTPException(status_code=404, detail="Company not found")
    return financials


@router.get("/company/{company_id}/salary-comparison")
async def api_salary_comparison(company_id: int):
    """JSON API endpoint for company salary comparison with VR survey data."""
    comparison = database.get_salary_comparison(company_id)
    if not comparison:
        raise HTTPException(status_code=404, detail="Company not found")
    return comparison


@router.get("/stats")
async def api_stats():
    """JSON API endpoint for platform statistics."""
    return database.get_platform_stats()
