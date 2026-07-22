"""Quarterly panel + price snapshot (MAs) for PEAD-style expand panels — Holdings, etc."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import yfinance as yf

from stocks.core.config import PEAD2_CACHE_HOURS, YFINANCE_REQUEST_DELAY, yfinance_worker_count
from stocks.core.database import load_pead2_cache
from stocks.core.log_service import METRICS_ERROR, log_error
from stocks.core.text_utils import safe_str
from stocks.market.company_profile import merge_company_profile
from stocks.market.price_service import to_yfinance_symbol
from stocks.market.yfinance_limits import call_throttled
from stocks.strategies.earnings.strategy import EPS_FIELDS, NET_INCOME_FIELDS
from stocks.strategies.pead2.quarters import build_quarter_panel, sanitize_quarter_panel
from stocks.strategies.pead2.service import (
    REVENUE_FIELDS,
    _info_price,
    _normalize_cache_blob,
    _pead2_ebidt_series,
    _safe_yf_info,
    _series_from_income,
)
from stocks.strategies.pead2.strategy import (
    compute_forward_pe,
    compute_trailing_pe,
    trim_reported_quarters,
)
from stocks.strategies.pead2.technicals import build_price_snapshot


def expand_from_lag_row(lag_row: dict | None) -> dict:
    """Extract expand-panel fields from a PEAD lag-0 row."""
    if not isinstance(lag_row, dict):
        return {}
    out: dict = {}
    for key in (
        "quarters",
        "snapshot",
        "pe_ratio",
        "forward_pe",
        "sales_yoy",
        "np_yoy",
        "eps_yoy",
        "cf_profit",
    ):
        val = lag_row.get(key)
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            out[key] = val
    return out


def _expand_from_cache(ticker: str, *, cache_hours: int) -> dict | None:
    key = safe_str(ticker).upper()
    if not key:
        return None
    blob = load_pead2_cache([key], max_hours=cache_hours).get(key)
    if not blob:
        return None
    norm = _normalize_cache_blob(blob)
    lag0 = (norm.get("lags") or {}).get("0")
    if not isinstance(lag0, dict):
        return None
    payload = expand_from_lag_row(lag0)
    if payload.get("quarters") or payload.get("snapshot"):
        return payload
    return None


def fetch_pead_expand_data(
    ticker: str,
    market: str | None,
    *,
    price: float | None = None,
    cache_hours: int | None = None,
) -> dict | None:
    """
    Quarterly panel + price snapshot (SMA/EMA, 52w) for expand panels.

    Uses PEAD2 cache when fresh; otherwise a lightweight Yahoo fetch (no PEAD score gates).
    """
    ticker_key = safe_str(ticker).upper()
    if not ticker_key:
        return None
    hours = PEAD2_CACHE_HOURS if cache_hours is None else int(cache_hours)
    cached = _expand_from_cache(ticker_key, cache_hours=hours)
    if cached:
        return cached

    symbol = to_yfinance_symbol(ticker_key, market)

    def _fetch() -> dict | None:
        yt = yf.Ticker(symbol)
        info = _safe_yf_info(yt)
        income = yt.quarterly_income_stmt
        hist = yt.history(period="6y", interval="1d", auto_adjust=True)
        revenue = trim_reported_quarters(_series_from_income(income, REVENUE_FIELDS))

        if revenue is None or revenue.empty:
            return None

        def _align(base: pd.Series | None) -> pd.Series:
            if base is not None and not base.empty:
                return base.reindex(revenue.index)
            return pd.Series(index=revenue.index, dtype=float)

        ebidt = _align(trim_reported_quarters(_pead2_ebidt_series(income)))
        net_profit = _align(trim_reported_quarters(_series_from_income(income, NET_INCOME_FIELDS)))
        eps = _align(trim_reported_quarters(_series_from_income(income, EPS_FIELDS)))
        price_val = price if price is not None else _info_price(info, hist)

        quarters = sanitize_quarter_panel(
            build_quarter_panel(revenue, ebidt, net_profit, eps)
        )

        pe_ratio = compute_trailing_pe(price_val, eps, info)
        forward_pe = compute_forward_pe(price_val, eps, info)

        snapshot = None
        if price_val is not None:
            snapshot = build_price_snapshot(
                info,
                hist,
                revenue,
                price=price_val,
                pe_ratio=pe_ratio,
                forward_pe=forward_pe,
            )
            if snapshot:
                snapshot = merge_company_profile(
                    snapshot,
                    ticker=ticker_key,
                    market=market,
                )

        if not quarters and not snapshot:
            return None

        out: dict = {}
        if quarters:
            out["quarters"] = quarters
        if snapshot:
            out["snapshot"] = snapshot
        if pe_ratio is not None:
            out["pe_ratio"] = pe_ratio
        if forward_pe is not None:
            out["forward_pe"] = forward_pe
        return out or None

    def _log(exc: Exception) -> None:
        log_error(
            METRICS_ERROR,
            "Holdings PEAD expand fetch failed",
            ticker=ticker_key,
            symbol=symbol,
            error=str(exc),
        )

    return call_throttled(_fetch, delay=YFINANCE_REQUEST_DELAY, on_error=_log)


def attach_pead_expand(
    df: pd.DataFrame,
    *,
    max_workers: int | None = None,
    cache_hours: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> pd.DataFrame:
    """Merge ``quarters`` + ``snapshot`` (MAs) onto each holdings row."""
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()

    out = df.copy()
    tickers = out["ticker"].astype(str).str.upper().tolist()
    cache_map = load_pead2_cache(tickers, max_hours=PEAD2_CACHE_HOURS if cache_hours is None else cache_hours)

    jobs: list[tuple[int, str, str | None, float | None]] = []
    prefilled: dict[int, dict] = {}
    for idx, row in out.iterrows():
        ticker = safe_str(row.get("ticker")).upper()
        market = safe_str(row.get("market")) or None
        price_raw = row.get("price")
        if price_raw is None or (isinstance(price_raw, float) and pd.isna(price_raw)):
            price_raw = row.get("current_price")
        price_f = (
            float(price_raw)
            if price_raw is not None and not pd.isna(price_raw)
            else None
        )
        blob = cache_map.get(ticker)
        if blob:
            norm = _normalize_cache_blob(blob)
            lag0 = (norm.get("lags") or {}).get("0")
            payload = expand_from_lag_row(lag0 if isinstance(lag0, dict) else None)
            if payload.get("quarters") or payload.get("snapshot"):
                prefilled[idx] = payload
                continue
        jobs.append((idx, ticker, market, price_f))

    workers = max_workers or yfinance_worker_count(len(jobs), 4)
    fetched: dict[int, dict] = {}
    total = len(jobs)
    done = 0

    if jobs:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    fetch_pead_expand_data,
                    ticker,
                    market,
                    price=price,
                    cache_hours=0 if cache_hours is None else cache_hours,
                ): idx
                for idx, ticker, market, price in jobs
            }
            for fut in as_completed(futures):
                done += 1
                if progress_callback:
                    progress_callback(done, total)
                idx = futures[fut]
                try:
                    payload = fut.result()
                except Exception:
                    continue
                if payload:
                    fetched[idx] = payload

    for idx, payload in {**prefilled, **fetched}.items():
        for key, val in payload.items():
            if key not in out.columns:
                out[key] = None
            out.at[idx, key] = val

    return out
