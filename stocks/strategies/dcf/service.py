"""DCF scan — yfinance FCF + two-stage discount model."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import yfinance as yf

from stocks.core.config import (
    DCF_DISCOUNT_RATE,
    DCF_FORECAST_YEARS,
    DCF_MAX_WORKERS,
    DCF_TERMINAL_GROWTH,
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
from stocks.strategies.dcf.strategy import compute_dcf_metrics, score_dcf
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


def analyze_dcf_stock(
    ticker: str,
    market: str | None,
    *,
    min_mcap_cr: float | None = None,
    known_mcap_cr: float | None = None,
    discount_rate: float | None = None,
    forecast_years: int | None = None,
    growth_pct: float | None = None,
    terminal_growth: float | None = None,
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

        metrics = compute_dcf_metrics(
            info,
            yt.cashflow,
            price=price,
            discount_rate=discount_rate,
            forecast_years=forecast_years,
            growth_pct=growth_pct,
            terminal_growth=terminal_growth,
        )
        if not metrics or metrics.get("fair_price") is None:
            return None
        # Drop schedule from scan payload (large).
        metrics.pop("schedule", None)

        return {
            "ticker": safe_str(ticker).upper(),
            "market": safe_str(market) or None,
            "name": safe_str(info.get("longName") or info.get("shortName")),
            "price": round(price, 2),
            "market_cap_cr": market_cap_cr,
            "website": safe_str(info.get("website")) or None,
            **metrics,
        }

    def _log(exc: Exception) -> None:
        log_error(
            METRICS_ERROR,
            "DCF fetch failed",
            ticker=ticker,
            symbol=symbol,
            error=str(exc),
        )

    return call_throttled(_fetch, delay=YFINANCE_REQUEST_DELAY, on_error=_log)


def run_dcf_scan(
    universe: pd.DataFrame,
    *,
    max_workers: int | None = None,
    min_mcap_cr: float | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    discount_rate: float | None = None,
    forecast_years: int | None = None,
    growth_pct: float | None = None,
    terminal_growth: float | None = None,
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
    workers = max_workers or yfinance_worker_count(len(universe), DCF_MAX_WORKERS)
    r = DCF_DISCOUNT_RATE if discount_rate is None else float(discount_rate)
    n = DCF_FORECAST_YEARS if forecast_years is None else int(forecast_years)
    g_term = DCF_TERMINAL_GROWTH if terminal_growth is None else float(terminal_growth)

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
                    analyze_dcf_stock,
                    safe_str(src.get("ticker")),
                    market,
                    min_mcap_cr=mcap_floor,
                    known_mcap_cr=known_mcap,
                    discount_rate=r,
                    forecast_years=n,
                    growth_pct=growth_pct,
                    terminal_growth=g_term,
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
    candidates = score_dcf(raw) if not raw.empty else pd.DataFrame()
    if not candidates.empty:
        candidates = attach_research_links(candidates)

    return {
        "candidates": candidates,
        "raw": raw,
        "scanned": scanned_total,
        "with_data": len(raw),
        "fetched": fetched,
    }


__all__ = [
    "analyze_dcf_stock",
    "prepare_pead_universe",
    "run_dcf_scan",
]
