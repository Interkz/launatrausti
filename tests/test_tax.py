"""Unit tests for Icelandic tax calculator (2026 rates)."""
from src.tax import calculate_net_salary, TaxBreakdown, PERSONAL_TAX_CREDIT


def test_zero_salary():
    b = calculate_net_salary(0)
    assert b.net == 0
    assert b.total_deductions == 0
    assert b.deduction_rate == 0.0


def test_bracket_1_only():
    """500k gross — stays in bracket 1 after pension."""
    b = calculate_net_salary(500_000)
    assert b.mandatory_pension == 20_000
    assert b.taxable_income == 480_000
    # 480,000 * 0.3149 = 151,152 → minus 72,492 credit = 78,660
    assert b.tax_after_credit == 78_660
    assert b.union_fee == 3_500       # 500k * 0.007
    assert b.net == 397_840


def test_bracket_1_and_2():
    """750k gross — Codex-verified values."""
    b = calculate_net_salary(750_000)
    assert b.mandatory_pension == 30_000
    assert b.taxable_income == 720_000
    # bracket1: 498,122 * 0.3149 = 156,858.62
    # bracket2: 221,878 * 0.3799 = 84,291.45
    # total: 241,150.07 → after credit: 168,658.07 → round to 168,658
    assert b.tax_after_credit == 168_658
    assert b.union_fee == 5_250
    assert b.net == 546_092


def test_all_three_brackets():
    """1.5M gross — Codex-verified values."""
    b = calculate_net_salary(1_500_000)
    assert b.mandatory_pension == 60_000
    assert b.taxable_income == 1_440_000
    assert b.tax_after_credit == 445_635
    assert b.union_fee == 10_500
    assert b.net == 983_865


def test_credit_exceeds_tax():
    """200k gross — personal tax credit exceeds tax owed."""
    b = calculate_net_salary(200_000)
    assert b.mandatory_pension == 8_000
    # taxable 192,000 * 0.3149 = 60,461.28 < 72,492 credit
    assert b.tax_after_credit == 0
    assert b.personal_tax_credit == 60_461  # only the tax amount is credited
    assert b.net == 200_000 - 8_000 - 0 - 1_400  # 190,600


def test_supplemental_pension_reduces_taxable():
    """4% supplemental pension should lower taxable income and thus tax."""
    base = calculate_net_salary(750_000)
    with_supp = calculate_net_salary(750_000, supplemental_pension_pct=0.04)
    assert with_supp.supplemental_pension == 30_000
    assert with_supp.taxable_income == 690_000  # 750k - 30k - 30k
    assert with_supp.tax_after_credit < base.tax_after_credit
    assert with_supp.net > base.net - 30_000  # net drops less than the extra pension


def test_bracket_boundary_exact():
    """Taxable income exactly at bracket 1 limit — no bracket 2 should apply."""
    # We need gross where gross * 0.96 = 498,122
    # gross = 498,122 / 0.96 = 518,877.08 → use 518,877
    b = calculate_net_salary(518_877)
    # taxable = 518,877 * 0.96 = 498,122.08 → rounds to 498,122
    # This is right at the boundary — only ~0.08 kr in bracket 2
    # The tax should be very close to pure bracket 1
    assert b.taxable_income in (498_122, 498_123)


def test_negative_salary():
    b = calculate_net_salary(-100_000)
    assert b.net == 0


def test_custom_union_fee():
    b = calculate_net_salary(750_000, union_fee_pct=0.0085)
    assert b.union_fee == 6_375  # 750k * 0.0085


def test_deduction_rate():
    b = calculate_net_salary(750_000)
    assert 0.25 < b.deduction_rate < 0.30  # ~27.2%


def test_return_type():
    b = calculate_net_salary(750_000)
    assert isinstance(b, TaxBreakdown)
    assert isinstance(b.net, int)
    assert isinstance(b.deduction_rate, float)
