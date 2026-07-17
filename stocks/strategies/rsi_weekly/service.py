"""Weekly RSI strategy — entry when RSI crosses ≥60 (new cross replaces prior)."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from stocks.core.text_utils import safe_str
from stocks.market.indicators import calculate_rsi
from stocks.strategies.tq_bb.service import (
    _enrich_results,
    _listing_rows,
    _run_parallel_scan,
    _tq_workers,
    is_skippable_symbol,
    prepare_strategy_universe,
    run_tq_worker_count,
)

RSI_LENGTH = 14
RSI_ENTRY = 60.0
RSI_MIN_BARS = RSI_LENGTH + 5
# 1y weekly is enough for RSI(14); keeps Yahoo fetches light.
RSI_HISTORY_PERIOD = "1y"

SIGNAL_ENTRY = "RSI_ENTRY"


def latest_rsi_entry_cross(
    rsi: pd.Series,
    *,
    entry: float = RSI_ENTRY,
) -> dict | None:
    """Return state only when the latest bar crosses above ``entry``."""
    s = pd.to_numeric(rsi, errors="coerce").dropna()
    if len(s) < 2:
        return None

    prev = float(s.iloc[-2])
    cur = float(s.iloc[-1])
    if not (prev < entry <= cur):
        return None

    return {
        "rsi": round(cur, 2),
        "prev_rsi": round(prev, 2),
        "signal": SIGNAL_ENTRY,
        "just_entered": True,
    }


def analyze_rsi_weekly(
    ticker: str,
    market: str | None = None,
    *,
    rsi_length: int = RSI_LENGTH,
    rsi_entry: float = RSI_ENTRY,
) -> dict | None:
    if is_skippable_symbol(ticker):
        return None

    from stocks.strategies.tq_bb.service import _fetch_history

    data = _fetch_history(ticker, market, period=RSI_HISTORY_PERIOD, interval="1wk")
    if data is None or len(data) < max(RSI_MIN_BARS, rsi_length + 5):
        return None

    rsi = calculate_rsi(data, period=rsi_length)
    state = latest_rsi_entry_cross(rsi, entry=rsi_entry)
    if not state:
        return None

    latest = data.iloc[-1]
    price = float(latest["Close"])
    return {
        "ticker": safe_str(ticker).upper(),
        "market": safe_str(market) or None,
        "price": round(price, 2),
        "rsi": state["rsi"],
        "prev_rsi": state["prev_rsi"],
        "signal": state["signal"],
        "rsi_entry": rsi_entry,
        "date": latest.name.strftime("%Y-%m-%d"),
        "timeframe": "weekly",
        "score": state["rsi"],
    }


def run_rsi_weekly_scan(
    universe: pd.DataFrame,
    *,
    limit: int | None = None,
    max_workers: int | None = None,
    progress_callback=None,
    should_stop: Callable[[], bool] | None = None,
    rsi_length: int = RSI_LENGTH,
    rsi_entry: float = RSI_ENTRY,
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

    def _analyze(ticker: str, market: str | None) -> dict | None:
        return analyze_rsi_weekly(
            ticker,
            market,
            rsi_length=rsi_length,
            rsi_entry=rsi_entry,
        )

    jobs = [(ticker, market) for ticker, market in listings]
    results = _run_parallel_scan(
        jobs,
        _analyze,
        workers=_tq_workers(max_workers, len(jobs)),
        progress_callback=progress_callback,
        should_stop=should_stop,
        accept_result=lambda res: res is not None and res.get("signal") == SIGNAL_ENTRY,
    )

    df = _enrich_results(results, meta)
    if df.empty:
        return df

    return df.sort_values(["rsi"], ascending=[False]).reset_index(drop=True)


prepare_rsi_weekly_universe = prepare_strategy_universe

# Back-compat alias used by older tests
simulate_rsi_weekly_state = latest_rsi_entry_cross

__all__ = [
    "RSI_ENTRY",
    "RSI_LENGTH",
    "SIGNAL_ENTRY",
    "analyze_rsi_weekly",
    "latest_rsi_entry_cross",
    "prepare_rsi_weekly_universe",
    "run_rsi_weekly_scan",
    "run_tq_worker_count",
    "simulate_rsi_weekly_state",
]
