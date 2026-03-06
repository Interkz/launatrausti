"""Pydantic response models for the Launatrausti API."""

from typing import Optional
from pydantic import BaseModel, Field


# --- Company models ---

class CompanyRanking(BaseModel):
    id: int
    kennitala: str = Field(description="Company national ID (kennitala)")
    name: str
    isat_code: Optional[str] = Field(None, description="ISAT industry classification code")
    year: int
    launakostnadur: int = Field(description="Total wage costs in ISK")
    starfsmenn: float = Field(description="Average employee count")
    avg_salary: int = Field(description="Calculated average salary (launakostnadur / starfsmenn)")
    tekjur: Optional[int] = Field(None, description="Revenue in ISK")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": 1,
                    "kennitala": "5612903529",
                    "name": "Landsbankinn hf.",
                    "isat_code": "64.19",
                    "year": 2023,
                    "launakostnadur": 28500000000,
                    "starfsmenn": 1050.0,
                    "avg_salary": 27142857,
                    "tekjur": 85000000000,
                }
            ]
        }
    }


class CompaniesResponse(BaseModel):
    companies: list[CompanyRanking]
    year: Optional[int] = Field(None, description="Filter year, or null for latest available")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "companies": [
                        {
                            "id": 1,
                            "kennitala": "5612903529",
                            "name": "Landsbankinn hf.",
                            "isat_code": "64.19",
                            "year": 2023,
                            "launakostnadur": 28500000000,
                            "starfsmenn": 1050.0,
                            "avg_salary": 27142857,
                            "tekjur": 85000000000,
                        }
                    ],
                    "year": 2023,
                }
            ]
        }
    }


class AnnualReportDetail(BaseModel):
    id: int
    company_id: int
    year: int
    launakostnadur: int
    starfsmenn: float
    tekjur: Optional[int] = None
    avg_salary: int
    source_pdf: str
    extracted_at: Optional[str] = None
    hagnadur: Optional[int] = None
    rekstrarkostnadur: Optional[int] = None
    eiginfjarhlufall: Optional[float] = None
    laun_hlutfall_tekna: Optional[float] = None
    source_type: Optional[str] = None
    confidence: Optional[float] = None
    is_sample: Optional[int] = None


class CompanyInfo(BaseModel):
    id: int
    kennitala: str
    name: str
    isat_code: Optional[str] = None
    address: Optional[str] = None
    legal_form: Optional[str] = None
    sector: Optional[str] = None
    employee_count_latest: Optional[int] = None
    updated_at: Optional[str] = None


class CompanyDetailResponse(BaseModel):
    company: CompanyInfo
    reports: list[AnnualReportDetail]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "company": {
                        "id": 1,
                        "kennitala": "5612903529",
                        "name": "Landsbankinn hf.",
                        "isat_code": "64.19",
                        "address": "Austurstræti 11",
                        "legal_form": "hf.",
                        "sector": "Finance",
                        "employee_count_latest": 1050,
                        "updated_at": None,
                    },
                    "reports": [
                        {
                            "id": 1,
                            "company_id": 1,
                            "year": 2023,
                            "launakostnadur": 28500000000,
                            "starfsmenn": 1050.0,
                            "tekjur": 85000000000,
                            "avg_salary": 27142857,
                            "source_pdf": "landsbankinn_2023.pdf",
                            "extracted_at": "2024-12-31T12:00:00",
                        }
                    ],
                }
            ]
        }
    }


# --- Benchmark models ---

class IndustryBenchmark(BaseModel):
    code: str = Field(description="Hagstofa industry letter code (e.g. J, K, F)")
    name: str = Field(description="Industry name in Icelandic")
    name_en: str = Field(description="Industry name in English")
    monthly_wage: int = Field(description="Average monthly wage in ISK")
    annual_wage: int = Field(description="Average annual wage in ISK (monthly * 12)")


class NationalAverage(BaseModel):
    monthly: Optional[int] = Field(None, description="National average monthly wage in ISK")
    annual: Optional[int] = Field(None, description="National average annual wage in ISK")


class BenchmarksResponse(BaseModel):
    year: int
    national_average: Optional[NationalAverage] = None
    industries: list[IndustryBenchmark]
    source: str = "Hagstofa Íslands (Statistics Iceland)"

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "year": 2023,
                    "national_average": {"monthly": 935000, "annual": 11220000},
                    "industries": [
                        {
                            "code": "J",
                            "name": "Upplýsingar og fjarskipti",
                            "name_en": "Information & Communication",
                            "monthly_wage": 1009000,
                            "annual_wage": 12108000,
                        },
                        {
                            "code": "K",
                            "name": "Fjármála- og vátryggingastarfsemi",
                            "name_en": "Finance & Insurance",
                            "monthly_wage": 1235000,
                            "annual_wage": 14820000,
                        },
                    ],
                    "source": "Hagstofa Íslands (Statistics Iceland)",
                }
            ]
        }
    }


# --- Salary survey models ---

class VRSurveyEntry(BaseModel):
    id: int
    survey_date: str = Field(description="Survey date (YYYY-MM format)")
    starfsheiti: str = Field(description="Job title in Icelandic")
    starfsstett: Optional[str] = Field(None, description="Job category")
    medaltal: int = Field(description="Average monthly salary in ISK")
    midgildi: Optional[int] = Field(None, description="Median monthly salary in ISK")
    p25: Optional[int] = Field(None, description="25th percentile salary")
    p75: Optional[int] = Field(None, description="75th percentile salary")
    fjoldi_svara: Optional[int] = Field(None, description="Number of survey responses")
    source_pdf: str
    extracted_at: Optional[str] = None


class SalariesResponse(BaseModel):
    surveys: list[VRSurveyEntry]
    categories: list[str] = Field(description="Available job categories for filtering")
    dates: list[str] = Field(description="Available survey dates for filtering")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "surveys": [
                        {
                            "id": 1,
                            "survey_date": "2024-03",
                            "starfsheiti": "Hugbúnaðarverkfræðingur",
                            "starfsstett": "Tækni og verkfræði",
                            "medaltal": 1150000,
                            "midgildi": 1100000,
                            "p25": 950000,
                            "p75": 1350000,
                            "fjoldi_svara": 245,
                            "source_pdf": "vr_survey_2024_03.pdf",
                            "extracted_at": "2024-12-31T12:00:00",
                        }
                    ],
                    "categories": ["Tækni og verkfræði", "Stjórnun", "Skrifstofa"],
                    "dates": ["2024-03", "2023-09"],
                }
            ]
        }
    }


# --- Financials models ---

class TrendData(BaseModel):
    salary_cagr: Optional[float] = Field(None, description="Compound annual growth rate of average salary")
    revenue_cagr: Optional[float] = Field(None, description="Compound annual growth rate of revenue")


class FinancialsResponse(BaseModel):
    company: CompanyInfo
    reports: list[AnnualReportDetail]
    trends: TrendData

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "company": {
                        "id": 1,
                        "kennitala": "5612903529",
                        "name": "Landsbankinn hf.",
                        "isat_code": "64.19",
                    },
                    "reports": [
                        {
                            "id": 1,
                            "company_id": 1,
                            "year": 2022,
                            "launakostnadur": 26000000000,
                            "starfsmenn": 1020.0,
                            "avg_salary": 25490196,
                            "source_pdf": "landsbankinn_2022.pdf",
                        },
                        {
                            "id": 2,
                            "company_id": 1,
                            "year": 2023,
                            "launakostnadur": 28500000000,
                            "starfsmenn": 1050.0,
                            "avg_salary": 27142857,
                            "source_pdf": "landsbankinn_2023.pdf",
                        },
                    ],
                    "trends": {"salary_cagr": 0.0648, "revenue_cagr": 0.0312},
                }
            ]
        }
    }


# --- Salary comparison models ---

class SalaryComparisonResponse(BaseModel):
    company_avg_salary: int = Field(description="Company average annual salary in ISK")
    report_year: int
    vr_survey_date: Optional[str] = None
    vr_avg: Optional[int] = Field(None, description="VR survey average monthly salary")
    vr_min: Optional[int] = None
    vr_max: Optional[int] = None
    vr_survey_count: Optional[int] = None
    diff_pct: Optional[float] = Field(None, description="Percentage difference from VR average")
    message: Optional[str] = None
    error: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "company_avg_salary": 27142857,
                    "report_year": 2023,
                    "vr_survey_date": "2024-03",
                    "vr_avg": 850000,
                    "vr_min": 420000,
                    "vr_max": 2100000,
                    "vr_survey_count": 156,
                    "diff_pct": 166.2,
                }
            ]
        }
    }


# --- Stats models ---

class PlatformStatsResponse(BaseModel):
    total_companies: int = Field(description="Total number of companies in database")
    total_reports: int = Field(description="Total number of annual reports")
    total_vr_surveys: int = Field(description="Total VR salary survey entries")
    total_scrape_entries: int = Field(description="Total scrape log entries")
    total_sources: int = Field(description="Distinct data sources")
    report_sources: int = Field(description="Distinct PDF sources for reports")
    year_range: tuple[Optional[int], Optional[int]] = Field(description="(min_year, max_year) of available data")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "total_companies": 42,
                    "total_reports": 156,
                    "total_vr_surveys": 312,
                    "total_scrape_entries": 89,
                    "total_sources": 3,
                    "report_sources": 28,
                    "year_range": [2019, 2023],
                }
            ]
        }
    }


# --- Health ---

class HealthResponse(BaseModel):
    status: str

    model_config = {
        "json_schema_extra": {
            "examples": [{"status": "ok"}]
        }
    }
