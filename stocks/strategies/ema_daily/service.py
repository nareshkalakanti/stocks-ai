"""Daily above-all-EMAs scan."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from stocks.core.text_utils import safe_str
from stocks.strategies.ema_daily.strategy import (
    EMA_HISTORY_PERIOD,
    EMA_INTERVAL,
    analyze_ema_daily,
)
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


def analyze_ema_daily_stock(ticker: str, market: str | None = None) -> dict | None:
    if is_skippable_symbol(ticker):
        return None
    hist = _fetch_history(
        ticker,
        market,
        period=EMA_HISTORY_PERIOD,
        interval=EMA_INTERVAL,
    )
    return analyze_ema_daily(ticker, market, hist=hist)


def run_ema_daily_scan(
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
        analyze_ema_daily_stock,
        workers=_tq_workers(max_workers, len(jobs)),
        progress_callback=progress_callback,
        should_stop=should_stop,
        accept_result=lambda res: res is not None and res.get("above_all_emas") is True,
    )

    df = _enrich_results(results, meta)
    if df.empty:
        return df

    return df.sort_values(["ema_stretch_pct"], ascending=[False]).reset_index(drop=True)


prepare_ema_daily_universe = prepare_strategy_universe

__all__ = [
    "analyze_ema_daily_stock",
    "prepare_ema_daily_universe",
    "run_ema_daily_scan",
    "run_tq_worker_count",
]
