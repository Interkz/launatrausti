"""
Pydantic validation models for all API endpoints.

Provides input validation with:
- Whitespace stripping on all string inputs
- Max length constraints on strings
- Min/max bounds on numeric inputs
- Icelandic error messages
"""

from typing import Annotated, Optional

from fastapi import Path, Query
from pydantic import BaseModel, field_validator

# -- Icelandic error message templates --
IS_YEAR_RANGE = "Ár verður að vera á milli 1900 og 2100"
IS_LIMIT_RANGE = "Hámark verður að vera á milli 1 og 1000"
IS_ID_POSITIVE = "Auðkenni verður að vera jákvæð tala"
IS_STRING_TOO_LONG = "Texti má ekki vera lengri en {max_length} stafir"

# -- Icelandic messages mapped by field name --
FIELD_MESSAGES_IS = {
    "year": IS_YEAR_RANGE,
    "limit": IS_LIMIT_RANGE,
    "company_id": IS_ID_POSITIVE,
    "sector": IS_STRING_TOO_LONG.format(max_length=500),
    "category": IS_STRING_TOO_LONG.format(max_length=500),
    "survey_date": IS_STRING_TOO_LONG.format(max_length=20),
}


def _strip(v: Optional[str]) -> Optional[str]:
    if v is not None:
        v = v.strip()
        if v == "":
            return None
    return v


# -- Annotated types for reuse across endpoints --

YearParam = Annotated[
    Optional[int],
    Query(ge=1900, le=2100, description="Ár (1900–2100)"),
]

YearParamRequired = Annotated[
    int,
    Query(ge=1900, le=2100, description="Ár (1900–2100)"),
]

LimitParam = Annotated[
    int,
    Query(ge=1, le=1000, description="Hámarksfjöldi niðurstaðna (1–1000)"),
]

SectorParam = Annotated[
    Optional[str],
    Query(max_length=500, description="Atvinnugrein"),
]

CategoryParam = Annotated[
    Optional[str],
    Query(max_length=500, description="Flokkur"),
]

SurveyDateParam = Annotated[
    Optional[str],
    Query(max_length=20, description="Dagsetning könnunar"),
]

CompanyIdPath = Annotated[
    int,
    Path(ge=1, description="Auðkenni fyrirtækis"),
]


class StrippingMixin:
    """Strips whitespace from all string fields."""

    @field_validator("*", mode="before")
    @classmethod
    def strip_strings(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if v == "":
                return None
        return v


class IndexParams(StrippingMixin, BaseModel):
    year: YearParam = None
    sector: SectorParam = None


class BenchmarksParams(BaseModel):
    year: YearParamRequired = 2023


class SalariesParams(StrippingMixin, BaseModel):
    category: CategoryParam = None
    survey_date: SurveyDateParam = None


class CompaniesApiParams(StrippingMixin, BaseModel):
    year: YearParam = None
    limit: LimitParam = 100
