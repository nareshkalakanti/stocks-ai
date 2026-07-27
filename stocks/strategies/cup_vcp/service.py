"""Cup & Handle and VCP daily pattern scanners."""

from __future__ import annotations

from collections.abc import Callable

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

HISTORY_PERIOD = "1y"
HISTORY_INTERVAL = "1d"
MIN_BARS = 60

PATTERN_CUP_HANDLE = "CUP_HANDLE"
PATTERN_VCP = "VCP"


def _analyze(
    ticker: str,
    market: str | None,
    *,
    pattern_code: str,
) -> dict | None:
    if is_skippable_symbol(ticker):
        return None
    data = _fetch_history(
        ticker, market, period=HISTORY_PERIOD, interval=HISTORY_INTERVAL
    )
    if data is None or len(data) < MIN_BARS:
        return None
    return analyze_ticker_patterns(
        ticker, market, data, pattern_code=pattern_code
    )


def analyze_cup_handle(ticker: str, market: str | None = None) -> dict | None:
    return _analyze(ticker, market, pattern_code=PATTERN_CUP_HANDLE)


def analyze_vcp(ticker: str, market: str | None = None) -> dict | None:
    return _analyze(ticker, market, pattern_code=PATTERN_VCP)


def analyze_cup_vcp(ticker: str, market: str | None = None) -> dict | None:
    """Best cup or VCP hit (legacy)."""
    if is_skippable_symbol(ticker):
        return None
    data = _fetch_history(
        ticker, market, period=HISTORY_PERIOD, interval=HISTORY_INTERVAL
    )
    if data is None or len(data) < MIN_BARS:
        return None
    return analyze_ticker_patterns(ticker, market, data)


def run_pattern_scan(
    universe: pd.DataFrame,
    *,
    pattern_code: str,
    limit: int | None = None,
    max_workers: int | None = None,
    progress_callback=None,
    should_stop: Callable[[], bool] | None = None,
) -> pd.DataFrame:
    code = safe_str(pattern_code).upper()
    if code == PATTERN_CUP_HANDLE:
        worker = analyze_cup_handle
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
    **kwargs,
) -> pd.DataFrame:
    return run_pattern_scan(universe, pattern_code=PATTERN_CUP_HANDLE, **kwargs)


def run_vcp_scan(
    universe: pd.DataFrame,
    **kwargs,
) -> pd.DataFrame:
    return run_pattern_scan(universe, pattern_code=PATTERN_VCP, **kwargs)


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
