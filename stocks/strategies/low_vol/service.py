"""Low volatility Quant scan — bottom-quintile short + long realized vol."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from stocks.core.text_utils import safe_str
from stocks.strategies.low_vol.detect import (
    HISTORY_INTERVAL,
    HISTORY_PERIOD,
    MIN_BARS,
    analyze_low_volatility,
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

# Keep lowest-vol quintile after ranking (matches Q1 vs Q5 slide style).
KEEP_BOTTOM_FRAC = 0.20


def analyze_low_vol(ticker: str, market: str | None = None) -> dict | None:
    if is_skippable_symbol(ticker):
        return None
    data = _fetch_history(
        ticker, market, period=HISTORY_PERIOD, interval=HISTORY_INTERVAL
    )
    if data is None or len(data) < MIN_BARS:
        return None
    return analyze_low_volatility(ticker, market, data)


def run_low_vol_scan(
    universe: pd.DataFrame,
    *,
    limit: int | None = None,
    max_workers: int | None = None,
    progress_callback=None,
    should_stop: Callable[[], bool] | None = None,
    keep_bottom_frac: float = KEEP_BOTTOM_FRAC,
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
        analyze_low_vol,
        workers=_tq_workers(max_workers, len(jobs)),
        progress_callback=progress_callback,
        should_stop=should_stop,
        accept_result=lambda res: res is not None and res.get("composite_vol") is not None,
    )

    df = _enrich_results(results, meta)
    if df.empty:
        return df

    df = df.sort_values(
        ["composite_vol", "ticker"], ascending=[True, True], kind="mergesort"
    ).reset_index(drop=True)
    frac = max(0.05, min(1.0, float(keep_bottom_frac)))
    keep_n = max(1, int(round(len(df) * frac)))
    out = df.head(keep_n).copy()
    out["vol_rank"] = range(1, len(out) + 1)
    return out.reset_index(drop=True)


prepare_low_vol_universe = prepare_strategy_universe

__all__ = [
    "analyze_low_vol",
    "prepare_low_vol_universe",
    "run_low_vol_scan",
    "run_tq_worker_count",
]
