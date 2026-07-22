"""DCF — forecast FCF + terminal value → fair price / reverse implied growth."""

from __future__ import annotations

from typing import Iterable

import pandas as pd

from stocks.core.config import (
    DCF_DISCOUNT_RATE,
    DCF_FAIR_BAND_PCT,
    DCF_FORECAST_YEARS,
    DCF_GROWTH_CAP_PCT,
    DCF_GROWTH_PCT,
    DCF_TERMINAL_GROWTH,
)
from stocks.strategies.cash_quality.strategy import CAPEX_FIELDS
from stocks.strategies.valuation_formula.strategy import CFO_FIELDS, _first_row

FCF_FIELDS = (
    "Free Cash Flow",
    "FreeCashFlow",
)


def _sorted_desc(series: pd.Series | None) -> pd.Series | None:
    if series is None or series.empty:
        return None
    s = series.dropna().astype(float).sort_index(ascending=False)
    return s if not s.empty else None


def _latest(series: pd.Series | None) -> float | None:
    s = _sorted_desc(series)
    if s is None:
        return None
    return float(s.iloc[0])


def _cagr(series: pd.Series | None, *, preferred_years: int = 3) -> float | None:
    s = _sorted_desc(series)
    if s is None:
        return None
    for years in range(preferred_years, 1, -1):
        if len(s) < years + 1:
            continue
        latest = float(s.iloc[0])
        prior = float(s.iloc[years])
        if latest <= 0 or prior <= 0:
            continue
        return (latest / prior) ** (1 / years) - 1
    return None


def free_cash_flow_series(cashflow: pd.DataFrame | None) -> pd.Series | None:
    """Prefer Yahoo Free Cash Flow row; else OCF + CapEx (CapEx usually negative)."""
    fcf = _first_row(cashflow, FCF_FIELDS)
    if fcf is not None and not fcf.empty:
        return fcf.astype(float)
    ocf = _first_row(cashflow, CFO_FIELDS)
    capex = _first_row(cashflow, CAPEX_FIELDS)
    if ocf is None or ocf.empty:
        return None
    if capex is None or capex.empty:
        return ocf.astype(float)
    # Align on common dates.
    idx = ocf.index.intersection(capex.index)
    if idx.empty:
        return ocf.astype(float)
    return (ocf.loc[idx].astype(float) + capex.loc[idx].astype(float)).dropna()


def base_fcf(
    info: dict | None,
    cashflow: pd.DataFrame | None,
) -> float | None:
    info = info or {}
    raw = info.get("freeCashflow")
    if raw is not None and not pd.isna(raw) and float(raw) > 0:
        return float(raw)
    series = free_cash_flow_series(cashflow)
    latest = _latest(series)
    if latest is not None and latest > 0:
        return latest
    return None


def resolve_growth_rate(
    cashflow: pd.DataFrame | None,
    *,
    growth_pct: float | None = None,
) -> float:
    """
    Annual FCF growth used in the explicit forecast.

    Priority: explicit override → env DCF_GROWTH_PCT → historical CAGR (capped) → 0.
    """
    if growth_pct is not None and not pd.isna(growth_pct):
        return float(growth_pct) / 100.0
    if DCF_GROWTH_PCT not in (None, ""):
        try:
            return float(DCF_GROWTH_PCT) / 100.0
        except ValueError:
            pass
    hist = _cagr(free_cash_flow_series(cashflow), preferred_years=3)
    if hist is None:
        return 0.0
    cap = DCF_GROWTH_CAP_PCT / 100.0
    return max(-0.5, min(float(hist), cap))


def project_cash_flows(
    base: float,
    *,
    years: int,
    growth: float,
) -> list[float]:
    """CF_t = base * (1+g)^t for t = 1..N."""
    n = max(1, int(years))
    g = float(growth)
    return [float(base) * ((1.0 + g) ** t) for t in range(1, n + 1)]


def discount_factor(rate: float, t: int) -> float:
    return 1.0 / ((1.0 + float(rate)) ** int(t))


def present_value_cash_flows(
    cash_flows: Iterable[float],
    *,
    discount_rate: float,
) -> tuple[float, list[dict]]:
    """Sum PV of explicit forecast; also return year-by-year schedule."""
    schedule: list[dict] = []
    total = 0.0
    for i, cf in enumerate(cash_flows, start=1):
        df = discount_factor(discount_rate, i)
        pv = float(cf) * df
        total += pv
        schedule.append(
            {
                "year": i,
                "cash_flow": round(float(cf), 2),
                "discount_factor": round(df, 4),
                "present_value": round(pv, 2),
            }
        )
    return total, schedule


def gordon_terminal_value(
    final_cf: float,
    *,
    discount_rate: float,
    terminal_growth: float,
) -> float | None:
    """TV = CF_N * (1+g) / (r - g). Requires r > g."""
    r = float(discount_rate)
    g = float(terminal_growth)
    if r <= g:
        return None
    return float(final_cf) * (1.0 + g) / (r - g)


def run_dcf(
    base_cash_flow: float,
    *,
    discount_rate: float | None = None,
    forecast_years: int | None = None,
    growth: float | None = None,
    terminal_growth: float | None = None,
    net_debt: float | None = None,
    shares: float | None = None,
    market_price: float | None = None,
) -> dict | None:
    """
    Two-stage DCF (explicit forecast + Gordon terminal).

    Value = Σ PV(CF_t) + PV(TV) − net_debt
    fair_price = equity_value / shares
    """
    if base_cash_flow is None or base_cash_flow <= 0:
        return None
    r = DCF_DISCOUNT_RATE if discount_rate is None else float(discount_rate)
    n = DCF_FORECAST_YEARS if forecast_years is None else int(forecast_years)
    g = 0.0 if growth is None else float(growth)
    g_term = DCF_TERMINAL_GROWTH if terminal_growth is None else float(terminal_growth)
    if r <= 0 or n < 1:
        return None

    flows = project_cash_flows(base_cash_flow, years=n, growth=g)
    pv_forecast, schedule = present_value_cash_flows(flows, discount_rate=r)
    tv = gordon_terminal_value(flows[-1], discount_rate=r, terminal_growth=g_term)
    if tv is None:
        return None
    pv_tv = tv * discount_factor(r, n)
    enterprise = pv_forecast + pv_tv
    debt = float(net_debt) if net_debt is not None and not pd.isna(net_debt) else 0.0
    equity = enterprise - debt
    fair_price = None
    if shares is not None and not pd.isna(shares) and float(shares) > 0:
        fair_price = equity / float(shares)

    upside_pct = None
    verdict = None
    if (
        fair_price is not None
        and market_price is not None
        and not pd.isna(market_price)
        and float(market_price) > 0
    ):
        upside_pct = (fair_price / float(market_price) - 1.0) * 100.0
        band = DCF_FAIR_BAND_PCT
        if upside_pct > band:
            verdict = "Undervalued"
        elif upside_pct < -band:
            verdict = "Overvalued"
        else:
            verdict = "Fair"

    return {
        "base_fcf": round(float(base_cash_flow), 2),
        "growth": round(g * 100.0, 2),
        "discount_rate": round(r * 100.0, 2),
        "terminal_growth": round(g_term * 100.0, 2),
        "forecast_years": n,
        "pv_forecast": round(pv_forecast, 2),
        "terminal_value": round(tv, 2),
        "pv_terminal": round(pv_tv, 2),
        "enterprise_value": round(enterprise, 2),
        "net_debt": round(debt, 2),
        "equity_value": round(equity, 2),
        "shares": float(shares) if shares is not None and not pd.isna(shares) else None,
        "fair_price": round(fair_price, 2) if fair_price is not None else None,
        "upside_pct": round(upside_pct, 2) if upside_pct is not None else None,
        "verdict": verdict,
        "schedule": schedule,
    }


def implied_growth_rate(
    base_cash_flow: float,
    market_price: float,
    *,
    discount_rate: float | None = None,
    forecast_years: int | None = None,
    terminal_growth: float | None = None,
    net_debt: float | None = None,
    shares: float | None = None,
    lo: float = -0.4,
    hi: float | None = None,
    tol: float = 1e-4,
    max_iter: int = 60,
) -> float | None:
    """
    Reverse DCF: growth g such that model fair_price ≈ market_price.

    Terminal growth held fixed. Returns growth as a fraction (0.12 = 12%).
    """
    if (
        base_cash_flow is None
        or base_cash_flow <= 0
        or market_price is None
        or market_price <= 0
        or shares is None
        or shares <= 0
    ):
        return None
    r = DCF_DISCOUNT_RATE if discount_rate is None else float(discount_rate)
    g_term = DCF_TERMINAL_GROWTH if terminal_growth is None else float(terminal_growth)
    # Keep room under discount rate for Gordon (forecast g can exceed g_term).
    upper = (r - 0.005) if hi is None else float(hi)
    if upper <= lo:
        return None

    def _price_at(g: float) -> float | None:
        out = run_dcf(
            base_cash_flow,
            discount_rate=r,
            forecast_years=forecast_years,
            growth=g,
            terminal_growth=g_term,
            net_debt=net_debt,
            shares=shares,
            market_price=market_price,
        )
        if not out or out.get("fair_price") is None:
            return None
        return float(out["fair_price"])

    p_lo = _price_at(lo)
    p_hi = _price_at(upper)
    if p_lo is None or p_hi is None:
        return None
    # Target may sit outside bracket (always cheap / always expensive).
    if market_price < min(p_lo, p_hi) - 1e-6:
        return lo if p_lo <= p_hi else upper
    if market_price > max(p_lo, p_hi) + 1e-6:
        return upper if p_hi >= p_lo else lo

    a, b = lo, upper
    for _ in range(max_iter):
        mid = (a + b) / 2.0
        p_mid = _price_at(mid)
        if p_mid is None:
            return None
        if abs(p_mid - market_price) / market_price < tol:
            return mid
        # Higher growth → higher fair price (monotone for sensible ranges).
        if p_mid < market_price:
            a = mid
        else:
            b = mid
    return (a + b) / 2.0


def net_debt_from_info(info: dict | None) -> float:
    info = info or {}
    debt = info.get("totalDebt")
    cash = info.get("totalCash") or info.get("cash")
    d = float(debt) if debt is not None and not pd.isna(debt) else 0.0
    c = float(cash) if cash is not None and not pd.isna(cash) else 0.0
    return d - c


def shares_from_info(info: dict | None) -> float | None:
    info = info or {}
    for key in ("sharesOutstanding", "impliedSharesOutstanding"):
        val = info.get(key)
        if val is not None and not pd.isna(val) and float(val) > 0:
            return float(val)
    return None


def compute_dcf_metrics(
    info: dict | None,
    cashflow: pd.DataFrame | None,
    *,
    price: float | None = None,
    discount_rate: float | None = None,
    forecast_years: int | None = None,
    growth_pct: float | None = None,
    terminal_growth: float | None = None,
) -> dict | None:
    """Pull FCF / shares / net debt from Yahoo and run forward + reverse DCF."""
    info = info or {}
    fcf = base_fcf(info, cashflow)
    if fcf is None:
        return None
    shares = shares_from_info(info)
    net_debt = net_debt_from_info(info)
    g = resolve_growth_rate(cashflow, growth_pct=growth_pct)
    model = run_dcf(
        fcf,
        discount_rate=discount_rate,
        forecast_years=forecast_years,
        growth=g,
        terminal_growth=terminal_growth,
        net_debt=net_debt,
        shares=shares,
        market_price=price,
    )
    if not model:
        return None
    implied = implied_growth_rate(
        fcf,
        float(price) if price is not None else 0.0,
        discount_rate=discount_rate,
        forecast_years=forecast_years,
        terminal_growth=terminal_growth,
        net_debt=net_debt,
        shares=shares,
    )
    model["implied_growth"] = (
        round(implied * 100.0, 2) if implied is not None else None
    )
    # Drop bulky schedule from scan rows (kept for single-ticker detail).
    return model


def score_dcf(df: pd.DataFrame) -> pd.DataFrame:
    """Rank by upside % (undervalued first); keep rows with a fair price."""
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df
    out = df.copy()
    out = out[out["fair_price"].notna()].copy()
    if out.empty:
        return out
    out["upside_pct"] = pd.to_numeric(out["upside_pct"], errors="coerce")
    out = out.sort_values(
        ["upside_pct", "fair_price"],
        ascending=[False, True],
        na_position="last",
    ).reset_index(drop=True)
    out.insert(0, "rank", range(1, len(out) + 1))
    return out


def format_dcf_export_df(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        ("rank", "rank"),
        ("ticker", "ticker"),
        ("name", "name"),
        ("verdict", "verdict"),
        ("price", "price"),
        ("fair_price", "fair_price"),
        ("upside_pct", "upside_pct"),
        ("implied_growth", "implied_growth_pct"),
        ("growth", "assumed_growth_pct"),
        ("discount_rate", "discount_rate_pct"),
        ("terminal_growth", "terminal_growth_pct"),
        ("base_fcf", "base_fcf"),
        ("equity_value", "equity_value"),
        ("pv_forecast", "pv_forecast"),
        ("pv_terminal", "pv_terminal"),
        ("net_debt", "net_debt"),
        ("market_cap_cr", "market_cap_cr"),
        ("sector", "sector"),
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=[a for _, a in cols])
    out = pd.DataFrame()
    for src, alias in cols:
        out[alias] = df[src] if src in df.columns else pd.NA
    return out


def dcf_caption() -> str:
    g_note = (
        f"forced growth {DCF_GROWTH_PCT}%"
        if DCF_GROWTH_PCT not in (None, "")
        else f"hist FCF CAGR (cap {DCF_GROWTH_CAP_PCT:g}%)"
    )
    return (
        f"**DCF** — {DCF_FORECAST_YEARS}Y FCF forecast ({g_note}) + Gordon terminal "
        f"(g={DCF_TERMINAL_GROWTH * 100:g}%), discount **{DCF_DISCOUNT_RATE * 100:g}%**. "
        f"Fair band ±{DCF_FAIR_BAND_PCT:g}%. Reverse DCF = growth priced in by the market. "
        "One model only — cross-check with PEG / quality screens."
    )


__all__ = [
    "base_fcf",
    "compute_dcf_metrics",
    "dcf_caption",
    "format_dcf_export_df",
    "free_cash_flow_series",
    "gordon_terminal_value",
    "implied_growth_rate",
    "net_debt_from_info",
    "present_value_cash_flows",
    "project_cash_flows",
    "resolve_growth_rate",
    "run_dcf",
    "score_dcf",
    "shares_from_info",
]
