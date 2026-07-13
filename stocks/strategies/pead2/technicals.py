"""Price snapshot for PEAD expand — price, mkt cap, PE, CAGR, MAs, 52-week range."""

from __future__ import annotations

from datetime import date

import pandas as pd

from stocks.core.text_utils import safe_str


def _normalize_website(url: str | None) -> str | None:
    site = safe_str(url).strip()
    if not site:
        return None
    if site.startswith(("http://", "https://")):
        return site
    return f"https://{site}"


def _profile_from_info(info: dict) -> dict[str, str | int]:
    out: dict[str, str | int] = {}
    desc = safe_str(info.get("longBusinessSummary")).strip()
    if desc:
        out["long_description"] = desc
    website = _normalize_website(info.get("website"))
    if website:
        out["website"] = website
    sector = safe_str(info.get("sector")).strip()
    if sector:
        out["company_sector"] = sector
    industry = safe_str(info.get("industry")).strip()
    if industry:
        out["company_industry"] = industry
    employees = info.get("fullTimeEmployees")
    if employees is not None:
        try:
            if not pd.isna(employees):
                out["employees"] = int(employees)
        except (TypeError, ValueError):
            pass
    hq_parts = [
        safe_str(info.get("city")).strip(),
        safe_str(info.get("state")).strip(),
        safe_str(info.get("country")).strip(),
    ]
    hq = ", ".join(part for part in hq_parts if part)
    if hq:
        out["headquarters"] = hq
    return out


def _sales_cagr_years(revenue: pd.Series, years: int = 3) -> float | None:
    rev = revenue.dropna().sort_index().astype(float)
    quarters_needed = years * 4
    if len(rev) <= quarters_needed:
        return None
    end = float(rev.iloc[-1])
    start = float(rev.iloc[-1 - quarters_needed])
    if start <= 0 or end <= 0:
        return None
    return round(((end / start) ** (1 / years) - 1) * 100, 2)


_EMA_PERIODS = (20, 50, 100, 200)


def indian_fy_labels(count: int = 4, as_of: date | None = None) -> list[str]:
    """Indian fiscal-year labels (FY26 = year ending Mar 2026) for the next ``count`` years."""
    d = as_of or date.today()
    first_fy_end = d.year + 1 if d.month >= 4 else d.year
    start = first_fy_end - 1
    return [f"FY{str(start + i)[-2:]}" for i in range(count)]


def build_expected_prices(
    price: float | None,
    *,
    pe_ratio: float | None = None,
    cagr: float | None = None,
    eps_yoy: float | None = None,
    comfortable_buy: float | None = None,
) -> list[dict[str, object]] | None:
    """
    FY26–FY29 price projection for expand panel.

    FY26 anchors on comfortable buy when available, else price grown by EPS YoY (or sales CAGR).
    Later years compound at the same growth rate.
    """
    if price is None or price <= 0:
        return None
    growth = eps_yoy if eps_yoy is not None else cagr
    if comfortable_buy is not None and comfortable_buy > 0:
        v0 = round(float(comfortable_buy))
    elif growth is not None:
        v0 = round(price * (1 + float(growth) / 100.0))
    else:
        return None

    labels = indian_fy_labels(4)
    values: list[float | None] = [v0]
    v = float(v0)
    if growth is not None:
        g = float(growth) / 100.0
        for _ in range(3):
            v *= 1 + g
            values.append(round(v))
    else:
        values.extend([None, None, None])

    return [{"fy": labels[i], "price": values[i]} for i in range(4)]


def enrich_snapshot_valuation_projection(
    snapshot: dict,
    *,
    price: float | None,
    pe_ratio: float | None = None,
    eps_yoy: float | None = None,
    comfortable_buy: float | None = None,
) -> dict:
    """Attach ``expected_prices`` to a price snapshot dict."""
    expected = build_expected_prices(
        price,
        pe_ratio=pe_ratio,
        cagr=snapshot.get("cagr"),
        eps_yoy=eps_yoy,
        comfortable_buy=comfortable_buy,
    )
    if not expected:
        return snapshot
    out = dict(snapshot)
    out["expected_prices"] = expected
    return out


def _ema_last(close: pd.Series, period: int) -> float | None:
    if len(close) < period:
        return None
    ema = close.ewm(span=period, adjust=False).mean()
    val = float(ema.iloc[-1])
    if pd.isna(val):
        return None
    return round(val, 2)


def _build_ema_averages(close: pd.Series, px: float) -> tuple[list[dict], bool | None]:
    rows: list[dict] = []
    for period in _EMA_PERIODS:
        ema_val = _ema_last(close, period)
        if ema_val is None:
            continue
        rows.append(
            {
                "period": period,
                "value": ema_val,
                "above": px >= ema_val,
            }
        )
    if not rows:
        return [], None
    return rows, all(row["above"] for row in rows)


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
            cagr = round(float(growth) * 100, 2)

    w52_low = info.get("fiftyTwoWeekLow")
    w52_high = info.get("fiftyTwoWeekHigh")
    low = float(w52_low) if w52_low is not None and not pd.isna(w52_low) else None
    high = float(w52_high) if w52_high is not None and not pd.isna(w52_high) else None

    close = hist["Close"].dropna().sort_index() if hist is not None and not hist.empty else pd.Series(dtype=float)
    price_trend: list[dict] = []
    if not close.empty:
        from stocks.strategies.sector_landscape.strategy import series_to_points

        price_trend = series_to_points(close, max_points=48)
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

    ema_averages, above_all_emas = _build_ema_averages(close, px) if not close.empty else ([], None)

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
        "ema_averages": ema_averages,
        "above_all_emas": above_all_emas,
        "price_trend": price_trend,
        **_profile_from_info(info),
    }
