"""
Icelandic take-home salary calculator (staðgreiðsla 2026).

Source: skatturinn.is/english/individuals/tax-brackets/2026/
Rates verified 2026-04-05. Must be re-verified annually.
"""
from dataclasses import dataclass

# --- 2026 withholding rates (tekjuskattur + útsvar combined) ---
TAX_YEAR = 2026

BRACKET_1_LIMIT = 498_122      # monthly ISK
BRACKET_2_LIMIT = 1_398_450    # monthly ISK

BRACKET_1_RATE = 0.3149        # 0 – 498,122
BRACKET_2_RATE = 0.3799        # 498,123 – 1,398,450
BRACKET_3_RATE = 0.4629        # above 1,398,450

PERSONAL_TAX_CREDIT = 72_492   # monthly ISK

MANDATORY_PENSION_PCT = 0.04   # 4% employee contribution, pre-tax


@dataclass
class TaxBreakdown:
    gross: int
    mandatory_pension: int
    supplemental_pension: int
    taxable_income: int
    tax_before_credit: int
    personal_tax_credit: int
    tax_after_credit: int
    union_fee: int
    total_deductions: int
    net: int
    deduction_rate: float       # total_deductions / gross


def _progressive_tax(taxable: float) -> float:
    """Calculate progressive income tax before personal tax credit."""
    if taxable <= 0:
        return 0.0
    tax = 0.0
    if taxable <= BRACKET_1_LIMIT:
        tax = taxable * BRACKET_1_RATE
    elif taxable <= BRACKET_2_LIMIT:
        tax = BRACKET_1_LIMIT * BRACKET_1_RATE
        tax += (taxable - BRACKET_1_LIMIT) * BRACKET_2_RATE
    else:
        tax = BRACKET_1_LIMIT * BRACKET_1_RATE
        tax += (BRACKET_2_LIMIT - BRACKET_1_LIMIT) * BRACKET_2_RATE
        tax += (taxable - BRACKET_2_LIMIT) * BRACKET_3_RATE
    return tax


def calculate_net_salary(
    gross_monthly: int,
    supplemental_pension_pct: float = 0.0,
    union_fee_pct: float = 0.007,
) -> TaxBreakdown:
    """
    Calculate monthly take-home pay.

    Args:
        gross_monthly: Gross salary in ISK/month.
        supplemental_pension_pct: Voluntary pension as decimal (0.0–0.04).
        union_fee_pct: Union fee as decimal (e.g. 0.007 for 0.70%).

    Returns:
        TaxBreakdown with all components rounded to nearest króna.
    """
    if gross_monthly <= 0:
        return TaxBreakdown(
            gross=0, mandatory_pension=0, supplemental_pension=0,
            taxable_income=0, tax_before_credit=0,
            personal_tax_credit=0, tax_after_credit=0,
            union_fee=0, total_deductions=0, net=0, deduction_rate=0.0,
        )

    gross = gross_monthly
    mandatory_pension = gross * MANDATORY_PENSION_PCT
    supplemental_pension = gross * supplemental_pension_pct
    taxable = gross - mandatory_pension - supplemental_pension

    tax_before = _progressive_tax(taxable)
    credit_used = min(PERSONAL_TAX_CREDIT, tax_before)
    tax_after = max(0.0, tax_before - PERSONAL_TAX_CREDIT)

    union_fee = gross * union_fee_pct

    total_deductions = mandatory_pension + supplemental_pension + tax_after + union_fee
    net = gross - total_deductions

    return TaxBreakdown(
        gross=round(gross),
        mandatory_pension=round(mandatory_pension),
        supplemental_pension=round(supplemental_pension),
        taxable_income=round(taxable),
        tax_before_credit=round(tax_before),
        personal_tax_credit=round(credit_used),
        tax_after_credit=round(tax_after),
        union_fee=round(union_fee),
        total_deductions=round(total_deductions),
        net=round(net),
        deduction_rate=round(total_deductions / gross, 4),
    )
