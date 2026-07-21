"""Growth strategy scan — fetch annual metrics via yfinance."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import yfinance as yf

from stocks.core.config import (
    GROWTH_MAX_WORKERS,
    MIN_MARKET_CAP_CR,
    YFINANCE_REQUEST_DELAY,
    yfinance_worker_count,
)
from stocks.core.database import save_market_cap_to_db
from stocks.core.log_service import METRICS_ERROR, log_error
from stocks.core.text_utils import resolve_company_name, safe_str
from stocks.market.price_service import to_yfinance_symbol
from stocks.market.yfinance_limits import call_throttled
from stocks.shared.links import attach_research_links
from stocks.strategies.growth.strategy import compute_growth_metrics, score_growth
from stocks.strategies.pead.service import prepare_pead_universe


def _cache_market_cap(
    ticker: str,
    market: str | None,
    symbol: str,
    info: dict,
) -> float | None:
    market_cap = info.get("marketCap")
    if market_cap is None or (isinstance(market_cap, float) and pd.isna(market_cap)):
        return None
    market_cap_cr = round(float(market_cap) / 1e7, 1)
    price = info.get("regularMarketPrice") or info.get("currentPrice")
    price_val = float(price) if price is not None and not pd.isna(price) else None
    save_market_cap_to_db(
        ticker,
        market_cap_cr,
        market=market,
        yf_symbol=symbol,
        price=price_val,
    )
    return market_cap_cr


def _merge_listing_meta(result: dict, src: pd.Series) -> dict:
    ticker = safe_str(result.get("ticker") or src.get("ticker")).upper()
    result["name"] = resolve_company_name(
        src.get("name"),
        result.get("name"),
        ticker=ticker,
    )
    for field in ("sector", "industry", "sub_sector"):
        val = src.get(field)
        if val and not result.get(field):
            result[field] = safe_str(val)
    return result


def analyze_growth_stock(
    ticker: str,
    market: str | None,
    *,
    min_mcap_cr: float | None = None,
    known_mcap_cr: float | None = None,
) -> dict | None:
    symbol = to_yfinance_symbol(ticker, market)
    floor = MIN_MARKET_CAP_CR if min_mcap_cr is None else min_mcap_cr
    if known_mcap_cr is not None and known_mcap_cr < floor:
        return None

    def _fetch() -> dict | None:
        yt = yf.Ticker(symbol)
        info = yt.info or {}
        market_cap_cr = known_mcap_cr
        if market_cap_cr is None:
            market_cap_cr = _cache_market_cap(ticker, market, symbol, info)
        if market_cap_cr is not None and market_cap_cr < floor:
            return None

        price_raw = info.get("regularMarketPrice") or info.get("currentPrice")
        if price_raw is None or pd.isna(price_raw):
            return None
        price = float(price_raw)

        metrics = compute_growth_metrics(yt.financials, yt.balance_sheet, info)
        # Need at least one CAGR or margin signal to keep the row.
        if (
            metrics.get("sales_cagr") is None
            and metrics.get("profit_cagr") is None
            and metrics.get("roe") is None
            and metrics.get("operating_margin") is None
        ):
            return None

        return {
            "ticker": safe_str(ticker).upper(),
            "market": safe_str(market) or None,
            "name": safe_str(info.get("longName") or info.get("shortName")),
            "price": round(price, 2),
            "market_cap_cr": market_cap_cr,
            **metrics,
        }

    def _log(exc: Exception) -> None:
        log_error(
            METRICS_ERROR,
            "Growth strategy fetch failed",
            ticker=ticker,
            symbol=symbol,
            error=str(exc),
        )

    return call_throttled(_fetch, delay=YFINANCE_REQUEST_DELAY, on_error=_log)


def run_growth_scan(
    universe: pd.DataFrame,
    *,
    max_workers: int | None = None,
    min_mcap_cr: float | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict:
    if universe is None or universe.empty:
        return {
            "candidates": pd.DataFrame(),
            "scanned": 0,
            "with_data": 0,
            "fetched": 0,
        }

    scanned_total = len(universe)
    mcap_floor = MIN_MARKET_CAP_CR if min_mcap_cr is None else min_mcap_cr
    workers = max_workers or yfinance_worker_count(len(universe), GROWTH_MAX_WORKERS)

    jobs: list[tuple[pd.Series, str | None, float | None]] = []
    for _, src in universe.iterrows():
        ticker = safe_str(src.get("ticker")).upper()
        if not ticker:
            continue
        known_mcap = src.get("market_cap_cr")
        known_mcap_f = (
            float(known_mcap)
            if known_mcap is not None and not pd.isna(known_mcap)
            else None
        )
        jobs.append((src, safe_str(src.get("market")) or None, known_mcap_f))

    rows: list[dict] = []
    total_jobs = len(jobs)
    done = 0
    fetched = 0

    if jobs:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    analyze_growth_stock,
                    safe_str(src.get("ticker")),
                    market,
                    min_mcap_cr=mcap_floor,
                    known_mcap_cr=known_mcap,
                ): src
                for src, market, known_mcap in jobs
            }
            for fut in as_completed(futures):
                done += 1
                fetched += 1
                if progress_callback:
                    progress_callback(done, total_jobs)
                try:
                    result = fut.result()
                except Exception:
                    continue
                if result:
                    src = futures[fut]
                    _merge_listing_meta(result, src)
                    rows.append(result)

    raw = pd.DataFrame(rows) if rows else pd.DataFrame()
    scored = score_growth(raw) if not raw.empty else pd.DataFrame()
    if not scored.empty:
        scored = attach_research_links(scored)

    return {
        "candidates": scored,
        "raw": raw,
        "scanned": scanned_total,
        "with_data": len(raw),
        "fetched": fetched,
    }


__all__ = [
    "analyze_growth_stock",
    "prepare_pead_universe",
    "run_growth_scan",
]
