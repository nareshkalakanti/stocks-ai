"""Price snapshot for PEAD expand — price, mkt cap, PE, CAGR, MAs, 52-week range."""

from __future__ import annotations

import pandas as pd


def _sales_cagr_years(revenue: pd.Series, years: int = 3) -> float | None:
    rev = revenue.dropna().sort_index().astype(float)
    quarters_needed = years * 4
    if len(rev) <= quarters_needed:
        return None
    end = float(rev.iloc[-1])
    start = float(rev.iloc[-1 - quarters_needed])
    if start <= 0 or end <= 0:
        return None
    return round(((end / start) ** (1 / years) - 1) * 100, 1)


def build_price_snapshot(
    info: dict,
    hist: pd.DataFrame,
    revenue: pd.Series | None,
    *,
    price: float | None = None,
    pe_ratio: float | None = None,
    forward_pe: float | None = None,
) -> dict | None:
    """Build screener-style price / mkt cap / PE / Fwd PE / CAGR / MA / 52w snapshot."""
    px = price
    if px is None:
        raw = info.get("regularMarketPrice") or info.get("currentPrice")
        px = float(raw) if raw is not None and not pd.isna(raw) else None
    if px is None:
        return None

    pe_trailing = pe_ratio
    if pe_trailing is None:
        trailing = info.get("trailingPE")
        if trailing is not None and not pd.isna(trailing):
            pe_trailing = round(float(trailing), 1)

    pe_forward = forward_pe
    if pe_forward is None:
        forward = info.get("forwardPE")
        if forward is not None and not pd.isna(forward):
            pe_forward = round(float(forward), 1)

    market_cap = info.get("marketCap")
    market_cap_cr = None
    if market_cap is not None and not pd.isna(market_cap):
        market_cap_cr = round(float(market_cap) / 1e7, 1)

    cagr = _sales_cagr_years(revenue) if revenue is not None else None
    if cagr is None:
        growth = info.get("revenueGrowth") or info.get("earningsGrowth")
        if growth is not None and not pd.isna(growth):
            cagr = round(float(growth) * 100, 1)

    w52_low = info.get("fiftyTwoWeekLow")
    w52_high = info.get("fiftyTwoWeekHigh")
    low = float(w52_low) if w52_low is not None and not pd.isna(w52_low) else None
    high = float(w52_high) if w52_high is not None and not pd.isna(w52_high) else None

    close = hist["Close"].dropna().sort_index() if hist is not None and not hist.empty else pd.Series(dtype=float)
    moving_averages: list[dict] = []
    for period in (20, 50, 100, 200):
        ma_val = None
        if len(close) >= period:
            ma_val = round(float(close.tail(period).mean()), 2)
        elif period == 50:
            avg = info.get("fiftyDayAverage")
            if avg is not None and not pd.isna(avg):
                ma_val = round(float(avg), 2)
        elif period == 200:
            avg = info.get("twoHundredDayAverage")
            if avg is not None and not pd.isna(avg):
                ma_val = round(float(avg), 2)
        if ma_val is not None:
            moving_averages.append(
                {
                    "period": period,
                    "value": ma_val,
                    "above": px >= ma_val,
                }
            )

    return {
        "price": round(px, 2),
        "market_cap_cr": market_cap_cr,
        "pe": pe_trailing,
        "pe_ratio": pe_trailing,
        "forward_pe": pe_forward,
        "cagr": cagr,
        "w52_low": round(low, 2) if low is not None else None,
        "w52_high": round(high, 2) if high is not None else None,
        "moving_averages": moving_averages,
    }
