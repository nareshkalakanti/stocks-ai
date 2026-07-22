"""Cash Quality — CROIC, CCC, cash/tax, OCF vs EBITDA growth from yfinance."""

from __future__ import annotations

import pandas as pd

from stocks.core.config import (
    CASH_QUALITY_LOOKBACK_YEARS,
    CASH_QUALITY_MAX_CCC_YEARS,
    CASH_QUALITY_MIN_CASH_TO_TAX,
    CASH_QUALITY_MIN_CHECKS,
    CASH_QUALITY_MIN_CROIC,
    CASH_QUALITY_MIN_OCF_EBITDA_GROWTH,
)
from stocks.strategies.earnings.strategy import EBIDT_FIELDS
from stocks.strategies.valuation_formula.strategy import (
    CFO_FIELDS,
    EQUITY_FIELDS,
    REVENUE_FIELDS,
    _first_row,
)

CASH_FIELDS = (
    "Cash And Cash Equivalents",
    "Cash Cash Equivalents And Short Term Investments",
    "Cash And Short Term Investments",
    "Cash Financial",
    "Cash",
)

TAX_FIELDS = (
    "Tax Provision",
    "Income Tax Expense",
    "Provision For Income Taxes",
)

CAPEX_FIELDS = (
    "Capital Expenditure",
    "Purchase Of PPE",
    "Net PPE Purchase And Sale",
)

INVESTED_CAPITAL_FIELDS = (
    "Invested Capital",
)

TOTAL_DEBT_FIELDS = (
    "Total Debt",
    "Net Debt",
)

INVENTORY_FIELDS = (
    "Inventory",
    "Inventories",
)

RECEIVABLE_FIELDS = (
    "Accounts Receivable",
    "Receivables",
    "Gross Accounts Receivable",
)

PAYABLE_FIELDS = (
    "Accounts Payable",
    "Payables",
    "Payables And Accrued Expenses",
)

COGS_FIELDS = (
    "Cost Of Revenue",
    "Reconciled Cost Of Revenue",
    "Cost Of Goods Sold",
)

EBITDA_FIELDS = (
    "EBITDA",
    "Normalized EBITDA",
) + EBIDT_FIELDS


def _sorted_desc(series: pd.Series | None) -> pd.Series | None:
    if series is None or series.empty:
        return None
    s = series.dropna().astype(float).sort_index(ascending=False)
    return s if not s.empty else None


def _cagr(series: pd.Series | None, *, years: int) -> float | None:
    s = _sorted_desc(series)
    if s is None or len(s) < years + 1:
        return None
    latest = float(s.iloc[0])
    prior = float(s.iloc[years])
    if latest <= 0 or prior <= 0:
        return None
    return (latest / prior) ** (1 / years) - 1


def _adaptive_cagr(
    series: pd.Series | None,
    *,
    preferred_years: int,
    min_years: int = 2,
) -> float | None:
    """CAGR using preferred span, then shorter spans Yahoo can support."""
    for years in range(preferred_years, min_years - 1, -1):
        val = _cagr(series, years=years)
        if val is not None:
            return val
    return None


def _value_n_years_ago(series: pd.Series | None, *, years: int) -> float | None:
    s = _sorted_desc(series)
    if s is None or len(s) < years + 1:
        return None
    return float(s.iloc[years])


def _oldest_available(
    series: pd.Series | None,
    *,
    preferred_years: int,
    min_years: int = 2,
) -> float | None:
    """Prefer N years back; else farthest available point at least min_years back."""
    s = _sorted_desc(series)
    if s is None or len(s) < min_years + 1:
        return None
    if len(s) >= preferred_years + 1:
        return float(s.iloc[preferred_years])
    return float(s.iloc[-1])


def _latest(series: pd.Series | None) -> float | None:
    s = _sorted_desc(series)
    if s is None:
        return None
    return float(s.iloc[0])


def cash_to_tax_ratio(
    balance_sheet: pd.DataFrame | None,
    financials: pd.DataFrame | None,
    *,
    years: int = CASH_QUALITY_LOOKBACK_YEARS,
) -> float | None:
    """Cash N years back / |Tax provision| (Yahoo often has ~4 annual cols)."""
    cash = _first_row(balance_sheet, CASH_FIELDS)
    tax = _first_row(financials, TAX_FIELDS)
    cash_old = _oldest_available(cash, preferred_years=years, min_years=2)
    if cash_old is None:
        return None
    tax_s = _sorted_desc(tax)
    tax_old = None
    if tax_s is not None:
        # Prefer same lookback index when available.
        if len(tax_s) >= years + 1:
            tax_old = float(tax_s.iloc[years])
        elif len(tax_s) >= 3:
            tax_old = float(tax_s.iloc[-1])
    if tax_old is None or tax_old == 0:
        tax_old = _latest(tax)
    if tax_old is None or tax_old == 0:
        return None
    return round(cash_old / abs(tax_old), 3)


def croic_ratio(
    cashflow: pd.DataFrame | None,
    balance_sheet: pd.DataFrame | None,
) -> float | None:
    """(Operating Cash Flow − |CapEx|) / Invested Capital."""
    ocf = _latest(_first_row(cashflow, CFO_FIELDS))
    if ocf is None:
        return None
    capex_raw = _latest(_first_row(cashflow, CAPEX_FIELDS))
    capex = abs(capex_raw) if capex_raw is not None else 0.0
    fcf = ocf - capex

    invested = _latest(_first_row(balance_sheet, INVESTED_CAPITAL_FIELDS))
    if invested is None or invested <= 0:
        equity = _latest(_first_row(balance_sheet, EQUITY_FIELDS))
        debt = _latest(_first_row(balance_sheet, TOTAL_DEBT_FIELDS)) or 0.0
        cash = _latest(_first_row(balance_sheet, CASH_FIELDS)) or 0.0
        if equity is None:
            return None
        invested = equity + max(debt, 0.0) - max(cash, 0.0)
    if invested is None or invested <= 0:
        return None
    return round(fcf / invested, 3)


def cash_conversion_cycle_years(
    financials: pd.DataFrame | None,
    balance_sheet: pd.DataFrame | None,
) -> tuple[float | None, float | None]:
    """
    CCC in years and days.

    DIO + DSO − DPO, then years = days / 365.
    Pass rule uses CCC years < 1 (under one year of cash tied in WC).
    """
    rev = _latest(_first_row(financials, REVENUE_FIELDS))
    cogs = _latest(_first_row(financials, COGS_FIELDS))
    inv = _latest(_first_row(balance_sheet, INVENTORY_FIELDS))
    ar = _latest(_first_row(balance_sheet, RECEIVABLE_FIELDS))
    ap = _latest(_first_row(balance_sheet, PAYABLE_FIELDS))

    if rev is None or rev <= 0:
        return None, None

    # Services/IT often have no inventory — treat as 0.
    inv_v = inv if inv is not None and inv > 0 else 0.0
    ar_v = ar if ar is not None and ar > 0 else 0.0
    ap_v = ap if ap is not None and ap > 0 else 0.0
    cogs_v = cogs if cogs is not None and cogs > 0 else rev

    dio = (inv_v / cogs_v) * 365 if cogs_v else 0.0
    dso = (ar_v / rev) * 365
    dpo = (ap_v / cogs_v) * 365 if cogs_v else 0.0
    days = dio + dso - dpo
    years = days / 365.0
    return round(years, 3), round(days, 1)


def ocf_vs_ebitda_growth(
    cashflow: pd.DataFrame | None,
    financials: pd.DataFrame | None,
    *,
    years: int = CASH_QUALITY_LOOKBACK_YEARS,
) -> float | None:
    """
    Prefer OCF CAGR / EBITDA CAGR.

    Fallback when Yahoo history is short: multi-year ΣOCF / ΣEBITDA.
    """
    ocf_s = _first_row(cashflow, CFO_FIELDS)
    ebitda_s = _first_row(financials, EBITDA_FIELDS)
    ocf_g = _adaptive_cagr(ocf_s, preferred_years=years, min_years=2)
    ebitda_g = _adaptive_cagr(ebitda_s, preferred_years=years, min_years=2)
    if ocf_g is not None and ebitda_g is not None and ebitda_g > 0:
        return round(ocf_g / ebitda_g, 3)

    # Cumulative conversion fallback (same threshold semantics: > 0.6).
    ocf = _sorted_desc(ocf_s)
    ebitda = _sorted_desc(ebitda_s)
    if ocf is None or ebitda is None:
        return None
    n = min(len(ocf), len(ebitda), years + 1)
    if n < 2:
        return None
    ocf_sum = float(ocf.iloc[:n].sum())
    ebitda_sum = float(ebitda.iloc[:n].sum())
    if ebitda_sum <= 0:
        return None
    return round(ocf_sum / ebitda_sum, 3)


def compute_cash_quality_metrics(
    financials: pd.DataFrame | None,
    balance_sheet: pd.DataFrame | None,
    cashflow: pd.DataFrame | None,
    *,
    years: int = CASH_QUALITY_LOOKBACK_YEARS,
) -> dict:
    ccc_years, ccc_days = cash_conversion_cycle_years(financials, balance_sheet)
    ocf_latest = _latest(_first_row(cashflow, CFO_FIELDS))
    ebitda_latest = _latest(_first_row(financials, EBITDA_FIELDS))
    ocf_to_ebitda = None
    if ocf_latest is not None and ebitda_latest is not None and ebitda_latest != 0:
        ocf_to_ebitda = round(ocf_latest / ebitda_latest, 3)

    ocf_cagr_raw = _adaptive_cagr(_first_row(cashflow, CFO_FIELDS), preferred_years=years)
    ebitda_cagr_raw = _adaptive_cagr(
        _first_row(financials, EBITDA_FIELDS), preferred_years=years
    )

    return {
        "cash_to_tax": cash_to_tax_ratio(balance_sheet, financials, years=years),
        "croic": croic_ratio(cashflow, balance_sheet),
        "ccc_years": ccc_years,
        "ccc_days": ccc_days,
        "ocf_ebitda_growth": ocf_vs_ebitda_growth(cashflow, financials, years=years),
        "ocf_to_ebitda": ocf_to_ebitda,
        "ocf_cagr": (
            round(ocf_cagr_raw * 100, 2) if ocf_cagr_raw is not None else None
        ),
        "ebitda_cagr": (
            round(ebitda_cagr_raw * 100, 2) if ebitda_cagr_raw is not None else None
        ),
        # Contingent liabilities not available on Yahoo — left for manual review.
        "contingent_liab_equity": None,
    }


def _check_pass(label: str, ok: bool, passed: list[str], failed: list[str]) -> None:
    if ok:
        passed.append(label)
    else:
        failed.append(label)


def score_cash_quality(df: pd.DataFrame) -> pd.DataFrame:
    """
    Pass rules (defaults):
    - Cash (N Y back) / Tax > 0.6
    - CROIC > 0.2
    - CCC years < 1
    - OCF CAGR / EBITDA CAGR > 0.6
    Contingent liabilities / equity is not auto-scored (Yahoo gap).
    """
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df

    out = df.copy()
    scores: list[float | None] = []
    check_labels: list[str] = []
    check_pass: list[int] = []
    check_total: list[int] = []

    for _, row in out.iterrows():
        passed: list[str] = []
        failed: list[str] = []

        cash_tax = pd.to_numeric(row.get("cash_to_tax"), errors="coerce")
        _check_pass(
            "Cash/Tax",
            cash_tax is not None
            and not pd.isna(cash_tax)
            and float(cash_tax) > CASH_QUALITY_MIN_CASH_TO_TAX,
            passed,
            failed,
        )

        croic = pd.to_numeric(row.get("croic"), errors="coerce")
        _check_pass(
            "CROIC",
            croic is not None
            and not pd.isna(croic)
            and float(croic) > CASH_QUALITY_MIN_CROIC,
            passed,
            failed,
        )

        ccc = pd.to_numeric(row.get("ccc_years"), errors="coerce")
        _check_pass(
            "CCC",
            ccc is not None
            and not pd.isna(ccc)
            and float(ccc) < CASH_QUALITY_MAX_CCC_YEARS,
            passed,
            failed,
        )

        ocf_g = pd.to_numeric(row.get("ocf_ebitda_growth"), errors="coerce")
        _check_pass(
            "OCF/EBITDA g",
            ocf_g is not None
            and not pd.isna(ocf_g)
            and float(ocf_g) > CASH_QUALITY_MIN_OCF_EBITDA_GROWTH,
            passed,
            failed,
        )

        n_pass = len(passed)
        n_total = n_pass + len(failed)
        check_pass.append(n_pass)
        check_total.append(n_total)
        check_labels.append(f"{n_pass}/{n_total}")

        if n_pass < CASH_QUALITY_MIN_CHECKS or n_total == 0:
            scores.append(None)
        else:
            croic_f = float(croic) if croic is not None and not pd.isna(croic) else 0.0
            scores.append(round(n_pass / n_total * 100 + min(croic_f, 1.0) * 20, 1))

    out["cq_checks"] = check_labels
    out["cq_checks_pass"] = check_pass
    out["cq_checks_total"] = check_total
    out["cq_score"] = scores

    out = out[out["cq_score"].notna()].copy()
    if out.empty:
        return out
    out = out.sort_values(
        ["cq_checks_pass", "cq_score", "croic"],
        ascending=[False, False, False],
        na_position="last",
    ).reset_index(drop=True)
    out.insert(0, "rank", range(1, len(out) + 1))
    return out


def format_cash_quality_export_df(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        ("rank", "rank"),
        ("ticker", "ticker"),
        ("name", "name"),
        ("cq_score", "cq_score"),
        ("cq_checks", "quant_checks"),
        ("cash_to_tax", "cash_to_tax"),
        ("croic", "croic"),
        ("ccc_years", "ccc_years"),
        ("ccc_days", "ccc_days"),
        ("ocf_ebitda_growth", "ocf_ebitda_growth"),
        ("ocf_to_ebitda", "ocf_to_ebitda"),
        ("ocf_cagr", "ocf_cagr"),
        ("ebitda_cagr", "ebitda_cagr"),
        ("website", "website"),
        ("market_cap_cr", "market_cap_cr"),
        ("sector", "sector"),
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=[a for _, a in cols])
    out = pd.DataFrame()
    for src, alias in cols:
        out[alias] = df[src] if src in df.columns else pd.NA
    return out


def cash_quality_caption() -> str:
    y = CASH_QUALITY_LOOKBACK_YEARS
    return (
        f"Cash Quality — **Cash({y}Y)/Tax > {CASH_QUALITY_MIN_CASH_TO_TAX:g}**, "
        f"**CROIC > {CASH_QUALITY_MIN_CROIC:g}**, "
        f"**CCC < {CASH_QUALITY_MAX_CCC_YEARS:g}Y**, "
        f"**OCF CAGR / EBITDA CAGR > {CASH_QUALITY_MIN_OCF_EBITDA_GROWTH:g}** "
        "(uses shorter Yahoo history when 5Y missing; ΣOCF/ΣEBITDA fallback). "
        "Contingent liabilities / equity needs annual-report review (not on Yahoo)."
    )


__all__ = [
    "cash_conversion_cycle_years",
    "cash_quality_caption",
    "cash_to_tax_ratio",
    "compute_cash_quality_metrics",
    "croic_ratio",
    "format_cash_quality_export_df",
    "ocf_vs_ebitda_growth",
    "score_cash_quality",
]
