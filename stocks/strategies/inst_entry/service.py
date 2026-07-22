"""Inst Entry scan — quant gates via yfinance + shareholding trigger."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import yfinance as yf

from stocks.core.config import (
    INST_ENTRY_FETCH_NSE,
    INST_ENTRY_FETCH_SCREENER,
    INST_ENTRY_MAX_WORKERS,
    INST_ENTRY_MCAP_MAX_CR,
    INST_ENTRY_MCAP_MIN_CR,
    INST_ENTRY_MIN_DII_FII_DELTA,
    INST_ENTRY_REQUIRE_SIGNAL,
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
    institutional_entry_signal,
)
from stocks.market.yfinance_limits import call_throttled
from stocks.shared.links import attach_research_links
from stocks.strategies.inst_entry.strategy import (
    compute_inst_entry_metrics,
    in_inst_entry_mcap_band,
    score_inst_entry,
)
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


def prepare_inst_entry_universe(
    stocks: pd.DataFrame,
    *,
    cap_tier_id: str = "inst_entry",
) -> tuple[pd.DataFrame, int, int]:
    init_db()
    import_shareholding_seed_csv()
    tier = cap_tier_id if cap_tier_id not in ("", None, "all") else "inst_entry"
    universe, cap_ex, missing = prepare_pead_universe(stocks, cap_tier_id=tier)
    if universe.empty:
        return universe, cap_ex, missing
    universe = attach_market_cap_for_scan_filter(universe)
    if "market_cap_cr" in universe.columns:
        lo, hi = INST_ENTRY_MCAP_MIN_CR, INST_ENTRY_MCAP_MAX_CR
        cap = pd.to_numeric(universe["market_cap_cr"], errors="coerce")
        known = cap.notna() & (cap >= lo) & (cap <= hi)
        unknown = cap.isna()
        universe = universe[known | unknown].copy()
    return universe.reset_index(drop=True), cap_ex, missing


def analyze_inst_entry_stock(
    ticker: str,
    market: str | None,
    *,
    known_mcap_cr: float | None = None,
    fetch_nse: bool = INST_ENTRY_FETCH_NSE,
    fetch_screener: bool = INST_ENTRY_FETCH_SCREENER,
) -> dict | None:
    symbol = to_yfinance_symbol(ticker, market)
    if known_mcap_cr is not None and not in_inst_entry_mcap_band(known_mcap_cr):
        return None

    def _fetch() -> dict | None:
        yt = yf.Ticker(symbol)
        info = yt.info or {}
        market_cap_cr = known_mcap_cr
        if market_cap_cr is None:
            market_cap_cr = _cache_market_cap(ticker, market, symbol, info)
        if not in_inst_entry_mcap_band(market_cap_cr):
            return None

        price_raw = info.get("regularMarketPrice") or info.get("currentPrice")
        if price_raw is None or pd.isna(price_raw):
            return None
        price = float(price_raw)

        metrics = compute_inst_entry_metrics(
            info, yt.financials, market_cap_cr=market_cap_cr
        )
        ensure_shareholding_for_ticker(
            ticker,
            market,
            fetch_nse=fetch_nse,
            fetch_screener=fetch_screener,
        )
        signal = institutional_entry_signal(
            ticker, min_delta=INST_ENTRY_MIN_DII_FII_DELTA
        )

        row = {
            "ticker": safe_str(ticker).upper(),
            "market": safe_str(market) or None,
            "name": safe_str(info.get("longName") or info.get("shortName")),
            "price": round(price, 2),
            "market_cap_cr": market_cap_cr,
            "website": safe_str(info.get("website")) or None,
            **metrics,
        }
        if signal:
            row.update(signal)
        else:
            row.update(
                {
                    "quarter_end": None,
                    "institutional_pct_now": None,
                    "institutional_pct_prior": None,
                    "institutional_pct_delta": None,
                    "first_time_entry": False,
                }
            )
        return row

    def _log(exc: Exception) -> None:
        log_error(
            METRICS_ERROR,
            "Inst Entry fetch failed",
            ticker=ticker,
            symbol=symbol,
            error=str(exc),
        )

    return call_throttled(_fetch, delay=YFINANCE_REQUEST_DELAY, on_error=_log)


def run_inst_entry_scan(
    universe: pd.DataFrame,
    *,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    require_signal: bool | None = None,
    fetch_nse: bool = INST_ENTRY_FETCH_NSE,
    fetch_screener: bool = INST_ENTRY_FETCH_SCREENER,
) -> dict:
    if universe is None or universe.empty:
        return {
            "candidates": pd.DataFrame(),
            "watchlist": pd.DataFrame(),
            "scanned": 0,
            "with_data": 0,
            "fetched": 0,
        }

    require = INST_ENTRY_REQUIRE_SIGNAL if require_signal is None else require_signal
    scanned_total = len(universe)
    workers = max_workers or yfinance_worker_count(
        len(universe), INST_ENTRY_MAX_WORKERS
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
        if known_mcap_f is not None and not in_inst_entry_mcap_band(known_mcap_f):
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
                    analyze_inst_entry_stock,
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
    # Quant-only watchlist (no inst requirement).
    watchlist = score_inst_entry(raw, require_signal=False) if not raw.empty else pd.DataFrame()
    candidates = (
        score_inst_entry(raw, require_signal=require) if not raw.empty else pd.DataFrame()
    )
    if not candidates.empty:
        candidates = attach_research_links(candidates)
    if not watchlist.empty:
        watchlist = attach_research_links(watchlist)

    return {
        "candidates": candidates,
        "watchlist": watchlist,
        "raw": raw,
        "scanned": scanned_total,
        "with_data": len(raw),
        "fetched": fetched,
    }


__all__ = [
    "analyze_inst_entry_stock",
    "prepare_inst_entry_universe",
    "run_inst_entry_scan",
]
