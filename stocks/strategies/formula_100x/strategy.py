"""100X Formula — rising CFO, CFO/EBIT, EBT/capital, CFO/market cap."""

from __future__ import annotations

import pandas as pd

from stocks.core.config import (
    FORMULA_100X_CFO_EBIT_MIN,
    FORMULA_100X_CFO_MCAP_MIN,
    FORMULA_100X_EBT_CAPITAL_MIN,
    FORMULA_100X_LOOKBACK_YEARS,
)

CFO_FIELDS = (
    "Operating Cash Flow",
    "Cash From Operating Activities",
    "Total Cash From Operating Activities",
    "Operating Activities Cash Flow",
    "Cash Flow From Operating Activities",
    "Cash Flow From Continuing Operating Activities",
)

EBIT_FIELDS = (
    "EBIT",
    "Earnings Before Interest and Taxes",
    "Operating Income",
    "Operating Income Or Loss",
)

EBT_FIELDS = (
    "Income Before Tax",
    "Earnings Before Tax",
    "EBT",
    "Pretax Income",
    "Income Before Tax Including Extra Items",
)

TOTAL_ASSETS_FIELDS = ("Total Assets", "TotalAssets")
CURRENT_LIAB_FIELDS = (
    "Current Liabilities",
    "Total Current Liabilities",
)
EQUITY_FIELDS = (
    "Stockholders Equity",
    "Total Stockholder Equity",
    "Total Stockholders Equity",
    "Shareholders Equity",
    "Common Stock Equity",
)
LT_DEBT_FIELDS = (
    "Long Term Debt",
    "Long Term Debt And Capital Lease Obligation",
)


def _first_row(df: pd.DataFrame | None, fields: tuple[str, ...]) -> pd.Series | None:
    if df is None or df.empty:
        return None
    for field in fields:
        if field in df.index:
            series = df.loc[field, :].dropna().astype(float)
            if not series.empty:
                return series.sort_index()
    return None


def _annual_series(df: pd.DataFrame | None, fields: tuple[str, ...]) -> pd.Series | None:
    row = _first_row(df, fields)
    if row is None or row.empty:
        return None
    return row.sort_index().tail(FORMULA_100X_LOOKBACK_YEARS)


def _to_inr_cr(value: float | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    v = float(value)
    if abs(v) >= 1e5:
        return round(v / 1e7, 2)
    return round(v, 2)


def _capital_employed(balance_sheet: pd.DataFrame | None) -> float | None:
    if balance_sheet is None or balance_sheet.empty:
        return None
    cols = sorted(balance_sheet.columns, reverse=True)
    if not cols:
        return None
    col = cols[0]
    assets = None
    for field in TOTAL_ASSETS_FIELDS:
        if field in balance_sheet.index:
            raw = balance_sheet.loc[field, col]
            if raw is not None and not pd.isna(raw):
                assets = float(raw)
                break
    cl = None
    for field in CURRENT_LIAB_FIELDS:
        if field in balance_sheet.index:
            raw = balance_sheet.loc[field, col]
            if raw is not None and not pd.isna(raw):
                cl = float(raw)
                break
    if assets is not None and cl is not None:
        ce = assets - cl
        if ce > 0:
            return ce
    equity = None
    for field in EQUITY_FIELDS:
        if field in balance_sheet.index:
            raw = balance_sheet.loc[field, col]
            if raw is not None and not pd.isna(raw):
                equity = float(raw)
                break
    debt = 0.0
    for field in LT_DEBT_FIELDS:
        if field in balance_sheet.index:
            raw = balance_sheet.loc[field, col]
            if raw is not None and not pd.isna(raw):
                debt = float(raw)
                break
    if equity is not None and equity + debt > 0:
        return equity + debt
    return None


def _rising_cfo(cfo: pd.Series | None) -> bool:
    if cfo is None or len(cfo) < 2:
        return False
    vals = cfo.sort_index().astype(float).tolist()
    return all(vals[i] > vals[i - 1] for i in range(1, len(vals)))


def compute_100x_cfo_checks(
    cashflow: pd.DataFrame | None,
    financials: pd.DataFrame | None,
) -> dict | None:
    """Annual rising-CFO and CFO/EBIT gates (display-only; shared with PEAD)."""
    cfo_s = _annual_series(cashflow, CFO_FIELDS)
    ebit_s = _annual_series(financials, EBIT_FIELDS)
    if cfo_s is None or ebit_s is None or ebit_s.empty:
        return None

    pass_rising = _rising_cfo(cfo_s)
    latest_cfo = float(cfo_s.iloc[-1])
    latest_ebit = float(ebit_s.iloc[-1])
    if latest_ebit == 0:
        return {
            "pass_rising_cfo": pass_rising,
            "pass_cfo_ebit": False,
            "cfo_ebit_pct": None,
        }

    cfo_ebit_pct = round((latest_cfo / latest_ebit) * 100, 1)
    return {
        "pass_rising_cfo": pass_rising,
        "pass_cfo_ebit": cfo_ebit_pct > FORMULA_100X_CFO_EBIT_MIN,
        "cfo_ebit_pct": cfo_ebit_pct,
    }


def evaluate_100x_formula(
    *,
    cashflow: pd.DataFrame | None,
    financials: pd.DataFrame | None,
    balance_sheet: pd.DataFrame | None,
    info: dict | None,
    market_cap_cr: float | None,
) -> dict | None:
    """
    Score 0–4 on 100X criteria. Returns metric dict or None if insufficient data.
    """
    info = info or {}
    cfo_s = _annual_series(cashflow, CFO_FIELDS)
    ebit_s = _annual_series(financials, EBIT_FIELDS)
    ebt_s = _annual_series(financials, EBT_FIELDS)
    if cfo_s is None or ebit_s is None or ebt_s is None:
        return None

    cfo_checks = compute_100x_cfo_checks(cashflow, financials)
    if cfo_checks is None:
        return None

    latest_cfo = float(cfo_s.iloc[-1])
    latest_ebit = float(ebit_s.iloc[-1])
    latest_ebt = float(ebt_s.iloc[-1])
    if latest_ebit == 0:
        return None

    cfo_ebit_pct = cfo_checks["cfo_ebit_pct"]
    ce = _capital_employed(balance_sheet)
    ebt_capital_pct = round((latest_ebt / ce) * 100, 1) if ce and ce > 0 else None

    mcap = market_cap_cr
    if mcap is None:
        raw_mcap = info.get("marketCap")
        if raw_mcap is not None and not pd.isna(raw_mcap):
            mcap = round(float(raw_mcap) / 1e7, 1)
    cfo_mcap_pct = None
    if mcap and mcap > 0:
        cfo_mcap_pct = round((latest_cfo / 1e7 / mcap) * 100, 1)

    pass_rising = cfo_checks["pass_rising_cfo"]
    pass_cfo_ebit = cfo_checks["pass_cfo_ebit"]
    pass_ebt_ce = (
        ebt_capital_pct is not None and ebt_capital_pct > FORMULA_100X_EBT_CAPITAL_MIN
    )
    pass_cfo_mcap = cfo_mcap_pct is not None and cfo_mcap_pct > FORMULA_100X_CFO_MCAP_MIN

    flags = [pass_rising, pass_cfo_ebit, pass_ebt_ce, pass_cfo_mcap]
    criteria_score = sum(1 for f in flags if f)

    price_raw = info.get("regularMarketPrice") or info.get("currentPrice")
    price = round(float(price_raw), 2) if price_raw is not None and not pd.isna(price_raw) else None

    return {
        "criteria_score": criteria_score,
        "pass_rising_cfo": pass_rising,
        "pass_cfo_ebit": pass_cfo_ebit,
        "pass_ebt_capital": pass_ebt_ce,
        "pass_cfo_mcap": pass_cfo_mcap,
        "cfo_ebit_pct": cfo_ebit_pct,
        "ebt_capital_pct": ebt_capital_pct,
        "cfo_mcap_pct": cfo_mcap_pct,
        "cfo_latest_cr": _to_inr_cr(latest_cfo),
        "ebit_latest_cr": _to_inr_cr(latest_ebit),
        "market_cap_cr": mcap,
        "price": price,
        "formula_pass": criteria_score == 4,
    }
