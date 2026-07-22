"""Quarterly panel + price snapshot for TQ / BB expand rows."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from stocks.core.config import STRATEGY_MAX_WORKERS_CAP
from stocks.core.text_utils import safe_str
from stocks.strategies.pead2.expand_data import fetch_pead_expand_data


def fetch_ticker_detail(
    ticker: str,
    market: str | None,
    *,
    price: float | None = None,
) -> dict | None:
    """Quarters + screener-style snapshot (same fetch path as PEAD expand)."""
    return fetch_pead_expand_data(ticker, market, price=price)


def enrich_strategy_dataframe(
    df: pd.DataFrame,
    *,
    max_workers: int | None = None,
) -> pd.DataFrame:
    """Attach snapshot + quarterly panel per strategy signal row."""
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()

    out = df.copy()
    workers = min(max_workers or 16, STRATEGY_MAX_WORKERS_CAP, len(out))
    details: dict[str, dict | None] = {}

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {}
        for _, row in out.iterrows():
            ticker = safe_str(row.get("ticker"))
            if not ticker:
                continue
            price = row.get("price")
            px = float(price) if price is not None and not pd.isna(price) else None
            futures[
                pool.submit(
                    fetch_ticker_detail,
                    ticker,
                    safe_str(row.get("market")) or None,
                    price=px,
                )
            ] = ticker.upper()

        for fut in as_completed(futures):
            key = futures[fut]
            try:
                details[key] = fut.result()
            except Exception:
                details[key] = None

    quarters_col: list[dict | None] = []
    snapshot_col: list[dict | None] = []
    for _, row in out.iterrows():
        key = safe_str(row.get("ticker")).upper()
        detail = details.get(key) or {}
        quarters_col.append(detail.get("quarters"))
        snapshot_col.append(detail.get("snapshot"))

    out["quarters"] = quarters_col
    out["snapshot"] = snapshot_col
    return out
