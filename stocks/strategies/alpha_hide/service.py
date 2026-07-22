"""Alpha Hide scan — SARVADA phases + ingredient gates via yfinance."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

import pandas as pd
import yfinance as yf

from stocks.core.config import (
    ALPHA_HIDE_FETCH_NSE,
    ALPHA_HIDE_FETCH_SCREENER,
    ALPHA_HIDE_MAX_WORKERS,
    ALPHA_HIDE_MCAP_MAX_CR,
    ALPHA_HIDE_MCAP_MIN_CR,
    YFINANCE_REQUEST_DELAY,
    yfinance_worker_count,
)
from stocks.core.database import init_db, save_market_cap_to_db
from stocks.core.log_service import METRICS_ERROR, log_error
from stocks.core.text_utils import resolve_company_name, safe_str
from stocks.market.fundamentals_service import attach_market_cap_for_scan_filter
from stocks.market.price_service import to_yfinance_symbol
from stocks.market.shareholding import (
    ensure_shareholding_for_ticker,
    import_shareholding_seed_csv,
    shareholding_deltas,
)
from stocks.market.yfinance_limits import call_throttled
from stocks.shared.links import attach_research_links
from stocks.strategies.alpha_hide.strategy import (
    compute_alpha_hide_metrics,
    in_alpha_hide_universe,
    score_alpha_hide,
)
from stocks.strategies.pead.service import prepare_pead_universe


@lru_cache(maxsize=1)
def _demerger_tickers() -> frozenset[str]:
    try:
        from stocks.shared.corp_tags import spinoffs_ticker_set

        return spinoffs_ticker_set()
    except Exception:
        return frozenset()


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


def prepare_alpha_hide_universe(
    stocks: pd.DataFrame,
    *,
    cap_tier_id: str = "alpha_hide",
) -> tuple[pd.DataFrame, int, int]:
    init_db()
    import_shareholding_seed_csv()
    tier = cap_tier_id if cap_tier_id not in ("", None, "all") else "alpha_hide"
    universe, cap_ex, missing = prepare_pead_universe(stocks, cap_tier_id=tier)
    if universe.empty:
        return universe, cap_ex, missing
    universe = attach_market_cap_for_scan_filter(universe)
    if "market_cap_cr" in universe.columns:
        lo, hi = ALPHA_HIDE_MCAP_MIN_CR, ALPHA_HIDE_MCAP_MAX_CR
        cap = pd.to_numeric(universe["market_cap_cr"], errors="coerce")
        known = cap.notna() & (cap >= lo) & (cap <= hi)
        unknown = cap.isna()
        universe = universe[known | unknown].copy()
    return universe.reset_index(drop=True), cap_ex, missing


def analyze_alpha_hide_stock(
    ticker: str,
    market: str | None,
    *,
    known_mcap_cr: float | None = None,
    fetch_nse: bool = ALPHA_HIDE_FETCH_NSE,
    fetch_screener: bool = ALPHA_HIDE_FETCH_SCREENER,
) -> dict | None:
    symbol = to_yfinance_symbol(ticker, market)
    if known_mcap_cr is not None and not in_alpha_hide_universe(known_mcap_cr):
        return None

    def _fetch() -> dict | None:
        yt = yf.Ticker(symbol)
        info = yt.info or {}
        market_cap_cr = known_mcap_cr
        if market_cap_cr is None:
            market_cap_cr = _cache_market_cap(ticker, market, symbol, info)
        if not in_alpha_hide_universe(market_cap_cr):
            return None

        price_raw = info.get("regularMarketPrice") or info.get("currentPrice")
        if price_raw is None or pd.isna(price_raw):
            return None
        price = float(price_raw)

        metrics = compute_alpha_hide_metrics(
            info,
            yt.financials,
            market_cap_cr=market_cap_cr,
            price=price,
        )
        ensure_shareholding_for_ticker(
            ticker,
            market,
            fetch_nse=fetch_nse,
            fetch_screener=fetch_screener,
        )
        sh = shareholding_deltas(ticker)
        demerger = safe_str(ticker).upper() in _demerger_tickers()

        return {
            "ticker": safe_str(ticker).upper(),
            "market": safe_str(market) or None,
            "name": safe_str(info.get("longName") or info.get("shortName")),
            "price": round(price, 2),
            "market_cap_cr": market_cap_cr,
            "website": safe_str(info.get("website")) or None,
            "demerger_flag": demerger,
            **metrics,
            **sh,
        }

    def _log(exc: Exception) -> None:
        log_error(
            METRICS_ERROR,
            "Alpha Hide fetch failed",
            ticker=ticker,
            symbol=symbol,
            error=str(exc),
        )

    return call_throttled(_fetch, delay=YFINANCE_REQUEST_DELAY, on_error=_log)


def run_alpha_hide_scan(
    universe: pd.DataFrame,
    *,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    fetch_nse: bool = ALPHA_HIDE_FETCH_NSE,
    fetch_screener: bool = ALPHA_HIDE_FETCH_SCREENER,
) -> dict:
    if universe is None or universe.empty:
        return {
            "candidates": pd.DataFrame(),
            "scanned": 0,
            "with_data": 0,
            "fetched": 0,
        }

    scanned_total = len(universe)
    workers = max_workers or yfinance_worker_count(
        len(universe), ALPHA_HIDE_MAX_WORKERS
    )

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
        if known_mcap_f is not None and not in_alpha_hide_universe(known_mcap_f):
            continue
        jobs.append((src, safe_str(src.get("market")) or None, known_mcap_f))

    rows: list[dict] = []
    total_jobs = len(jobs)
    done = 0
    fetched = 0

    if jobs:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    analyze_alpha_hide_stock,
                    safe_str(src.get("ticker")),
                    market,
                    known_mcap_cr=known_mcap,
                    fetch_nse=fetch_nse,
                    fetch_screener=fetch_screener,
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
    scored = score_alpha_hide(raw) if not raw.empty else pd.DataFrame()
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
    "analyze_alpha_hide_stock",
    "prepare_alpha_hide_universe",
    "run_alpha_hide_scan",
]
