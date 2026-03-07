"""
Pydantic response models for the Launatrausti API.

Provides typed, documented response schemas with example values
for all JSON API endpoints. Used by FastAPI to generate OpenAPI docs.
"""

from typing import Optional
from pydantic import BaseModel, Field


# --- Shared / Reusable Models ---

class ErrorDetail(BaseModel):
    """Standard error response body."""
    detail: str = Field(..., description="Human-readable error message")

    model_config = {
        "json_schema_extra": {
            "examples": [{"detail": "Company not found"}]
        }
    }


# --- Company Models ---

class CompanyRanking(BaseModel):
    """A company entry in the salary rankings list."""
    id: int = Field(..., description="Internal company ID", examples=[1])
    kennitala: str = Field(..., description="Icelandic national ID (kennitala) of the company", examples=["4602070880"])
    name: str = Field(..., description="Company name", examples=["Landsbankinn hf."])
    isat_code: Optional[str] = Field(None, description="ISAT industry classification code", examples=["64.19"])
    year: int = Field(..., description="Report year", examples=[2023])
    launakostnadur: int = Field(..., description="Total annual wage costs in ISK", examples=[42_000_000_000])
    starfsmenn: float = Field(..., description="Average number of employees during the year", examples=[1050.0])
    avg_salary: int = Field(..., description="Calculated average annual salary per employee in ISK", examples=[40_000_000])
    tekjur: Optional[int] = Field(None, description="Total revenue in ISK", examples=[95_000_000_000])


class CompanyRankingsResponse(BaseModel):
    """Response for the company rankings endpoint."""
    companies: list[CompanyRanking] = Field(..., description="List of companies ranked by average salary (descending)")
    year: Optional[int] = Field(None, description="Filter year, or null for latest available year per company")

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "companies": [{
                    "id": 1,
                    "kennitala": "4602070880",
                    "name": "Landsbankinn hf.",
                    "isat_code": "64.19",
                    "year": 2023,
                    "launakostnadur": 42_000_000_000,
                    "starfsmenn": 1050.0,
                    "avg_salary": 40_000_000,
                    "tekjur": 95_000_000_000,
                }],
                "year": 2023,
            }]
        }
    }


# --- Company Detail Models ---

class CompanyInfo(BaseModel):
    """Core company metadata."""
    id: int = Field(..., description="Internal company ID", examples=[1])
    kennitala: str = Field(..., description="Icelandic national ID (kennitala)", examples=["4602070880"])
    name: str = Field(..., description="Company name", examples=["Landsbankinn hf."])
    isat_code: Optional[str] = Field(None, description="ISAT industry classification code", examples=["64.19"])
    address: Optional[str] = Field(None, description="Registered address", examples=["Austurstræti 11, 155 Reykjavík"])
    legal_form: Optional[str] = Field(None, description="Legal form of the company", examples=["hf."])
    sector: Optional[str] = Field(None, description="Business sector", examples=["Finance"])
    employee_count_latest: Optional[int] = Field(None, description="Most recent known employee count", examples=[1050])
    updated_at: Optional[str] = Field(None, description="Last metadata update timestamp")


class AnnualReportDetail(BaseModel):
    """A single annual report for a company."""
    id: int = Field(..., description="Report ID", examples=[1])
    company_id: int = Field(..., description="FK to company", examples=[1])
    year: int = Field(..., description="Report year", examples=[2023])
    launakostnadur: int = Field(..., description="Total annual wage costs in ISK", examples=[42_000_000_000])
    starfsmenn: float = Field(..., description="Average employee count", examples=[1050.0])
    tekjur: Optional[int] = Field(None, description="Revenue in ISK", examples=[95_000_000_000])
    avg_salary: int = Field(..., description="Calculated average annual salary in ISK", examples=[40_000_000])
    source_pdf: str = Field(..., description="Source PDF filename or identifier", examples=["landsbankinn_2023.pdf"])
    extracted_at: str = Field(..., description="When the data was extracted", examples=["2024-06-15T10:30:00"])
    hagnadur: Optional[int] = Field(None, description="Net profit in ISK", examples=[15_000_000_000])
    rekstrarkostnadur: Optional[int] = Field(None, description="Operating costs in ISK", examples=[80_000_000_000])
    eiginfjarhlufall: Optional[float] = Field(None, description="Equity ratio (0-1)", examples=[0.12])
    laun_hlutfall_tekna: Optional[float] = Field(None, description="Wage costs as fraction of revenue", examples=[0.44])
    source_type: Optional[str] = Field(None, description="How the data was obtained", examples=["pdf"])
    confidence: Optional[float] = Field(None, description="Extraction confidence score (0-1)", examples=[0.95])
    is_sample: Optional[bool] = Field(None, description="Whether this is sample/test data", examples=[False])


class CompanyDetailResponse(BaseModel):
    """Full company profile with all annual reports."""
    company: CompanyInfo
    reports: list[AnnualReportDetail] = Field(..., description="Annual reports ordered by year descending")


# --- Benchmarks Models ---

class NationalAverage(BaseModel):
    """National average wage figures."""
    monthly: Optional[int] = Field(None, description="National average monthly wage in ISK", examples=[935_000])
    annual: Optional[int] = Field(None, description="National average annual wage in ISK", examples=[11_220_000])


class IndustryBenchmark(BaseModel):
    """Wage benchmark for a single industry."""
    code: str = Field(..., description="Hagstofa industry letter code", examples=["J"])
    name: str = Field(..., description="Industry name in Icelandic", examples=["Upplýsingar og fjarskipti"])
    name_en: str = Field(..., description="Industry name in English", examples=["Information & communication"])
    monthly_wage: int = Field(..., description="Average monthly wage in ISK", examples=[1_009_000])
    annual_wage: int = Field(..., description="Average annual wage in ISK (monthly x 12)", examples=[12_108_000])


class BenchmarksResponse(BaseModel):
    """Industry wage benchmarks from Hagstofa Íslands (Statistics Iceland)."""
    year: int = Field(..., description="Benchmark year", examples=[2023])
    national_average: Optional[NationalAverage] = Field(None, description="National average wages across all industries")
    industries: list[IndustryBenchmark] = Field(..., description="Per-industry wage benchmarks sorted by wage descending")
    source: str = Field(
        default="Hagstofa Íslands (Statistics Iceland)",
        description="Data source attribution",
    )


# --- Salaries (VR Survey) Models ---

class VRSurveyEntry(BaseModel):
    """A single entry from the VR union salary survey."""
    id: int = Field(..., description="Survey entry ID", examples=[1])
    survey_date: str = Field(..., description="Survey date identifier", examples=["2024-01"])
    starfsheiti: str = Field(..., description="Job title in Icelandic", examples=["Hugbúnaðarverkfræðingur"])
    starfsstett: Optional[str] = Field(None, description="Job category / occupation class", examples=["Tæknistarfsmenn"])
    medaltal: int = Field(..., description="Mean monthly salary in ISK", examples=[1_050_000])
    midgildi: Optional[int] = Field(None, description="Median monthly salary in ISK", examples=[980_000])
    p25: Optional[int] = Field(None, description="25th percentile monthly salary in ISK", examples=[850_000])
    p75: Optional[int] = Field(None, description="75th percentile monthly salary in ISK", examples=[1_200_000])
    fjoldi_svara: Optional[int] = Field(None, description="Number of survey responses", examples=[142])
    source_pdf: str = Field(..., description="Source PDF filename", examples=["vr_launarannsokn_2024.pdf"])
    extracted_at: str = Field(..., description="Extraction timestamp", examples=["2024-06-15T10:30:00"])


class SalariesResponse(BaseModel):
    """VR union salary survey data with available filters."""
    surveys: list[VRSurveyEntry] = Field(..., description="Survey entries, ordered by date desc then salary desc")
    categories: list[str] = Field(..., description="Available job categories for filtering", examples=[["Tæknistarfsmenn", "Skrifstofufólk"]])
    dates: list[str] = Field(..., description="Available survey dates for filtering", examples=[["2024-01", "2023-01"]])


# --- Financials Models ---

class FinancialTrends(BaseModel):
    """Computed financial trends across multiple annual reports."""
    salary_cagr: Optional[float] = Field(None, description="Compound annual growth rate of avg salary", examples=[0.054])
    revenue_cagr: Optional[float] = Field(None, description="Compound annual growth rate of revenue", examples=[0.082])


class CompanyFinancialsResponse(BaseModel):
    """Full financial profile with all reports and computed trends."""
    company: CompanyInfo
    reports: list[AnnualReportDetail] = Field(..., description="Annual reports ordered by year ascending")
    trends: FinancialTrends = Field(..., description="Computed trend metrics across report years")


# --- Salary Comparison Models ---

class SalaryComparisonResponse(BaseModel):
    """Comparison of a company's average salary against VR survey benchmarks."""
    company_avg_salary: Optional[int] = Field(None, description="Company's average annual salary in ISK", examples=[40_000_000])
    report_year: Optional[int] = Field(None, description="Year of the company's annual report", examples=[2023])
    vr_survey_date: Optional[str] = Field(None, description="Date of the VR survey used for comparison", examples=["2024-01"])
    vr_avg: Optional[int] = Field(None, description="VR survey average monthly salary in ISK", examples=[935_000])
    vr_min: Optional[int] = Field(None, description="Lowest salary in VR survey", examples=[450_000])
    vr_max: Optional[int] = Field(None, description="Highest salary in VR survey", examples=[2_100_000])
    vr_survey_count: Optional[int] = Field(None, description="Number of job titles in the VR survey", examples=[85])
    diff_pct: Optional[float] = Field(None, description="Percentage difference from VR average (positive = above)", examples=[12.5])
    error: Optional[str] = Field(None, description="Error message if comparison could not be computed")
    message: Optional[str] = Field(None, description="Informational message (e.g. no VR data available)")
    vr_data: Optional[dict] = Field(None, description="Raw VR data when available (null when no data)")


# --- Platform Stats Models ---

class PlatformStatsResponse(BaseModel):
    """Aggregate statistics about the Launatrausti platform."""
    total_companies: int = Field(..., description="Total number of companies in the database", examples=[127])
    total_reports: int = Field(..., description="Total number of annual reports", examples=[312])
    total_vr_surveys: int = Field(..., description="Total VR salary survey entries", examples=[85])
    total_scrape_entries: int = Field(..., description="Total entries in the scrape log", examples=[450])
    total_sources: int = Field(..., description="Number of distinct scrape sources", examples=[3])
    report_sources: int = Field(..., description="Number of distinct report sources (PDFs)", examples=[45])
    year_range: tuple[Optional[int], Optional[int]] = Field(
        ...,
        description="Earliest and latest report years as [min, max]",
        examples=[(2019, 2023)],
    )


# --- Health Check ---

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(..., description="Service status", examples=["ok"])
