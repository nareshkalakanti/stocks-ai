"""Small + Cheap — mcap 20–200 Cr, Mcap/Sales < 1, optional debt-free via yfinance."""

from __future__ import annotations

import pandas as pd

from stocks.core.config import (
    SMALL_CHEAP_MAX_DEBT_EQUITY,
    SMALL_CHEAP_MAX_PRICE_TO_SALES,
    SMALL_CHEAP_MCAP_MAX_CR,
    SMALL_CHEAP_MCAP_MIN_CR,
)
from stocks.strategies.inst_entry.strategy import _debt_to_equity
from stocks.strategies.micro_value.strategy import price_to_sales


def in_small_cheap_mcap_band(market_cap_cr: float | None) -> bool:
    if market_cap_cr is None or pd.isna(market_cap_cr):
        return False
    cap = float(market_cap_cr)
    return SMALL_CHEAP_MCAP_MIN_CR <= cap <= SMALL_CHEAP_MCAP_MAX_CR


def is_low_debt(info: dict | None, debt_to_equity: float | None = None) -> bool | None:
    """
    True when Yahoo shows no meaningful debt.

    None = debt data missing (small caps often omit D/E on Yahoo).
    """
    info = info or {}
    debt = info.get("totalDebt")
    if debt is not None and not pd.isna(debt):
        return float(debt) <= 0

    dte = debt_to_equity if debt_to_equity is not None else _debt_to_equity(info)
    if dte is not None and not pd.isna(dte):
        return float(dte) <= SMALL_CHEAP_MAX_DEBT_EQUITY

    return None


def compute_small_cheap_metrics(
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

    debt_to_equity = _debt_to_equity(info)
    pe = info.get("trailingPE")
    pe_f = round(float(pe), 1) if pe is not None and not pd.isna(pe) else None

    sales_growth = None
    rg = info.get("revenueGrowth")
    if rg is not None and not pd.isna(rg):
        sales_growth = round(float(rg) * 100, 2)

    return {
        "price_to_sales": price_to_sales(info, financials, market_cap=mcap),
        "pe_ratio": pe_f,
        "sales_growth": sales_growth,
        "debt_to_equity": debt_to_equity,
        "debt_free": is_low_debt(info, debt_to_equity),
    }


def score_small_cheap(
    df: pd.DataFrame,
    *,
    debt_free_only: bool = True,
) -> pd.DataFrame:
    """Keep small caps with Mcap/Sales < 1; optionally require low/no debt."""
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df

    out = df.copy()
    out["market_cap_cr"] = pd.to_numeric(out.get("market_cap_cr"), errors="coerce")
    out["price_to_sales"] = pd.to_numeric(out.get("price_to_sales"), errors="coerce")

    band = out["market_cap_cr"].map(in_small_cheap_mcap_band)
    cheap = out["price_to_sales"].notna() & (
        out["price_to_sales"] < SMALL_CHEAP_MAX_PRICE_TO_SALES
    )
    mask = band & cheap

    if debt_free_only:
        if "debt_free" not in out.columns:
            out["debt_free"] = out.apply(
                lambda row: is_low_debt(
                    None,
                    pd.to_numeric(row.get("debt_to_equity"), errors="coerce"),
                ),
                axis=1,
            )
        mask = mask & (out["debt_free"].isin([True, None]))

    out = out[mask].copy()
    if out.empty:
        return out

    out = out.sort_values(
        ["price_to_sales", "sales_growth", "market_cap_cr"],
        ascending=[True, False, True],
        na_position="last",
    ).reset_index(drop=True)
    out.insert(0, "rank", range(1, len(out) + 1))

    out["sc_score"] = out["price_to_sales"].map(
        lambda x: round(
            max(
                0.0,
                (SMALL_CHEAP_MAX_PRICE_TO_SALES - float(x))
                / SMALL_CHEAP_MAX_PRICE_TO_SALES
                * 100,
            ),
            1,
        )
        if x is not None and not pd.isna(x)
        else None
    )
    return out


def format_small_cheap_export_df(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        ("rank", "rank"),
        ("ticker", "ticker"),
        ("name", "name"),
        ("sc_score", "sc_score"),
        ("price_to_sales", "mcap_to_sales"),
        ("market_cap_cr", "market_cap_cr"),
        ("pe_ratio", "pe"),
        ("sales_growth", "sales_growth"),
        ("debt_to_equity", "debt_to_equity"),
        ("debt_free", "debt_free"),
        ("website", "website"),
        ("sector", "sector"),
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=[a for _, a in cols])
    out = pd.DataFrame()
    for src, alias in cols:
        out[alias] = df[src] if src in df.columns else pd.NA
    return out


def small_cheap_caption(*, debt_free_only: bool = True) -> str:
    debt_note = (
        f"**debt-free / D/E ≤ {SMALL_CHEAP_MAX_DEBT_EQUITY:g}** (unknown debt kept)"
        if debt_free_only
        else "debt filter off"
    )
    return (
        f"**Small + Cheap** — market cap **{SMALL_CHEAP_MCAP_MIN_CR:g}–"
        f"{SMALL_CHEAP_MCAP_MAX_CR:g} Cr**, **Mcap/Sales < "
        f"{SMALL_CHEAP_MAX_PRICE_TO_SALES:g}**, {debt_note}. "
        "Ranked by lowest P/S."
    )


__all__ = [
    "compute_small_cheap_metrics",
    "format_small_cheap_export_df",
    "in_small_cheap_mcap_band",
    "is_low_debt",
    "score_small_cheap",
    "small_cheap_caption",
]
