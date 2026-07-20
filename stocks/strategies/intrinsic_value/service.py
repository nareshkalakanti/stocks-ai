"""Intrinsic Value scan — fetch 3Y growth, ROCE, P/B and rank."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import yfinance as yf

from stocks.core.config import (
    HEADWIND_IV_CACHE_HOURS,
    INTRINSIC_VALUE_CACHE_HOURS,
    INTRINSIC_VALUE_MAX_WORKERS,
    MIN_MARKET_CAP_CR,
    YFINANCE_REQUEST_DELAY,
    yfinance_worker_count,
)
from stocks.core.database import load_market_cap_from_db, patch_intrinsic_value_pcf, save_market_cap_to_db
from stocks.core.log_service import METRICS_ERROR, log_error
from stocks.market.fundamentals_service import apply_market_cap_filter
from stocks.strategies.intrinsic_value.cache import (
    iv_row_from_cache,
    load_cached_iv_rows,
    persist_iv_rows,
)
from stocks.strategies.intrinsic_value.strategy import (
    pe_ratio_and_forward,
    price_to_book,
    price_to_cash_flow,
    rank_intrinsic_value,
    roce_3y_average,
    sales_growth_3y_cagr,
    sector_headwind_tailwind,
)
from stocks.strategies.pead.service import prepare_pead_universe
from stocks.market.price_service import to_yfinance_symbol
from stocks.shared.links import attach_research_links
from stocks.core.text_utils import resolve_company_name, safe_str
from stocks.market.yfinance_limits import call_throttled

_IV_PERSIST_BATCH = 25


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


def _fetch_mcap_cr_fast(ticker: str, market: str | None) -> float | None:
    symbol = to_yfinance_symbol(ticker, market)

    def _go() -> float | None:
        info = yf.Ticker(symbol).info or {}
        return _cache_market_cap(ticker, market, symbol, info)

    return call_throttled(_go, delay=YFINANCE_REQUEST_DELAY)


def filter_universe_by_db_mcap(
    universe: pd.DataFrame,
    *,
    min_cr: float,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """
    Keep only listings with fresh SQLite market_cap_cr >= min_cr.
    No yfinance calls — use for headwind pre-scan counts and universe shrink.
    """
    stats = {"total": 0, "cached": 0, "eligible": 0, "missing": 0, "below_floor": 0}
    if universe.empty:
        return universe, stats

    out = universe.copy()
    out["ticker"] = out["ticker"].astype(str).str.upper()
    stats["total"] = len(out)

    cached = load_market_cap_from_db(out["ticker"].tolist())
    if cached.empty:
        stats["missing"] = len(out)
        return out.iloc[0:0].copy(), stats

    caps = cached[["ticker", "market_cap_cr"]].drop_duplicates("ticker")
    merged = out.merge(caps, on="ticker", how="left")
    stats["cached"] = int(merged["market_cap_cr"].notna().sum())
    stats["missing"] = stats["total"] - stats["cached"]

    filtered, excluded = apply_market_cap_filter(merged, min_cr=min_cr)
    stats["eligible"] = len(filtered)
    stats["below_floor"] = int(excluded)
    return filtered.reset_index(drop=True), stats


def shrink_universe_by_mcap(
    universe: pd.DataFrame,
    *,
    min_cr: float,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> tuple[pd.DataFrame, int]:
    """
    Drop sub-floor listings using SQLite mcap cache + fast info-only fetch.
    Returns (filtered_universe, excluded_count).
    """
    if universe.empty:
        return universe, 0

    out = universe.copy()
    tickers = out["ticker"].astype(str).str.upper().tolist()
    markets = (
        out["market"].tolist() if "market" in out.columns else [None] * len(out)
    )

    cached = load_market_cap_from_db(tickers)
    if not cached.empty:
        out = out.drop(columns=["market_cap_cr"], errors="ignore").merge(
            cached[["ticker", "market_cap_cr"]].drop_duplicates("ticker"),
            on="ticker",
            how="left",
        )
    elif "market_cap_cr" not in out.columns:
        out["market_cap_cr"] = None

    need: list[tuple[str, str | None, int]] = []
    for idx, (ticker, market) in enumerate(zip(tickers, markets)):
        cap = out.iloc[idx].get("market_cap_cr")
        if cap is None or (isinstance(cap, float) and pd.isna(cap)):
            need.append((ticker, market, idx))

    if need:
        workers = yfinance_worker_count(len(need), max_workers)
        done = 0
        total = len(need)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_fetch_mcap_cr_fast, t, m): (t, m, idx)
                for t, m, idx in need
            }
            for fut in as_completed(futures):
                done += 1
                t, _m, idx = futures[fut]
                try:
                    cap = fut.result()
                except Exception:
                    cap = None
                if cap is not None:
                    out.at[out.index[idx], "market_cap_cr"] = cap
                if progress_callback:
                    progress_callback(done, total, "mcap")

    filtered, excluded = apply_market_cap_filter(out, min_cr=min_cr)
    return filtered, excluded


def drop_known_sub_floor(universe: pd.DataFrame, *, min_cr: float) -> pd.DataFrame:
    """Drop listings already in SQLite below the market-cap floor (no yfinance)."""
    if universe.empty:
        return universe
    tickers = universe["ticker"].astype(str).str.upper().tolist()
    cached = load_market_cap_from_db(tickers)
    if cached.empty:
        return universe
    caps = cached[["ticker", "market_cap_cr"]].drop_duplicates("ticker")
    merged = universe.copy()
    merged["ticker"] = merged["ticker"].astype(str).str.upper()
    merged = merged.merge(caps, on="ticker", how="left")
    keep = merged["market_cap_cr"].isna() | (merged["market_cap_cr"] >= min_cr)
    return merged.loc[keep].drop(columns=["market_cap_cr"], errors="ignore").reset_index(drop=True)


def analyze_intrinsic_value_stock(
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

        growth = sales_growth_3y_cagr(yt.financials)
        if growth is None:
            rg = info.get("revenueGrowth")
            if rg is not None and not pd.isna(rg):
                growth = round(float(rg) * 100, 2)

        roce = roce_3y_average(yt.financials, yt.balance_sheet)
        if roce is None:
            roe = info.get("returnOnEquity")
            if roe is not None and not pd.isna(roe):
                roce = round(float(roe) * 100, 2)

        pb = price_to_book(info, price=price)
        pe_ratio, forward_pe = pe_ratio_and_forward(
            price, info, yt.quarterly_income_stmt
        )
        pcf = price_to_cash_flow(info, price=price, cashflow=yt.cashflow)
        if growth is None or roce is None or pb is None:
            return None

        return {
            "ticker": safe_str(ticker).upper(),
            "market": safe_str(market) or None,
            "name": safe_str(info.get("longName") or info.get("shortName")),
            "price": round(price, 2),
            "market_cap_cr": market_cap_cr,
            "sales_growth_3y": growth,
            "roce_3y": roce,
            "pb": pb,
            "pe_ratio": pe_ratio,
            "forward_pe": forward_pe,
            "pcf": pcf,
        }

    def _log(exc: Exception) -> None:
        log_error(
            METRICS_ERROR,
            "Intrinsic Value fetch failed",
            ticker=ticker,
            symbol=symbol,
            error=str(exc),
        )

    return call_throttled(_fetch, delay=YFINANCE_REQUEST_DELAY, on_error=_log)


def resolve_scan_group_col(
    ranked: pd.DataFrame,
    *,
    min_coverage: float = 0.5,
    min_tagged: int = 20,
    force_display_sector: bool = False,
) -> str:
    """Pick sector-board grouping column — avoid sparse industry tags (holdings-only)."""
    if ranked is None or ranked.empty:
        return "sector"
    if force_display_sector and "sector" in ranked.columns:
        return "sector"
    n = len(ranked)
    for col in ("sub_sector", "industry"):
        if col not in ranked.columns:
            continue
        tagged = int(ranked[col].astype(str).str.strip().ne("").sum())
        if tagged >= min_tagged and tagged / n >= min_coverage:
            return col
    return "sector" if "sector" in ranked.columns else "industry"


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


def fetch_stock_pcf(
    ticker: str,
    market: str | None,
    *,
    price: float | None = None,
) -> float | None:
    """Lightweight yfinance fetch for price ÷ operating cash flow per share."""
    symbol = to_yfinance_symbol(ticker, market)

    def _fetch() -> float | None:
        yt = yf.Ticker(symbol)
        info = yt.info or {}
        px = price
        if px is None:
            raw = info.get("regularMarketPrice") or info.get("currentPrice")
            px = float(raw) if raw is not None and not pd.isna(raw) else None
        return price_to_cash_flow(info, price=px, cashflow=yt.cashflow)

    try:
        return call_throttled(_fetch, delay=YFINANCE_REQUEST_DELAY)
    except Exception:
        return None


def ensure_pcf_values(
    frame: pd.DataFrame,
    *,
    max_hours: int,
    fetch_missing: bool = False,
    max_workers: int | None = None,
) -> pd.DataFrame:
    """Fill missing P/CF from IV cache, optionally backfill via yfinance."""
    if frame is None or frame.empty or "ticker" not in frame.columns:
        return frame if frame is not None else pd.DataFrame()

    out = frame.copy()
    if "pcf" not in out.columns:
        out["pcf"] = pd.NA
    out["pcf"] = pd.to_numeric(out["pcf"], errors="coerce")

    missing = out["pcf"].isna()
    if not missing.any():
        return out

    tickers = (
        out.loc[missing, "ticker"].astype(str).str.strip().str.upper().unique().tolist()
    )
    cached = load_cached_iv_rows(tickers, max_hours=max_hours)
    if not cached.empty and "pcf" in cached.columns:
        by_ticker = cached.copy()
        by_ticker["ticker"] = by_ticker["ticker"].astype(str).str.upper()
        by_ticker = by_ticker.drop_duplicates("ticker").set_index("ticker")
        keys = out["ticker"].astype(str).str.strip().str.upper()
        mapped = keys.map(by_ticker["pcf"])
        fill = missing & mapped.notna()
        if fill.any():
            out.loc[fill, "pcf"] = mapped.loc[fill].to_numpy(dtype=float, na_value=np.nan)
        missing = out["pcf"].isna()

    if not fetch_missing or not missing.any():
        return out

    workers = max_workers or yfinance_worker_count(int(missing.sum()), 8)
    jobs: list[tuple[int, str, str | None, float | None]] = []
    for idx, row in out.loc[missing].iterrows():
        ticker = safe_str(row.get("ticker")).upper()
        if not ticker:
            continue
        market = safe_str(row.get("market")) or None
        price = row.get("price")
        price_f = float(price) if price is not None and not pd.isna(price) else None
        jobs.append((idx, ticker, market, price_f))

    updates: dict[str, float] = {}
    if jobs:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(fetch_stock_pcf, ticker, market, price=price): (idx, ticker)
                for idx, ticker, market, price in jobs
            }
            for fut in as_completed(futures):
                idx, ticker = futures[fut]
                try:
                    pcf = fut.result()
                except Exception:
                    pcf = None
                if pcf is None or pd.isna(pcf):
                    continue
                out.at[idx, "pcf"] = float(pcf)
                updates[ticker] = float(pcf)

    if updates:
        patch_intrinsic_value_pcf(updates)

    return out


def _finalize_intrinsic_value_scan(
    rows: list[dict],
    *,
    scanned_total: int,
    min_sector_companies: int,
) -> dict:
    if not rows:
        return {
            "ranked": pd.DataFrame(),
            "sectors": pd.DataFrame(),
            "scanned": scanned_total,
            "with_data": 0,
        }

    raw = pd.DataFrame(rows)
    ranked = rank_intrinsic_value(raw)
    if ranked.empty:
        return {
            "ranked": ranked,
            "sectors": pd.DataFrame(),
            "scanned": scanned_total,
            "with_data": len(raw),
        }

    industry_col = resolve_scan_group_col(ranked, force_display_sector=True)

    sectors = sector_headwind_tailwind(
        ranked, industry_col=industry_col, min_companies=min_sector_companies
    )
    ranked = ensure_pcf_values(
        ranked,
        max_hours=INTRINSIC_VALUE_CACHE_HOURS,
        fetch_missing=False,
    )
    ranked = attach_research_links(ranked)
    return {
        "ranked": ranked,
        "sectors": sectors,
        "scanned": scanned_total,
        "with_data": len(ranked),
        "industry_col": industry_col,
    }


def assemble_headwind_from_iv_cache(
    universe: pd.DataFrame,
    *,
    min_mcap_cr: float,
    min_sector_companies: int = 1,
    max_hours: int | None = None,
) -> dict | None:
    """Build headwind board from SQLite ticker cache only (no yfinance)."""
    if universe.empty:
        return None

    cache_hours = HEADWIND_IV_CACHE_HOURS if max_hours is None else max_hours
    tickers = [safe_str(t).upper() for t in universe["ticker"] if safe_str(t)]
    cached_df = load_cached_iv_rows(tickers, max_hours=cache_hours)
    if cached_df.empty:
        return None

    meta_by_ticker = {
        safe_str(row.get("ticker")).upper(): row
        for _, row in universe.iterrows()
        if safe_str(row.get("ticker"))
    }
    rows: list[dict] = []
    for _, cached in cached_df.iterrows():
        ticker = safe_str(cached.get("ticker")).upper()
        if not ticker:
            continue
        cap = cached.get("market_cap_cr")
        if cap is not None and not pd.isna(cap) and float(cap) < min_mcap_cr:
            continue
        row = iv_row_from_cache(cached)
        src = meta_by_ticker.get(ticker)
        if src is not None:
            _merge_listing_meta(row, src)
        rows.append(row)

    result = _finalize_intrinsic_value_scan(
        rows,
        scanned_total=len(universe),
        min_sector_companies=min_sector_companies,
    )
    if result["sectors"] is None or result["sectors"].empty:
        return None
    return result


def run_intrinsic_value_scan(
    universe: pd.DataFrame,
    *,
    max_workers: int | None = None,
    min_mcap_cr: float | None = None,
    min_sector_companies: int = 2,
    prefilter_mcap: bool = False,
    use_cache: bool = True,
    progress_callback: Callable[[int, int], None] | None = None,
    progress_phase: Callable[[int, int, str], None] | None = None,
) -> dict:
    if universe.empty:
        return {
            "ranked": pd.DataFrame(),
            "sectors": pd.DataFrame(),
            "scanned": 0,
            "with_data": 0,
        }

    scanned_total = len(universe)
    mcap_floor = MIN_MARKET_CAP_CR if min_mcap_cr is None else min_mcap_cr
    workers = max_workers or yfinance_worker_count(len(universe), INTRINSIC_VALUE_MAX_WORKERS)

    if prefilter_mcap:

        def _mcap_progress(done: int, total: int, _phase: str) -> None:
            if progress_phase:
                progress_phase(done, total, "mcap")

        universe, _excluded = shrink_universe_by_mcap(
            universe,
            min_cr=mcap_floor,
            max_workers=workers,
            progress_callback=_mcap_progress if progress_phase else None,
        )
        if universe.empty:
            return {
                "ranked": pd.DataFrame(),
                "sectors": pd.DataFrame(),
                "scanned": scanned_total,
                "with_data": 0,
            }

    tickers = [safe_str(t).upper() for t in universe["ticker"] if safe_str(t)]
    cached_df = load_cached_iv_rows(tickers, max_hours=INTRINSIC_VALUE_CACHE_HOURS) if use_cache else pd.DataFrame()
    cached_by_ticker: dict[str, dict] = {}
    if not cached_df.empty:
        for _, row in cached_df.iterrows():
            cached_by_ticker[safe_str(row["ticker"]).upper()] = iv_row_from_cache(row)

    rows: list[dict] = []
    jobs: list[tuple[pd.Series, str | None, float | None]] = []
    for _, src in universe.iterrows():
        ticker = safe_str(src.get("ticker")).upper()
        if not ticker:
            continue
        if ticker in cached_by_ticker:
            row = cached_by_ticker[ticker].copy()
            pe_missing = (
                row.get("pe_ratio") is None or pd.isna(row.get("pe_ratio"))
            ) and (
                row.get("forward_pe") is None or pd.isna(row.get("forward_pe"))
            )
            if pe_missing:
                known_mcap = src.get("market_cap_cr")
                known_mcap_f = (
                    float(known_mcap)
                    if known_mcap is not None and not pd.isna(known_mcap)
                    else None
                )
                jobs.append((src, safe_str(src.get("market")) or None, known_mcap_f))
                continue
            _merge_listing_meta(row, src)
            rows.append(row)
            continue
        known_mcap = src.get("market_cap_cr")
        known_mcap_f = float(known_mcap) if known_mcap is not None and not pd.isna(known_mcap) else None
        jobs.append((src, safe_str(src.get("market")) or None, known_mcap_f))

    total_jobs = len(jobs)
    done = 0
    persist_batch: list[dict] = []

    if jobs:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    analyze_intrinsic_value_stock,
                    safe_str(src.get("ticker")),
                    market,
                    min_mcap_cr=mcap_floor,
                    known_mcap_cr=known_mcap,
                ): src
                for src, market, known_mcap in jobs
            }
            for fut in as_completed(futures):
                done += 1
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
                    persist_batch.append(result)
                    if len(persist_batch) >= _IV_PERSIST_BATCH:
                        if use_cache:
                            persist_iv_rows(persist_batch)
                        persist_batch.clear()

    if use_cache and persist_batch:
        persist_iv_rows(persist_batch)

    return _finalize_intrinsic_value_scan(
        rows,
        scanned_total=scanned_total,
        min_sector_companies=min_sector_companies,
    )


__all__ = [
    "assemble_headwind_from_iv_cache",
    "filter_universe_by_db_mcap",
    "drop_known_sub_floor",
    "prepare_pead_universe",
    "resolve_scan_group_col",
    "run_intrinsic_value_scan",
    "analyze_intrinsic_value_stock",
    "ensure_pcf_values",
    "fetch_stock_pcf",
    "shrink_universe_by_mcap",
]
