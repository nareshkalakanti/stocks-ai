"""Weekly base breakout scanner."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from stocks.core.text_utils import safe_str
from stocks.strategies.base_breakout.detect import analyze_ticker_base_breakout
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

HISTORY_PERIOD = "5y"
HISTORY_INTERVAL = "1wk"
MIN_BARS = 30


def analyze_base_breakout(ticker: str, market: str | None = None) -> dict | None:
    if is_skippable_symbol(ticker):
        return None
    data = _fetch_history(ticker, market, period=HISTORY_PERIOD, interval=HISTORY_INTERVAL)
    if data is None or len(data) < MIN_BARS:
        return None
    return analyze_ticker_base_breakout(ticker, market, data)


def run_base_breakout_scan(
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
        analyze_base_breakout,
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


prepare_base_breakout_universe = prepare_strategy_universe

__all__ = [
    "analyze_base_breakout",
    "prepare_base_breakout_universe",
    "run_base_breakout_scan",
    "run_tq_worker_count",
]
