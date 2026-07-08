"""Earnings Explosion — revenue / op profit / EPS burst + margin + price/volume buy."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

NET_INCOME_FIELDS = (
    "Net Income",
    "Net Income Common Stockholders",
    "Net Income From Continuing Operation Net Minority Interest",
)

REVENUE_FIELDS = ("Total Revenue", "Operating Revenue", "Revenue")
# Screener-style operating profit ≈ EBITDA for Indian quarterly P&L.
EBIDT_FIELDS = ("EBITDA", "Operating Income", "EBIT", "Operating Income Or Loss")
OP_FIELDS = EBIDT_FIELDS
EPS_FIELDS = (
    "Diluted EPS",
    "Basic EPS",
    "Diluted EPS Including Extra Items",
    "Basic EPS Including Extra Items",
)


@dataclass(frozen=True)
class EarningsScanParams:
    jump_min: float = 1.5
    trail_quarters: int = 3
    max_streak: int = 2
    min_margin_room_pp: float = 2.0
    min_gap_pct: float = 2.0
    min_vol_ratio: float = 2.0
    require_price: bool = True


def _sorted_series(income: pd.DataFrame, fields: tuple[str, ...]) -> pd.Series | None:
    if income is None or income.empty:
        return None
    for field in fields:
        if field in income.index:
            series = income.loc[field, :].dropna().sort_index()
            if not series.empty:
                return series.astype(float)
    return None


def burst_ratio(series: pd.Series, *, trail: int) -> float | None:
    s = series.dropna().sort_index()
    if len(s) < trail + 1:
        return None
    latest = float(s.iloc[-1])
    base = float(s.iloc[-(trail + 1) : -1].mean())
    if base <= 0:
        return None
    return latest / base


def streak_up(series: pd.Series) -> int:
    s = series.dropna().sort_index()
    if len(s) < 2:
        return 0
    streak = 0
    for delta in reversed(s.diff().iloc[1:].tolist()):
        if delta is not None and not pd.isna(delta) and delta > 0:
            streak += 1
        else:
            break
    return streak


def margin_stats(revenue: pd.Series, op_profit: pd.Series) -> dict | None:
    rev = revenue.dropna().sort_index()
    op = op_profit.reindex(rev.index).astype(float)
    opm = (op / rev.replace(0, np.nan)).dropna()
    if len(opm) < 2:
        return None

    latest = float(opm.iloc[-1])
    prior = opm.iloc[:-1]
    peak = float(prior.max())
    at_ath = latest >= float(opm.max()) - 1e-9
    room_pp = max(0.0, (peak - latest) * 100)
    improving = latest > float(opm.iloc[-2])
    return {
        "opm_pct": round(latest * 100, 2),
        "opm_peak_pct": round(peak * 100, 2),
        "opm_room_pp": round(room_pp, 2),
        "opm_at_ath": at_ath,
        "opm_improving": improving,
    }


def evaluate_fundamentals(
    revenue: pd.Series,
    op_profit: pd.Series,
    eps: pd.Series,
    params: EarningsScanParams,
) -> dict:
    rev_jump = burst_ratio(revenue, trail=params.trail_quarters)
    op_jump = burst_ratio(op_profit, trail=params.trail_quarters)
    eps_jump = burst_ratio(eps, trail=params.trail_quarters)

    rev_streak = streak_up(revenue)
    op_streak = streak_up(op_profit)
    eps_streak = streak_up(eps)

    margin = margin_stats(revenue, op_profit)
    jumps_ok = all(
        x is not None and x >= params.jump_min for x in (rev_jump, op_jump, eps_jump)
    )
    streaks_ok = all(
        1 <= s <= params.max_streak for s in (rev_streak, op_streak, eps_streak)
    )
    margin_ok = False
    margin_note = ""
    if margin:
        if margin["opm_improving"]:
            if margin["opm_at_ath"]:
                margin_ok = True
                margin_note = "ATH margin"
            elif margin["opm_room_pp"] >= params.min_margin_room_pp:
                margin_ok = True
                margin_note = "Room vs peak"
            else:
                margin_note = "Low room vs peak"
        else:
            margin_note = "Margin not improving"

    passed = bool(jumps_ok and streaks_ok and margin_ok)
    return {
        "passed_fundamental": passed,
        "rev_jump": rev_jump,
        "op_jump": op_jump,
        "eps_jump": eps_jump,
        "rev_streak": rev_streak,
        "op_streak": op_streak,
        "eps_streak": eps_streak,
        "margin_note": margin_note,
        **(margin or {}),
    }


def evaluate_price_volume(
    hist: pd.DataFrame,
    result_date: pd.Timestamp,
    params: EarningsScanParams,
) -> dict:
    empty = {
        "passed_price": False,
        "gap_pct": None,
        "vol_ratio": None,
        "holds_gap": False,
        "result_date": result_date.strftime("%Y-%m-%d"),
    }
    if hist is None or hist.empty or len(hist) < 25:
        return empty

    hist = hist.sort_index()
    hist.index = pd.to_datetime(hist.index).tz_localize(None)
    result_ts = pd.Timestamp(result_date).tz_localize(None)

    on_or_after = hist[hist.index >= result_ts.normalize()]
    if on_or_after.empty:
        on_or_after = hist.tail(1)
    day = on_or_after.iloc[0]
    prior = hist[hist.index < day.name]
    if prior.empty:
        return empty

    prev_close = float(prior.iloc[-1]["Close"])
    open_px = float(day["Open"])
    close_px = float(day["Close"])
    volume = float(day.get("Volume") or 0)
    if prev_close <= 0 or open_px <= 0:
        return empty

    gap_pct = (open_px / prev_close - 1) * 100
    vol_avg = float(hist["Volume"].tail(20).mean())
    vol_ratio = volume / vol_avg if vol_avg > 0 else None
    holds_gap = close_px >= open_px * 0.98 and close_px >= prev_close

    passed = (
        gap_pct >= params.min_gap_pct
        and vol_ratio is not None
        and vol_ratio >= params.min_vol_ratio
        and holds_gap
    )
    return {
        "passed_price": passed,
        "gap_pct": round(gap_pct, 2),
        "vol_ratio": round(vol_ratio, 2) if vol_ratio is not None else None,
        "holds_gap": holds_gap,
        "result_date": pd.Timestamp(day.name).strftime("%Y-%m-%d"),
    }


def composite_score(row: dict) -> float:
    parts: list[float] = []
    for key in ("rev_jump", "op_jump", "eps_jump"):
        val = row.get(key)
        if val is not None and not pd.isna(val):
            parts.append(float(val))
    for key in ("gap_pct", "vol_ratio"):
        val = row.get(key)
        if val is not None and not pd.isna(val):
            parts.append(float(val) / 10)
    if row.get("passed_price"):
        parts.append(2.0)
    if row.get("opm_improving"):
        parts.append(0.5)
    cap = row.get("market_cap_cr")
    if cap is not None and not pd.isna(cap) and float(cap) < 5000:
        parts.append(0.5)
    return round(sum(parts), 2) if parts else 0.0


def classify_signal(fund: dict, price: dict, *, require_price: bool) -> str:
    if not fund.get("passed_fundamental"):
        return "REJECT"
    if price.get("passed_price"):
        return "EARNINGS_BUY"
    if require_price:
        return "EARNINGS_FUNDAMENTAL"
    return "EARNINGS_BUY"


def rank_earnings_results(rows: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not rows:
        empty = pd.DataFrame()
        return empty, empty

    df = pd.DataFrame(rows)
    df["score"] = df.apply(composite_score, axis=1)
    df = df.sort_values("score", ascending=False)

    buy = df[df["signal"] == "EARNINGS_BUY"].copy()
    fundamental = df[df["signal"] == "EARNINGS_FUNDAMENTAL"].copy()
    return buy.reset_index(drop=True), fundamental.reset_index(drop=True)
