"""Cup & Handle and VCP pattern scanners (daily / weekly)."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

import pandas as pd

from stocks.core.text_utils import safe_str
from stocks.strategies.cup_vcp.detect import analyze_ticker_patterns
from stocks.strategies.tq_bb.service import (
    _enrich_results,
    _fetch_history,
    _listing_rows,
    _run_parallel_scan,
    _tq_workers,
    is_skippable_symbol,
    prepare_strategy_universe,
    run_tq_worker_count,
)

HISTORY_BY_TF = {
    "daily": ("1y", "1d", 60),
    "weekly": ("5y", "1wk", 40),
}

PATTERN_CUP_HANDLE = "CUP_HANDLE"
PATTERN_VCP = "VCP"


def _history_cfg(timeframe: str) -> tuple[str, str, int]:
    tf = safe_str(timeframe).lower() or "daily"
    return HISTORY_BY_TF.get(tf, HISTORY_BY_TF["daily"])


def _analyze(
    ticker: str,
    market: str | None,
    *,
    pattern_code: str,
    timeframe: str = "daily",
) -> dict | None:
    if is_skippable_symbol(ticker):
        return None
    period, interval, min_bars = _history_cfg(timeframe)
    data = _fetch_history(ticker, market, period=period, interval=interval)
    if data is None or len(data) < min_bars:
        return None
    return analyze_ticker_patterns(
        ticker,
        market,
        data,
        pattern_code=pattern_code,
        timeframe=safe_str(timeframe).lower() or "daily",
    )


def analyze_cup_handle(
    ticker: str,
    market: str | None = None,
    *,
    timeframe: str = "weekly",
) -> dict | None:
    return _analyze(
        ticker, market, pattern_code=PATTERN_CUP_HANDLE, timeframe=timeframe
    )


def analyze_vcp(ticker: str, market: str | None = None) -> dict | None:
    return _analyze(ticker, market, pattern_code=PATTERN_VCP, timeframe="daily")


def analyze_cup_vcp(ticker: str, market: str | None = None) -> dict | None:
    """Best cup or VCP hit (legacy daily)."""
    if is_skippable_symbol(ticker):
        return None
    period, interval, min_bars = _history_cfg("daily")
    data = _fetch_history(ticker, market, period=period, interval=interval)
    if data is None or len(data) < min_bars:
        return None
    return analyze_ticker_patterns(ticker, market, data, timeframe="daily")


def run_pattern_scan(
    universe: pd.DataFrame,
    *,
    pattern_code: str,
    timeframe: str = "daily",
    limit: int | None = None,
    max_workers: int | None = None,
    progress_callback=None,
    should_stop: Callable[[], bool] | None = None,
) -> pd.DataFrame:
    code = safe_str(pattern_code).upper()
    tf = safe_str(timeframe).lower() or "daily"
    if code == PATTERN_CUP_HANDLE:
        worker = partial(analyze_cup_handle, timeframe=tf)
    elif code == PATTERN_VCP:
        worker = analyze_vcp
    else:
        raise ValueError(f"Unknown pattern_code: {pattern_code}")

    listings = _listing_rows(universe)
    if limit is not None and limit > 0:
        listings = listings[:limit]
    if not listings:
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

    jobs = [(ticker, market) for ticker, market in listings]
    results = _run_parallel_scan(
        jobs,
        worker,
        workers=_tq_workers(max_workers, len(jobs)),
        progress_callback=progress_callback,
        should_stop=should_stop,
        accept_result=lambda res: res is not None and bool(res.get("pattern")),
    )

    df = _enrich_results(results, meta)
    if df.empty:
        return df

    df["_sig"] = df["signal"].map(lambda x: 0 if x == "BREAKOUT" else 1)
    df = df.sort_values(
        ["_sig", "score", "ticker"], ascending=[True, False, True], kind="mergesort"
    )
    return df.drop(columns=["_sig"]).reset_index(drop=True)


def run_cup_handle_scan(
    universe: pd.DataFrame,
    *,
    timeframe: str = "weekly",
    **kwargs,
) -> pd.DataFrame:
    return run_pattern_scan(
        universe,
        pattern_code=PATTERN_CUP_HANDLE,
        timeframe=timeframe,
        **kwargs,
    )


def run_vcp_scan(
    universe: pd.DataFrame,
    **kwargs,
) -> pd.DataFrame:
    return run_pattern_scan(universe, pattern_code=PATTERN_VCP, timeframe="daily", **kwargs)


def run_cup_vcp_scan(
    universe: pd.DataFrame,
    **kwargs,
) -> pd.DataFrame:
    """Legacy: runs cup & handle only (use separate scans for VCP)."""
    return run_cup_handle_scan(universe, **kwargs)


prepare_cup_vcp_universe = prepare_strategy_universe
prepare_cup_handle_universe = prepare_strategy_universe
prepare_vcp_universe = prepare_strategy_universe

__all__ = [
    "PATTERN_CUP_HANDLE",
    "PATTERN_VCP",
    "analyze_cup_handle",
    "analyze_cup_vcp",
    "analyze_vcp",
    "prepare_cup_handle_universe",
    "prepare_cup_vcp_universe",
    "prepare_vcp_universe",
    "run_cup_handle_scan",
    "run_cup_vcp_scan",
    "run_pattern_scan",
    "run_vcp_scan",
    "run_tq_worker_count",
]
