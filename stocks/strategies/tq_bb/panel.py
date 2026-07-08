"""Quarterly panel + price snapshot for TQ / BB expand rows."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import yfinance as yf

from stocks.core.config import STRATEGY_MAX_WORKERS_CAP
from stocks.strategies.earnings.strategy import EBIDT_FIELDS, EPS_FIELDS
from stocks.core.log_service import METRICS_ERROR, log_error
from stocks.strategies.pead2.quarters import build_quarter_panel
from stocks.strategies.pead2.strategy import NET_INCOME_FIELDS
from stocks.strategies.pead2.service import REVENUE_FIELDS, _series_from_income
from stocks.strategies.pead2.technicals import build_price_snapshot
from stocks.market.price_service import to_yfinance_symbol
from stocks.core.text_utils import safe_str
from stocks.market.yfinance_limits import call_fast


def fetch_ticker_detail(
    ticker: str,
    market: str | None,
    *,
    price: float | None = None,
) -> dict | None:
    """Quarters + screener-style snapshot (price, mcap, PE, CAGR, MAs, 52w)."""
    symbol = to_yfinance_symbol(ticker, market)

    def _fetch() -> dict | None:
        yt = yf.Ticker(symbol)
        info = yt.info or {}
        hist = yt.history(period="2y", interval="1d")
        if hist is None or hist.empty:
            hist = pd.DataFrame()
        income = yt.quarterly_income_stmt
        revenue = _series_from_income(income, REVENUE_FIELDS)
        ebit = _series_from_income(income, EBIDT_FIELDS)
        net_profit = _series_from_income(income, NET_INCOME_FIELDS)
        eps = _series_from_income(income, EPS_FIELDS)
        detail: dict = {}
        quarters = build_quarter_panel(revenue, ebit, net_profit, eps)
        if quarters:
            detail["quarters"] = quarters
        px = price
        if px is None:
            raw = info.get("regularMarketPrice") or info.get("currentPrice")
            px = float(raw) if raw is not None and not pd.isna(raw) else None
        snapshot = build_price_snapshot(info, hist, revenue, price=px)
        if snapshot:
            detail["snapshot"] = snapshot
        return detail if detail else None

    def _log(exc: Exception) -> None:
        log_error(
            METRICS_ERROR,
            "Strategy detail fetch failed",
            ticker=ticker,
            symbol=symbol,
            error=str(exc),
        )

    return call_fast(_fetch, on_error=_log)


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
