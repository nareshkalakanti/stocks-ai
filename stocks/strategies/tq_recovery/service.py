"""TQ W52 recovery scan — 52-week RS below zero, turning up from red to yellow."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from stocks.market.indicators import align_weekly_with_nifty, calculate_relative_strength, get_nifty_data
from stocks.strategies.tq_bb.service import (
    _enrich_results,
    _listing_rows,
    _run_parallel_scan,
    _tq_workers,
    is_skippable_symbol,
    prepare_strategy_universe,
    run_tq_worker_count,
)
from stocks.core.text_utils import safe_str

# TradingView TQ : W52 inputs (screenshot defaults)
TQ_RS_LONG_TERM = 52
TQ_RS_LONG_EXIT_THRESHOLD = -0.25
TQ_RS_SHORT_TERM = 13
TQ_SUPERTREND_ATR = 10
TQ_SUPERTREND_FACTOR = 3
TQ_RSI_LENGTH = 21
TQ_RSI_ENTRY = 55
TQ_RSI_EXIT = 45
TQ_ADX_THRESHOLD = 20
TQ_DMI_LENGTH = 13
TQ_MA_LENGTH = 13

TQ_ZONE_RED = "red"
TQ_ZONE_YELLOW = "yellow"
TQ_ZONE_GREEN = "green"


def classify_tq_zone(
    rs: float | None,
    prev_rs: float | None,
) -> str | None:
    """Map 52W RS to chart zone: green (≥0), yellow (below 0, rising), red (below 0, flat/falling)."""
    if rs is None or (isinstance(rs, float) and pd.isna(rs)):
        return None
    if rs >= 0:
        return TQ_ZONE_GREEN
    if prev_rs is not None and not pd.isna(prev_rs) and rs > prev_rs:
        return TQ_ZONE_YELLOW
    return TQ_ZONE_RED


def is_red_becoming_yellow(
    rs: float | None,
    prev_rs: float | None,
    prev2_rs: float | None,
    *,
    deep_red: float = -0.15,
) -> bool:
    """TQ below zero, rising (yellow), recently in red."""
    if rs is None or prev_rs is None or (isinstance(rs, float) and pd.isna(rs)):
        return False
    if rs >= 0 or rs <= prev_rs:
        return False

    zone = classify_tq_zone(rs, prev_rs)
    if zone != TQ_ZONE_YELLOW:
        return False

    if prev2_rs is None or (isinstance(prev2_rs, float) and pd.isna(prev2_rs)):
        return prev_rs < deep_red

    prev_zone = classify_tq_zone(prev_rs, prev2_rs)
    return prev_zone == TQ_ZONE_RED or prev_rs <= prev2_rs or prev_rs < deep_red


def _fetch_weekly(ticker: str, market: str | None):
    from stocks.strategies.tq_bb.service import _fetch_history

    return _fetch_history(ticker, market, period="2y", interval="1wk")


def analyze_tq_recovery(ticker: str, market: str | None, nifty_data: pd.DataFrame) -> dict | None:
    if is_skippable_symbol(ticker):
        return None

    data = _fetch_weekly(ticker, market)
    if data is None or len(data) < TQ_RS_LONG_TERM + 5:
        return None

    data, nifty = align_weekly_with_nifty(data, nifty_data)
    if data is None or nifty is None:
        return None

    rs_long = calculate_relative_strength(data, nifty, TQ_RS_LONG_TERM)
    rs_short = calculate_relative_strength(data, nifty, TQ_RS_SHORT_TERM)

    if len(rs_long) < 3:
        return None

    current_rs = float(rs_long.iloc[-1])
    prev_rs = float(rs_long.iloc[-2])
    prev2_rs = float(rs_long.iloc[-3])

    if pd.isna(current_rs) or pd.isna(prev_rs):
        return None

    if not is_red_becoming_yellow(current_rs, prev_rs, prev2_rs):
        return None

    short_rs = float(rs_short.iloc[-1]) if len(rs_short) else None
    zone = classify_tq_zone(current_rs, prev_rs)
    latest = data.iloc[-1]
    price = float(latest["Close"])

    rs_delta = round(current_rs - prev_rs, 4)
    depth = round(current_rs - TQ_RS_LONG_EXIT_THRESHOLD, 4)
    recovery_score = round(max(0, rs_delta * 1000) + max(0, -current_rs * 50), 2)

    return {
        "ticker": safe_str(ticker).upper(),
        "market": safe_str(market) or None,
        "price": round(price, 2),
        "tq_w52": round(current_rs, 4),
        "tq_w52_prev": round(prev_rs, 4),
        "tq_change": rs_delta,
        "tq_zone": zone or TQ_ZONE_YELLOW,
        "short_term_rs": round(short_rs, 4) if short_rs is not None and not pd.isna(short_rs) else None,
        "recovery_score": recovery_score,
        "depth_vs_exit": depth,
        "signal": "TQ_RECOVERY",
        "date": latest.name.strftime("%Y-%m-%d"),
        "timeframe": "weekly",
    }


def run_tq_recovery_scan(
    universe: pd.DataFrame,
    *,
    limit: int | None = None,
    max_workers: int | None = None,
    progress_callback=None,
    should_stop: Callable[[], bool] | None = None,
) -> pd.DataFrame:
    listings = _listing_rows(universe)
    if limit is not None and limit > 0:
        listings = listings[:limit]

    if not listings:
        return pd.DataFrame()

    nifty_data = get_nifty_data()
    if nifty_data.empty:
        return pd.DataFrame()

    meta = {
        safe_str(row.get("ticker")).upper(): {
            "name": safe_str(row.get("name")),
            "market": safe_str(row.get("market")) or None,
            "sector": safe_str(row.get("sector")),
            "industry": safe_str(row.get("industry")),
            "sub_sector": safe_str(row.get("sub_sector")),
        }
        for _, row in universe.iterrows()
        if safe_str(row.get("ticker"))
    }

    jobs = [(ticker, market, nifty_data) for ticker, market in listings]
    results = _run_parallel_scan(
        jobs,
        analyze_tq_recovery,
        workers=_tq_workers(max_workers, len(jobs)),
        progress_callback=progress_callback,
        should_stop=should_stop,
        accept_result=lambda res: res is not None and res.get("signal") == "TQ_RECOVERY",
    )

    df = _enrich_results(results, meta)
    if df.empty:
        return df

    df = df.sort_values(["recovery_score", "tq_change"], ascending=[False, False])
    return df.reset_index(drop=True)


prepare_tq_recovery_universe = prepare_strategy_universe
