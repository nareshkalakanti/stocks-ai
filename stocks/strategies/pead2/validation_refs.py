"""PEAD validation helpers — load tests/data/pead_references.json."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yfinance as yf

from stocks.market.price_service import to_yfinance_symbol
from stocks.strategies.earnings.strategy import (
    EPS_FIELDS,
    NET_INCOME_FIELDS,
    OP_FIELDS,
    REVENUE_FIELDS,
    _sorted_series,
)
from stocks.strategies.pead2.strategy import compute_growth_metrics

REFERENCES_PATH = (
    Path(__file__).resolve().parents[3] / "tests" / "data" / "pead_references.json"
)

YFINANCE_SYMBOLS = (
    "KPL",
    "BLACKBUCK",
    "WPIL",
    "JAYBARMARU",
    "SOUTHWEST",
    "MODIS",
    "TSFINV",
)


def load_pead_references() -> dict:
    with open(REFERENCES_PATH, encoding="utf-8") as f:
        return json.load(f)


def ff_dashboard_rows() -> list[dict]:
    return load_pead_references().get("ff_returns_dashboard_2026_07_10", {}).get("rows", [])


def ff_daily_ret_rows() -> list[dict]:
    return load_pead_references().get("ff_daily_ret_dashboard_2026_07_10", {}).get("rows", [])


def ff_reference_by_ticker() -> dict[str, dict]:
    """Merge FF screenshot rows; daily-ret batch wins on duplicate tickers."""
    merged: dict[str, dict] = {}
    refs = load_pead_references()
    for key in ("ff_returns_dashboard_2026_07_10", "ff_daily_ret_dashboard_2026_07_10"):
        for row in refs.get(key, {}).get("rows", []):
            merged[str(row["ticker"])] = dict(row)
    return merged


def live_returns_vs_ff(
    ticker: str,
    row: dict,
    *,
    market: str = "NSE",
    tol: float = 2.0,
) -> tuple[float | None, float | None]:
    """Compute returns with FF result_date; return (live, expected)."""
    symbol = to_yfinance_symbol(ticker, market)
    yt = yf.Ticker(symbol)
    info = yt.info or {}
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if price is None:
        return None, row.get("returns_pct")
    rd = pd.Timestamp(row["result_date"])
    hist = yt.history(
        start=(rd - pd.Timedelta(days=5)).strftime("%Y-%m-%d"),
        auto_adjust=True,
    )
    if hist is None or hist.empty:
        return None, row.get("returns_pct")
    from stocks.strategies.pead2.strategy import compute_return_since_result

    live = compute_return_since_result(hist, rd, current_price=float(price))
    return live, row.get("returns_pct")


def assert_close(actual, expected, tol: float, label: str) -> None:
    if expected is None:
        return
    if actual is None:
        raise AssertionError(f"{label}: got None, expected {expected}")
    if abs(float(actual) - float(expected)) > tol:
        raise AssertionError(f"{label}: got {actual}, expected {expected} ±{tol}")


def extract_raw_quarterly(ticker: str, *, market: str = "NSE") -> dict:
    """Quarterly lakhs / growth from yfinance (same basis as stock-analysis refs)."""
    symbol = to_yfinance_symbol(ticker, market)
    qi = yf.Ticker(symbol).quarterly_income_stmt
    if qi is None or qi.empty:
        raise ValueError(f"No quarterly income for {ticker}")

    quarters = sorted(qi.columns, reverse=True)
    if len(quarters) < 4:
        raise ValueError(f"Need 4+ quarters for {ticker}, got {len(quarters)}")

    q0, q1 = quarters[0], quarters[1]
    q0_obj = pd.Timestamp(q0)
    qy = None
    for q_date in quarters:
        q_obj = pd.Timestamp(q_date)
        if q_obj.quarter == q0_obj.quarter and q_obj.year == q0_obj.year - 1:
            qy = q_date
            break
    if qy is None:
        raise ValueError(f"No YoY quarter for {ticker} (q0={q0_obj.date()})")

    def _lakhs(field: str, col) -> float | None:
        if field not in qi.index:
            return None
        val = qi.loc[field, col]
        return round(float(val) / 1e5, 2) if pd.notna(val) else None

    def _ebitda_pct(col) -> float | None:
        if "EBITDA" not in qi.index or "Total Revenue" not in qi.index:
            return None
        rev = qi.loc["Total Revenue", col]
        ebitda = qi.loc["EBITDA", col]
        if pd.isna(rev) or pd.isna(ebitda) or not rev:
            return None
        return round(float(ebitda / rev * 100), 2)

    rev0 = float(qi.loc["Total Revenue", q0])
    rev1 = float(qi.loc["Total Revenue", q1])
    revy = float(qi.loc["Total Revenue", qy])
    np0 = float(qi.loc["Net Income", q0])
    npy = float(qi.loc["Net Income", qy])

    return {
        "symbol": ticker,
        "q0_end": str(pd.Timestamp(q0).date()),
        "revenue_q0_lakhs": _lakhs("Total Revenue", q0),
        "revenue_q1_lakhs": _lakhs("Total Revenue", q1),
        "revenue_yoy_lakhs": _lakhs("Total Revenue", qy),
        "np_q0_lakhs": _lakhs("Net Income", q0),
        "np_q1_lakhs": _lakhs("Net Income", q1),
        "np_yoy_lakhs": _lakhs("Net Income", qy),
        "ebitda_pct_q0": _ebitda_pct(q0),
        "ebitda_pct_q1": _ebitda_pct(q1),
        "ebitda_pct_yoy": _ebitda_pct(qy),
        "sales_yoy_pct": round((rev0 - revy) / abs(revy) * 100, 1),
        "sales_qoq_pct": round((rev0 - rev1) / abs(rev1) * 100, 1),
        "np_yoy_pct": round((np0 - npy) / abs(npy) * 100, 1),
    }


def pead2_growth_for_ticker(ticker: str, *, market: str = "NSE") -> dict:
    """Growth metrics via PEAD2 compute_growth_metrics on latest yfinance quarters."""
    symbol = to_yfinance_symbol(ticker, market)
    yt = yf.Ticker(symbol)
    qi = yt.quarterly_income_stmt
    if qi is None or qi.empty:
        raise ValueError(f"No quarterly income for {ticker}")

    rev = _sorted_series(qi, REVENUE_FIELDS)
    np_s = _sorted_series(qi, NET_INCOME_FIELDS)
    eb = _sorted_series(qi, OP_FIELDS)
    ep = _sorted_series(qi, EPS_FIELDS)
    if rev is None or np_s is None or eb is None or ep is None:
        raise ValueError(f"Incomplete quarterly series for {ticker}")

    growth = compute_growth_metrics(rev, np_s, eb, ep)
    info = yt.info or {}
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    return {
        "ticker": ticker,
        "price": float(price) if price is not None else None,
        **growth,
    }
