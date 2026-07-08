"""Valuation Formula — comfortable buy price from 5Y avg P/B, P/S, P/CF."""

from __future__ import annotations

import pandas as pd

VALUATION_LOOKBACK_YEARS = 5
VALUATION_MIN_YEARS = 3

EQUITY_FIELDS = (
    "Stockholders Equity",
    "Total Stockholder Equity",
    "Total Stockholders Equity",
    "Shareholders Equity",
    "Total Shareholders Equity",
    "Common Stock Equity",
)

REVENUE_FIELDS = (
    "Total Revenue",
    "Operating Revenue",
    "Revenue",
)

CFO_FIELDS = (
    "Operating Cash Flow",
    "Cash From Operating Activities",
    "Total Cash From Operating Activities",
    "Cash Flow From Continuing Operating Activities",
)

SHARES_FIELDS = (
    "Basic Average Shares",
    "Diluted Average Shares",
    "Share Issued",
)


def _first_row(df: pd.DataFrame | None, fields: tuple[str, ...]) -> pd.Series | None:
    if df is None or df.empty:
        return None
    for field in fields:
        if field in df.index:
            series = df.loc[field, :].dropna()
            if not series.empty:
                return series.astype(float)
    return None


def _value_at_date(series: pd.Series | None, dt: pd.Timestamp) -> float | None:
    if series is None or series.empty:
        return None
    s = series.dropna().astype(float)
    target = pd.Timestamp(dt)
    if target in s.index:
        val = float(s.loc[target])
        return val if pd.notna(val) else None
    for idx in s.index:
        if pd.Timestamp(idx).normalize() == target.normalize():
            val = float(s.loc[idx])
            return val if pd.notna(val) else None
    year = target.year
    for idx in s.index:
        if pd.Timestamp(idx).year == year:
            val = float(s.loc[idx])
            return val if pd.notna(val) else None
    return None


def _price_near_date(hist: pd.DataFrame | None, dt: pd.Timestamp) -> float | None:
    if hist is None or hist.empty or "Close" not in hist.columns:
        return None
    px = hist.sort_index().copy()
    px.index = pd.to_datetime(px.index).tz_localize(None)
    target = pd.Timestamp(dt).tz_localize(None).normalize()
    window = px[px.index <= target]
    if window.empty:
        window = px.head(1)
    if window.empty:
        return None
    close = float(window.iloc[-1]["Close"])
    return close if close > 0 else None


def _mean_positive(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None and pd.notna(v) and v > 0]
    if len(clean) < VALUATION_MIN_YEARS:
        return None
    return round(float(sum(clean) / len(clean)), 3)


def historical_ratio_averages(
    balance_sheet: pd.DataFrame | None,
    financials: pd.DataFrame | None,
    cashflow: pd.DataFrame | None,
    hist: pd.DataFrame | None,
    *,
    fallback_shares: float | None = None,
    lookback_years: int = VALUATION_LOOKBACK_YEARS,
) -> dict[str, float | None]:
    equity = _first_row(balance_sheet, EQUITY_FIELDS)
    revenue = _first_row(financials, REVENUE_FIELDS)
    cfo = _first_row(cashflow, CFO_FIELDS)
    shares_s = _first_row(financials, SHARES_FIELDS)

    if equity is None or equity.empty:
        return {"pb_avg": None, "ps_avg": None, "pcf_avg": None, "years_used": 0}

    dates = sorted(
        [pd.Timestamp(d) for d in equity.index],
        reverse=True,
    )[:lookback_years]

    pb_hist: list[float] = []
    ps_hist: list[float] = []
    pcf_hist: list[float] = []

    for dt in dates:
        eq = _value_at_date(equity, dt)
        rev = _value_at_date(revenue, dt) if revenue is not None else None
        cf = _value_at_date(cfo, dt) if cfo is not None else None
        sh = _value_at_date(shares_s, dt) if shares_s is not None else None
        if sh is None or sh <= 0:
            sh = fallback_shares
        price = _price_near_date(hist, dt)
        if not eq or not sh or not price or eq <= 0 or sh <= 0:
            continue
        bvps = eq / sh
        if bvps > 0:
            pb_hist.append(price / bvps)
        if rev and rev > 0:
            ps_hist.append(price / (rev / sh))
        if cf and cf > 0:
            pcf_hist.append(price / (cf / sh))

    return {
        "pb_avg": _mean_positive(pb_hist),
        "ps_avg": _mean_positive(ps_hist),
        "pcf_avg": _mean_positive(pcf_hist),
        "years_used": max(len(pb_hist), len(ps_hist), len(pcf_hist)),
    }


def evaluate_valuation_formula(
    *,
    price: float | None,
    info: dict,
    balance_sheet: pd.DataFrame | None,
    financials: pd.DataFrame | None,
    cashflow: pd.DataFrame | None,
    hist: pd.DataFrame | None,
) -> dict | None:
    """Return current ratios, 5Y averages, pass flags, and comfortable buy price."""
    if price is None or price <= 0:
        return None

    book_value = info.get("bookValue")
    shares = info.get("sharesOutstanding")
    try:
        bvps = float(book_value) if book_value is not None and not pd.isna(book_value) else None
    except (TypeError, ValueError):
        bvps = None
    try:
        shares_f = float(shares) if shares is not None and not pd.isna(shares) else None
    except (TypeError, ValueError):
        shares_f = None

    avgs = historical_ratio_averages(
        balance_sheet,
        financials,
        cashflow,
        hist,
        fallback_shares=shares_f,
    )
    pb_avg = avgs.get("pb_avg")
    ps_avg = avgs.get("ps_avg")
    pcf_avg = avgs.get("pcf_avg")

    pb_now = info.get("priceToBook")
    if pb_now is None or (isinstance(pb_now, float) and pd.isna(pb_now)):
        pb_now = (price / bvps) if bvps and bvps > 0 else None
    else:
        pb_now = float(pb_now)

    ps_now = info.get("priceToSalesTrailing12Months")
    if ps_now is None or (isinstance(ps_now, float) and pd.isna(ps_now)):
        rev = _first_row(financials, REVENUE_FIELDS)
        latest_rev = float(rev.iloc[0]) if rev is not None and not rev.empty else None
        if latest_rev and shares_f and shares_f > 0:
            ps_now = price / (latest_rev / shares_f)
        else:
            ps_now = None
    else:
        ps_now = float(ps_now)

    pcf_now = None
    op_cf = info.get("operatingCashflow")
    if op_cf is not None and not pd.isna(op_cf) and shares_f and shares_f > 0:
        pcf_now = price / (float(op_cf) / shares_f)
    elif bvps:
        cfo = _first_row(cashflow, CFO_FIELDS)
        latest_cfo = float(cfo.iloc[0]) if cfo is not None and not cfo.empty else None
        if latest_cfo and shares_f and shares_f > 0:
            pcf_now = price / (latest_cfo / shares_f)

    rev = _first_row(financials, REVENUE_FIELDS)
    cfo_s = _first_row(cashflow, CFO_FIELDS)
    latest_rev = float(rev.iloc[0]) if rev is not None and not rev.empty else None
    latest_cfo = float(cfo_s.iloc[0]) if cfo_s is not None and not cfo_s.empty else None

    sps = (latest_rev / shares_f) if latest_rev and shares_f and shares_f > 0 else None
    cfps = (latest_cfo / shares_f) if latest_cfo and shares_f and shares_f > 0 else None

    ceilings: list[float] = []
    if pb_avg and bvps and bvps > 0:
        ceilings.append(pb_avg * bvps)
    if ps_avg and sps and sps > 0:
        ceilings.append(ps_avg * sps)
    if pcf_avg and cfps and cfps > 0:
        ceilings.append(pcf_avg * cfps)

    comfortable_buy = round(min(ceilings), 2) if ceilings else None

    def _pass(now: float | None, avg: float | None) -> bool | None:
        if now is None or avg is None:
            return None
        return bool(now < avg)

    pass_pb = _pass(pb_now, pb_avg if isinstance(pb_avg, float) else None)
    pass_ps = _pass(ps_now, ps_avg if isinstance(ps_avg, float) else None)
    pass_pcf = _pass(pcf_now, pcf_avg if isinstance(pcf_avg, float) else None)
    passes = [p for p in (pass_pb, pass_ps, pass_pcf) if p is not None]
    valuation_pass = bool(passes) and all(passes)

    discount_pct = None
    if comfortable_buy and comfortable_buy > 0:
        discount_pct = round((comfortable_buy / price - 1.0) * 100.0, 1)

    return {
        "pb": round(pb_now, 2) if pb_now is not None else None,
        "pb_avg_5y": pb_avg,
        "ps": round(ps_now, 2) if ps_now is not None else None,
        "ps_avg_5y": ps_avg,
        "pcf": round(pcf_now, 2) if pcf_now is not None else None,
        "pcf_avg_5y": pcf_avg,
        "pass_pb": pass_pb,
        "pass_ps": pass_ps,
        "pass_pcf": pass_pcf,
        "valuation_pass": valuation_pass,
        "comfortable_buy_price": comfortable_buy,
        "buy_headroom_pct": discount_pct,
        "valuation_years": avgs.get("years_used", 0),
        "criteria_score": sum(1 for p in (pass_pb, pass_ps, pass_pcf) if p is True),
    }


def comfort_buy_fields(
    *,
    price: float | None,
    info: dict,
    balance_sheet: pd.DataFrame | None,
    financials: pd.DataFrame | None,
    cashflow: pd.DataFrame | None,
    hist: pd.DataFrame | None,
) -> dict:
    """Subset for PEAD dashboards — comfort buy price + headroom."""
    result = evaluate_valuation_formula(
        price=price,
        info=info,
        balance_sheet=balance_sheet,
        financials=financials,
        cashflow=cashflow,
        hist=hist,
    )
    if not result:
        return {
            "comfortable_buy_price": None,
            "buy_headroom_pct": None,
            "valuation_pass": None,
        }
    return {
        "comfortable_buy_price": result.get("comfortable_buy_price"),
        "buy_headroom_pct": result.get("buy_headroom_pct"),
        "valuation_pass": result.get("valuation_pass"),
    }
