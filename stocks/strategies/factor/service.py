"""Factor investing Quant scan — momentum only, full ranked list."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from stocks.core.text_utils import safe_str
from stocks.strategies.factor.detect import (
    HISTORY_INTERVAL,
    HISTORY_PERIOD,
    analyze_factor_stock,
    attach_factor_scores,
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

# 1.0 = keep every name with valid momentum (UI shows full ranked list).
KEEP_TOP_FRAC = 1.0


def analyze_factor(ticker: str, market: str | None = None) -> dict | None:
    if is_skippable_symbol(ticker):
        return None
    data = _fetch_history(
        ticker, market, period=HISTORY_PERIOD, interval=HISTORY_INTERVAL
    )
    # Drop only when Yahoo has no usable bars (keep short-history names with price).
    if data is None or data.empty or "Close" not in data.columns:
        return None
    return analyze_factor_stock(ticker, market, data)


def run_factor_scan(
    universe: pd.DataFrame,
    *,
    limit: int | None = None,
    max_workers: int | None = None,
    progress_callback=None,
    should_stop: Callable[[], bool] | None = None,
    keep_top_frac: float = KEEP_TOP_FRAC,
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
        analyze_factor,
        workers=_tq_workers(max_workers, len(jobs)),
        progress_callback=progress_callback,
        should_stop=should_stop,
        accept_result=lambda res: res is not None and res.get("price") is not None,
    )

    df = _enrich_results(results, meta)
    if df.empty:
        return df

    df = attach_factor_scores(df)
    df = df.sort_values(
        ["momentum_pct", "ticker"],
        ascending=[False, True],
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)
    frac = max(0.0, min(1.0, float(keep_top_frac)))
    if frac < 1.0:
        keep_n = max(1, int(round(len(df) * frac)))
        out = df.head(keep_n).copy()
    else:
        out = df.copy()
    out["factor_rank"] = range(1, len(out) + 1)
    return out.reset_index(drop=True)


prepare_factor_universe = prepare_strategy_universe

__all__ = [
    "analyze_factor",
    "prepare_factor_universe",
    "run_factor_scan",
    "run_tq_worker_count",
]
