"""Micro Value — mcap 20–200 Cr with Market cap / Sales < 1."""

from __future__ import annotations

import pandas as pd

from stocks.core.config import (
    MICRO_VALUE_MAX_PRICE_TO_SALES,
    MICRO_VALUE_MCAP_MAX_CR,
    MICRO_VALUE_MCAP_MIN_CR,
)
from stocks.strategies.valuation_formula.strategy import REVENUE_FIELDS, _first_row


def price_to_sales(
    info: dict | None,
    financials: pd.DataFrame | None = None,
    *,
    market_cap: float | None = None,
) -> float | None:
    """Market cap / trailing sales (prefer Yahoo priceToSales, else mcap/revenue)."""
    info = info or {}
    pts = info.get("priceToSalesTrailing12Months")
    if pts is not None and not pd.isna(pts) and float(pts) > 0:
        return round(float(pts), 3)

    mcap = market_cap
    if mcap is None:
        raw = info.get("marketCap")
        if raw is not None and not pd.isna(raw):
            mcap = float(raw)
    if mcap is None or mcap <= 0:
        return None

    rev = None
    total_rev = info.get("totalRevenue")
    if total_rev is not None and not pd.isna(total_rev) and float(total_rev) > 0:
        rev = float(total_rev)
    else:
        series = _first_row(financials, REVENUE_FIELDS)
        if series is not None and not series.empty:
            latest = float(series.sort_index(ascending=False).iloc[0])
            if latest > 0:
                rev = latest
    if rev is None or rev <= 0:
        return None
    return round(mcap / rev, 3)


def in_micro_value_mcap_band(market_cap_cr: float | None) -> bool:
    if market_cap_cr is None or pd.isna(market_cap_cr):
        return False
    cap = float(market_cap_cr)
    return MICRO_VALUE_MCAP_MIN_CR <= cap <= MICRO_VALUE_MCAP_MAX_CR


def compute_micro_value_metrics(
    info: dict | None,
    financials: pd.DataFrame | None = None,
    *,
    market_cap_cr: float | None = None,
) -> dict:
    info = info or {}
    mcap_raw = info.get("marketCap")
    mcap = float(mcap_raw) if mcap_raw is not None and not pd.isna(mcap_raw) else None
    if market_cap_cr is not None and not pd.isna(market_cap_cr) and mcap is None:
        mcap = float(market_cap_cr) * 1e7

    pts = price_to_sales(info, financials, market_cap=mcap)
    pe = info.get("trailingPE")
    pe_f = round(float(pe), 1) if pe is not None and not pd.isna(pe) else None

    sales_growth = None
    rg = info.get("revenueGrowth")
    if rg is not None and not pd.isna(rg):
        sales_growth = round(float(rg) * 100, 2)

    dte = info.get("debtToEquity")
    debt_to_equity = None
    if dte is not None and not pd.isna(dte):
        val = float(dte)
        if abs(val) > 10:
            val = val / 100.0
        debt_to_equity = round(val, 2)

    return {
        "price_to_sales": pts,
        "pe_ratio": pe_f,
        "sales_growth": sales_growth,
        "debt_to_equity": debt_to_equity,
    }


def score_micro_value(df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep names in ₹20–200 Cr with Market cap/Sales < 1.
    Rank cheapest P/S first (rerating runway), then higher sales growth.
    """
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df

    out = df.copy()
    out["market_cap_cr"] = pd.to_numeric(out.get("market_cap_cr"), errors="coerce")
    out["price_to_sales"] = pd.to_numeric(out.get("price_to_sales"), errors="coerce")

    band = out["market_cap_cr"].map(in_micro_value_mcap_band)
    cheap = out["price_to_sales"].notna() & (
        out["price_to_sales"] < MICRO_VALUE_MAX_PRICE_TO_SALES
    )
    out = out[band & cheap].copy()
    if out.empty:
        return out

    out = out.sort_values(
        ["price_to_sales", "sales_growth", "market_cap_cr"],
        ascending=[True, False, True],
        na_position="last",
    ).reset_index(drop=True)
    out.insert(0, "rank", range(1, len(out) + 1))

    # Score: cheaper P/S → higher (0–100 scale vs threshold).
    out["mv_score"] = out["price_to_sales"].map(
        lambda x: round(
            max(0.0, (MICRO_VALUE_MAX_PRICE_TO_SALES - float(x)) / MICRO_VALUE_MAX_PRICE_TO_SALES * 100),
            1,
        )
        if x is not None and not pd.isna(x)
        else None
    )
    return out


def format_micro_value_export_df(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        ("rank", "rank"),
        ("ticker", "ticker"),
        ("name", "name"),
        ("mv_score", "mv_score"),
        ("price_to_sales", "mcap_to_sales"),
        ("market_cap_cr", "market_cap_cr"),
        ("pe_ratio", "pe"),
        ("sales_growth", "sales_growth"),
        ("debt_to_equity", "debt_to_equity"),
        ("website", "website"),
        ("sector", "sector"),
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=[a for _, a in cols])
    out = pd.DataFrame()
    for src, alias in cols:
        out[alias] = df[src] if src in df.columns else pd.NA
    return out


def micro_value_caption() -> str:
    return (
        f"**Micro Value** — market cap **{MICRO_VALUE_MCAP_MIN_CR:g}–"
        f"{MICRO_VALUE_MCAP_MAX_CR:g} Cr** and **Mcap/Sales < "
        f"{MICRO_VALUE_MAX_PRICE_TO_SALES:g}** (cheap sales multiple = "
        "rerating runway while still small). Ranked by lowest P/S."
    )


__all__ = [
    "compute_micro_value_metrics",
    "format_micro_value_export_df",
    "in_micro_value_mcap_band",
    "micro_value_caption",
    "price_to_sales",
    "score_micro_value",
]
