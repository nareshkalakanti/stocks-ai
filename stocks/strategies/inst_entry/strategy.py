"""Inst Entry — micro deep value + DII/FII institutional entry trigger."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from stocks.core.config import (
    INST_ENTRY_MAX_DEBT_EQUITY,
    INST_ENTRY_MAX_PRICE_TO_SALES,
    INST_ENTRY_MCAP_MAX_CR,
    INST_ENTRY_MCAP_MIN_CR,
    INST_ENTRY_MIN_AVG_VOLUME,
    INST_ENTRY_MIN_DII_FII_DELTA,
    INST_ENTRY_MIN_LISTED_YEARS,
    INST_ENTRY_MIN_SALES_CAGR,
    INST_ENTRY_REQUIRE_SIGNAL,
)
from stocks.strategies.earnings.strategy import NET_INCOME_FIELDS
from stocks.strategies.micro_value.strategy import price_to_sales
from stocks.strategies.valuation_formula.strategy import REVENUE_FIELDS, _first_row


def _debt_to_equity(info: dict | None) -> float | None:
    info = info or {}
    dte = info.get("debtToEquity")
    if dte is not None and not pd.isna(dte):
        val = float(dte)
        if abs(val) > 10:
            val = val / 100.0
        return round(val, 3)
    # Yahoo often omits D/E; treat zero / missing debt as 0.
    debt = info.get("totalDebt")
    if debt is not None and not pd.isna(debt) and float(debt) <= 0:
        return 0.0
    return None


def _sales_cagr_pct(
    financials: pd.DataFrame | None,
    *,
    preferred_years: int = 5,
) -> float | None:
    rev = _first_row(financials, REVENUE_FIELDS)
    if rev is None or rev.empty:
        return None
    s = rev.dropna().astype(float).sort_index(ascending=False)
    for years in range(preferred_years, 2, -1):
        if len(s) < years + 1:
            continue
        latest = float(s.iloc[0])
        prior = float(s.iloc[years])
        if latest <= 0 or prior <= 0:
            continue
        return round(((latest / prior) ** (1 / years) - 1) * 100, 2)
    return None


def _ttm_profit_positive(
    info: dict | None,
    financials: pd.DataFrame | None,
) -> bool | None:
    info = info or {}
    ni = info.get("netIncomeToCommon")
    if ni is not None and not pd.isna(ni):
        return float(ni) > 0
    series = _first_row(financials, NET_INCOME_FIELDS)
    if series is None or series.empty:
        return None
    latest = float(series.sort_index(ascending=False).iloc[0])
    return latest > 0


def _avg_volume(info: dict | None) -> float | None:
    info = info or {}
    for key in ("averageVolume", "averageDailyVolume10Day", "averageVolume10days"):
        val = info.get(key)
        if val is not None and not pd.isna(val):
            return float(val)
    return None


def _years_listed(info: dict | None) -> float | None:
    info = info or {}
    epoch = info.get("firstTradeDateEpochUtc") or info.get("firstTradeDateEpoch")
    if epoch is None or pd.isna(epoch):
        return None
    try:
        start = datetime.fromtimestamp(float(epoch), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
    days = (datetime.now(timezone.utc) - start).days
    return round(days / 365.25, 2)


def in_inst_entry_mcap_band(market_cap_cr: float | None) -> bool:
    if market_cap_cr is None or pd.isna(market_cap_cr):
        return False
    cap = float(market_cap_cr)
    return INST_ENTRY_MCAP_MIN_CR <= cap <= INST_ENTRY_MCAP_MAX_CR


def compute_inst_entry_metrics(
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

    return {
        "price_to_sales": price_to_sales(info, financials, market_cap=mcap),
        "debt_to_equity": _debt_to_equity(info),
        "sales_cagr": _sales_cagr_pct(financials),
        "profit_positive": _ttm_profit_positive(info, financials),
        "avg_volume": _avg_volume(info),
        "years_listed": _years_listed(info),
    }


def passes_quant_gates(row: pd.Series | dict) -> tuple[bool, list[str], list[str]]:
    """Binary value/quality gates from the script. Returns (ok, passed, failed)."""
    passed: list[str] = []
    failed: list[str] = []

    def _check(label: str, ok: bool) -> None:
        if ok:
            passed.append(label)
        else:
            failed.append(label)

    mcap = pd.to_numeric(
        row.get("market_cap_cr") if hasattr(row, "get") else None, errors="coerce"
    )
    _check("Mcap band", in_inst_entry_mcap_band(mcap))

    pts = pd.to_numeric(row.get("price_to_sales"), errors="coerce")
    _check(
        "P/S",
        pts is not None
        and not pd.isna(pts)
        and float(pts) < INST_ENTRY_MAX_PRICE_TO_SALES,
    )

    de = pd.to_numeric(row.get("debt_to_equity"), errors="coerce")
    # Missing D/E: pass (Yahoo gaps); present D/E must be ≤ max.
    _check(
        "D/E",
        de is None
        or pd.isna(de)
        or float(de) <= INST_ENTRY_MAX_DEBT_EQUITY,
    )

    cagr = pd.to_numeric(row.get("sales_cagr"), errors="coerce")
    _check(
        "Sales CAGR",
        cagr is not None
        and not pd.isna(cagr)
        and float(cagr) >= INST_ENTRY_MIN_SALES_CAGR,
    )

    profit_ok = row.get("profit_positive")
    _check("Profit+", profit_ok is True)

    vol = pd.to_numeric(row.get("avg_volume"), errors="coerce")
    _check(
        "Volume",
        vol is not None
        and not pd.isna(vol)
        and float(vol) >= INST_ENTRY_MIN_AVG_VOLUME,
    )

    years = pd.to_numeric(row.get("years_listed"), errors="coerce")
    # Yahoo rarely sends firstTradeDate for NSE — skip when unknown.
    _check(
        "Listed",
        years is None
        or pd.isna(years)
        or float(years) >= INST_ENTRY_MIN_LISTED_YEARS,
    )

    return len(failed) == 0, passed, failed


def score_inst_entry(
    df: pd.DataFrame,
    *,
    require_signal: bool | None = None,
) -> pd.DataFrame:
    """
    Gate on quant filters; trigger = institutional_pct_delta.

    Rank by inst delta (then first-time), not a blended fundamentals score.
    """
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df

    require = INST_ENTRY_REQUIRE_SIGNAL if require_signal is None else require_signal
    out = df.copy()
    keep_mask: list[bool] = []
    gate_labels: list[str] = []
    for _, row in out.iterrows():
        ok, passed, failed = passes_quant_gates(row)
        gate_labels.append(f"{len(passed)}/{len(passed) + len(failed)}")
        has_signal = False
        delta = pd.to_numeric(row.get("institutional_pct_delta"), errors="coerce")
        if delta is not None and not pd.isna(delta):
            has_signal = float(delta) >= INST_ENTRY_MIN_DII_FII_DELTA
        if require:
            keep_mask.append(ok and has_signal)
        else:
            keep_mask.append(ok)

    out["ie_gates"] = gate_labels
    out = out[keep_mask].copy()
    if out.empty:
        return out

    if "first_time_entry" not in out.columns:
        out["first_time_entry"] = False
    out["institutional_pct_delta"] = pd.to_numeric(
        out.get("institutional_pct_delta"), errors="coerce"
    )
    out = out.sort_values(
        ["first_time_entry", "institutional_pct_delta", "price_to_sales"],
        ascending=[False, False, True],
        na_position="last",
    ).reset_index(drop=True)
    out.insert(0, "rank", range(1, len(out) + 1))
    return out


def format_inst_entry_export_df(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        ("rank", "rank"),
        ("ticker", "ticker"),
        ("name", "name"),
        ("first_time_entry", "first_time_entry"),
        ("institutional_pct_delta", "inst_delta_pp"),
        ("institutional_pct_now", "inst_pct_now"),
        ("quarter_end", "quarter_end"),
        ("market_cap_cr", "market_cap_cr"),
        ("price_to_sales", "mcap_to_sales"),
        ("debt_to_equity", "debt_to_equity"),
        ("sales_cagr", "sales_cagr"),
        ("avg_volume", "avg_volume"),
        ("years_listed", "years_listed"),
        ("ie_gates", "quant_gates"),
        ("sector", "sector"),
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=[a for _, a in cols])
    out = pd.DataFrame()
    for src, alias in cols:
        out[alias] = df[src] if src in df.columns else pd.NA
    return out


def inst_entry_caption() -> str:
    return (
        f"**Inst Entry** — ₹{INST_ENTRY_MCAP_MIN_CR:g}–{INST_ENTRY_MCAP_MAX_CR:g} Cr, "
        f"**P/S < {INST_ENTRY_MAX_PRICE_TO_SALES:g}**, "
        f"**D/E ≤ {INST_ENTRY_MAX_DEBT_EQUITY:g}**, "
        f"**sales CAGR ≥ {INST_ENTRY_MIN_SALES_CAGR:g}%**, profit+, "
        f"volume ≥ {INST_ENTRY_MIN_AVG_VOLUME:,}, listed ≥ {INST_ENTRY_MIN_LISTED_YEARS:g}Y. "
        f"**Trigger:** DII+FII QoQ Δ ≥ {INST_ENTRY_MIN_DII_FII_DELTA:g}pp "
        "(first-time preferred). Shareholding from NSE XBRL / seed CSV "
        "(screener scrape optional)."
    )


__all__ = [
    "compute_inst_entry_metrics",
    "format_inst_entry_export_df",
    "in_inst_entry_mcap_band",
    "inst_entry_caption",
    "passes_quant_gates",
    "score_inst_entry",
]
