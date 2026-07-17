"""PEAD 2 — fetch quarterly metrics + score for dashboard."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

import pandas as pd
import yfinance as yf

from stocks.core.config import (
    PEAD2_CACHE_HOURS,
    PEAD2_CALC_VERSION,
    PEAD2_DRIFT_DAYS,
    PEAD2_MAX_WORKERS,
    PEAD2_MIN_QUARTERS,
    PEAD2_SALES_BUST_QOQ_MIN,
    PEAD2_SALES_BUST_STREAK,
    STRATEGY_YFINANCE_MAX_INFLIGHT,
    yfinance_worker_count,
)
from stocks.core.database import load_pead2_cache, load_pead2_fetched_at, save_market_cap_to_db, save_pead2_cache
from stocks.strategies.earnings.quality import cap_eps_yoy_pct, cap_growth_qoq_pct, passes_earnings_quality
from stocks.strategies.earnings.strategy import EBIDT_FIELDS, EPS_FIELDS
from stocks.strategies.valuation_formula.strategy import comfort_buy_fields
from stocks.core.log_service import METRICS_ERROR, log_error
from stocks.strategies.pead2.strategy import (
    CFO_FIELDS,
    NET_INCOME_FIELDS,
    Pead2AbsoluteWeights,
    apply_breakout_map,
    compute_cf_profit,
    compute_daily_ret_ff,
    compute_daily_ret_pct,
    compute_forward_pe,
    compute_growth_metrics,
    compute_returns_pct,
    compute_trailing_pe,
    score_pead2_candidates,
    series_through_lag,
    trim_reported_quarters,
    unannounced_latest_offset,
    result_quarter_end,
)
from stocks.core.text_utils import safe_str
from stocks.strategies.pead2.quarters import (
    PEAD2_QUARTER_PANEL,
    build_quarter_panel,
    is_sales_bust,
    sanitize_quarter_panel,
)
from stocks.strategies.pead2.technicals import build_price_snapshot
from stocks.strategies.pead.service import estimate_result_date, prepare_pead_universe
from stocks.market.company_profile import hydrate_blob_profile, merge_company_profile
from stocks.market.price_service import to_yfinance_symbol
from stocks.shared.links import attach_research_links
from stocks.core.text_utils import safe_str
from stocks.market.yfinance_limits import call_fast

REVENUE_FIELDS = (
    "Total Revenue",
    "Operating Revenue",
    "Revenue",
)

# Banks and some industrials omit EBIT/EBITDA on Yahoo — fall back before skipping.
_PEAD2_EBIDT_FALLBACK_FIELDS = (
    "Pretax Income",
    "Net Interest Income",
    "Net Income Continuous Operations",
)


def _series_from_income(income: pd.DataFrame, fields: tuple[str, ...]) -> pd.Series | None:
    if income is None or income.empty:
        return None
    for field in fields:
        if field in income.index:
            series = income.loc[field, :].dropna().sort_index()
            if not series.empty:
                return series.astype(float)
    return None


def _pead2_ebidt_series(income: pd.DataFrame) -> pd.Series | None:
    series = _series_from_income(income, EBIDT_FIELDS)
    if series is not None and not series.empty:
        return series
    return _series_from_income(income, _PEAD2_EBIDT_FALLBACK_FIELDS)


def _pead2_passes_earnings_quality(net_profit: pd.Series, eps: pd.Series) -> bool:
    """PEAD2 earnings gate — allow shorter EPS history when YoY base check cannot run."""
    ok, reason = passes_earnings_quality(net_profit, eps)
    if ok:
        return True
    ep = eps.dropna()
    if reason.startswith("Need 5+") and len(ep) >= 3:
        return True
    return False


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


def _safe_yf_info(yt: yf.Ticker) -> dict:
    try:
        return yt.info or {}
    except Exception:
        return {}


def _last_hist_close(hist: pd.DataFrame) -> float | None:
    if hist is None or hist.empty or "Close" not in hist.columns:
        return None
    close = hist["Close"].dropna()
    if close.empty:
        return None
    return round(float(close.iloc[-1]), 2)


def _info_price(info: dict, hist: pd.DataFrame | None = None) -> float | None:
    price = info.get("regularMarketPrice") or info.get("currentPrice")
    if price is not None and not pd.isna(price):
        return round(float(price), 2)
    return _last_hist_close(hist) if hist is not None else None


def _backfill_lag_from_legacy(lag_row: dict, legacy_lag: dict | None) -> dict:
    if not legacy_lag:
        return lag_row
    out = dict(lag_row)
    for key in (
        "price",
        "snapshot",
        "pe_ratio",
        "forward_pe",
        "returns_pct",
        "daily_ret_pct",
    ):
        if out.get(key) is None and legacy_lag.get(key) is not None:
            out[key] = legacy_lag[key]
    return out


def _backfill_blob_from_legacy(blob: dict, legacy: dict | None) -> dict:
    if not legacy:
        return blob
    out = dict(blob)
    lags = dict(out.get("lags") or {})
    leg_lags = legacy.get("lags") or {}
    for key, lag_row in lags.items():
        lags[key] = _backfill_lag_from_legacy(lag_row, leg_lags.get(key))
    out["lags"] = lags
    if out.get("market_cap_cr") is None and legacy.get("market_cap_cr") is not None:
        out["market_cap_cr"] = legacy["market_cap_cr"]
    return out


def _newest_legacy_cache(all_cached: dict[str, dict]) -> dict[str, dict]:
    legacy: dict[str, dict] = {}
    for ticker, blob in all_cached.items():
        if blob.get("calc_version") == PEAD2_CALC_VERSION:
            continue
        prev = legacy.get(ticker)
        if prev is None or (blob.get("calc_version") or 0) >= (prev.get("calc_version") or 0):
            legacy[ticker] = blob
    return legacy


PendingFetchMode = Literal["all", "missing", "stale", "aged", "no_data"]
PEAD2_PENDING_FETCH_MODES: tuple[PendingFetchMode, ...] = (
    "all",
    "missing",
    "stale",
    "aged",
    "no_data",
)


@dataclass(frozen=True)
class Pead2ScanCoverage:
    """How much of a scan universe is already in ``pead2_cache`` (current calc version)."""

    universe_total: int
    cached: int
    stale: int
    missing: int
    scorable: int = 0
    aged: int = 0

    @property
    def pending(self) -> int:
        return self.stale + self.missing

    @property
    def refreshable(self) -> int:
        """Tickers that can be batch-refreshed (missing, old formula, or aged cache)."""
        return self.stale + self.missing + self.aged

    @property
    def no_data(self) -> int:
        return max(self.cached - self.scorable, 0)

    @property
    def complete(self) -> bool:
        return self.universe_total > 0 and self.refreshable == 0

    def pending_count(self, mode: PendingFetchMode = "all") -> int:
        if mode == "missing":
            return self.missing
        if mode == "stale":
            return self.stale
        if mode == "aged":
            return self.aged
        if mode == "no_data":
            return self.no_data
        return self.refreshable


def _pead2_scorable_blob(blob: dict) -> bool:
    return not blob.get("no_pead_data")


def _pead2_no_data_blob(ticker: str, market: str | None) -> dict:
    return {
        "ticker": safe_str(ticker).upper(),
        "market": market,
        "calc_version": PEAD2_CALC_VERSION,
        "no_pead_data": True,
        "lags": {},
    }


def _scorable_cached_rows(cached: dict[str, dict], universe_keys: set[str]) -> list[dict]:
    return [
        blob
        for blob in cached.values()
        if safe_str(blob.get("ticker")).upper() in universe_keys and _pead2_scorable_blob(blob)
    ]


def _universe_ticker_lists(
    universe: pd.DataFrame,
) -> tuple[list[str], list[str | None], set[str]]:
    if universe.empty or "ticker" not in universe.columns:
        return [], [], set()
    work = universe.drop_duplicates("ticker")
    tickers: list[str] = []
    markets: list[str | None] = []
    has_market = "market" in work.columns
    for _, row in work.iterrows():
        ticker = safe_str(row["ticker"]).upper()
        if not ticker:
            continue
        tickers.append(ticker)
        markets.append(safe_str(row["market"]) or None if has_market else None)
    return tickers, markets, set(tickers)


def _should_tombstone_failed_fetch(mode: PendingFetchMode) -> bool:
    return mode in ("missing", "no_data")


def _is_pead2_cache_aged(fetched_at: str | None) -> bool:
    from stocks.core.database import _is_fresh

    if not fetched_at:
        return False
    return not _is_fresh(fetched_at, PEAD2_CACHE_HOURS)


def _filter_pending_tickers(
    tickers: list[str],
    markets: list[str | None],
    cached: dict[str, dict],
    all_cached: dict[str, dict],
    fetched_at: dict[str, str],
    *,
    mode: PendingFetchMode = "all",
) -> list[tuple[str, str | None]]:
    pending: list[tuple[str, str | None]] = []
    for ticker, market in zip(tickers, markets):
        raw = all_cached.get(ticker)
        if mode == "no_data":
            blob = cached.get(ticker)
            if blob is None or _pead2_scorable_blob(blob):
                continue
            pending.append((ticker, market))
            continue
        if mode == "aged":
            if ticker not in cached:
                continue
            if not _is_pead2_cache_aged(fetched_at.get(ticker)):
                continue
            pending.append((ticker, market))
            continue
        if ticker in cached:
            if mode == "all" and (
                _is_pead2_cache_aged(fetched_at.get(ticker))
                or not _pead2_scorable_blob(cached[ticker])
            ):
                pending.append((ticker, market))
            continue
        if mode == "missing" and raw is not None:
            continue
        if mode == "stale" and raw is None:
            continue
        pending.append((ticker, market))
    return pending


def _partition_pead2_universe_cache(
    universe: pd.DataFrame,
    *,
    pending_mode: PendingFetchMode = "all",
) -> tuple[dict[str, dict], list[tuple[str, str | None]], Pead2ScanCoverage, dict[str, dict]]:
    """Split universe into fresh SQLite rows vs tickers that still need Yahoo."""
    tickers, markets, universe_keys = _universe_ticker_lists(universe)
    if not tickers:
        empty = Pead2ScanCoverage(0, 0, 0, 0, 0, 0)
        return {}, [], empty, {}

    all_cached = load_pead2_cache(tickers, max_hours=999999)
    fetched_at = load_pead2_fetched_at(tickers)
    legacy_by_ticker = _newest_legacy_cache(all_cached)

    cached: dict[str, dict] = {}
    stale = 0
    missing = 0
    aged = 0
    for ticker in tickers:
        raw = all_cached.get(ticker)
        if raw is None:
            missing += 1
            continue
        if raw.get("calc_version") != PEAD2_CALC_VERSION:
            stale += 1
            continue
        cached[ticker] = hydrate_blob_profile(
            _backfill_blob_from_legacy(raw, legacy_by_ticker.get(ticker))
        )
        if _is_pead2_cache_aged(fetched_at.get(ticker)):
            aged += 1

    pending = _filter_pending_tickers(
        tickers,
        markets,
        cached,
        all_cached,
        fetched_at,
        mode=pending_mode,
    )

    scorable = sum(
        1 for ticker in tickers if ticker in cached and _pead2_scorable_blob(cached[ticker])
    )
    coverage = Pead2ScanCoverage(
        universe_total=len(tickers),
        cached=len(cached),
        stale=stale,
        missing=missing,
        scorable=scorable,
        aged=aged,
    )
    return cached, pending, coverage, legacy_by_ticker


def pead2_scan_coverage(universe: pd.DataFrame) -> Pead2ScanCoverage:
    """DB-only count of cached vs remaining tickers for the current universe."""
    _, _, coverage, _ = _partition_pead2_universe_cache(universe)
    return coverage


def _breakout_map_from_frames(
    *,
    tq_df: pd.DataFrame | None,
    bb_df: pd.DataFrame | None,
) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if tq_df is not None and not tq_df.empty:
        for _, row in tq_df.iterrows():
            ticker = safe_str(row.get("ticker")).upper()
            if not ticker:
                continue
            out.setdefault(ticker, {})["tq"] = {
                "score": row.get("score"),
                "crossover_type": row.get("crossover_type"),
                "timeframe": row.get("timeframe") or "weekly",
            }
    if bb_df is not None and not bb_df.empty:
        for _, row in bb_df.iterrows():
            ticker = safe_str(row.get("ticker")).upper()
            if not ticker:
                continue
            out.setdefault(ticker, {})["bb"] = {
                "signal": row.get("signal") or "ABOVE_BAND",
                "timeframe": row.get("timeframe") or "weekly",
            }
    return out


def attach_weekly_breakouts_to_pead(
    df: pd.DataFrame,
    *,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    persist: bool = True,
) -> pd.DataFrame:
    """Check BB weekly + TQ weekly on PEAD rows; flag breakouts and optionally cache."""
    if df is None or df.empty or "ticker" not in df.columns:
        return df

    work = df
    if "pead_score" in df.columns:
        scored = df[df["pead_score"].notna()]
        if not scored.empty:
            work = scored

    meta_cols = [c for c in ("ticker", "name", "market", "sector", "industry", "sub_sector") if c in work.columns]
    universe = work[meta_cols].drop_duplicates("ticker").copy()
    if universe.empty:
        return df

    from stocks.strategies.tq_bb.service import run_bb_strategy, run_tq_strategy

    bb_done = 0
    tq_done = 0
    bb_total = len(universe)
    tq_total = len(universe)

    def _bb_progress(done: int, total: int) -> None:
        nonlocal bb_done
        bb_done = done
        if progress_callback:
            progress_callback(bb_done + tq_done, bb_total + tq_total)

    def _tq_progress(done: int, total: int) -> None:
        nonlocal tq_done
        tq_done = done
        if progress_callback:
            progress_callback(bb_done + tq_done, bb_total + tq_total)

    bb_df = run_bb_strategy(
        universe,
        timeframe="weekly",
        progress_callback=_bb_progress if progress_callback else None,
    )
    tq_df = run_tq_strategy(
        universe,
        timeframe="weekly",
        max_workers=max_workers,
        progress_callback=_tq_progress if progress_callback else None,
    )

    if persist:
        from stocks.core.database import (
            clear_strategy_breakouts_for_tickers,
            upsert_strategy_bb_signals,
            upsert_strategy_tq_signals,
        )

        checked = universe["ticker"].astype(str).str.strip().str.upper().tolist()
        clear_strategy_breakouts_for_tickers(checked, timeframe="weekly")
        if bb_df is not None and not bb_df.empty:
            upsert_strategy_bb_signals(bb_df, timeframe="weekly")
        if tq_df is not None and not tq_df.empty:
            upsert_strategy_tq_signals(tq_df, timeframe="weekly")

    bmap = _breakout_map_from_frames(tq_df=tq_df, bb_df=bb_df)
    return apply_breakout_map(df, bmap, overwrite=True)


def expand_pead_candidates_to_universe(
    universe: pd.DataFrame,
    candidates: pd.DataFrame,
) -> pd.DataFrame:
    """Show every universe ticker; scored rows keep PEAD fields, others show as no-data."""
    if universe.empty or "ticker" not in universe.columns:
        return candidates

    meta_cols = ["ticker", "name", "market", "sector"]
    for col in ("industry", "sub_sector"):
        if col in universe.columns:
            meta_cols.append(col)
    base = universe[meta_cols].drop_duplicates("ticker").copy()
    base["ticker"] = base["ticker"].astype(str).str.strip().str.upper()

    score_df = pd.DataFrame()
    if candidates is not None and not candidates.empty:
        drop_meta = [c for c in meta_cols if c != "ticker" and c in candidates.columns]
        score_df = candidates.drop(columns=drop_meta, errors="ignore").copy()
        score_df["ticker"] = score_df["ticker"].astype(str).str.strip().str.upper()

    if score_df.empty:
        out = base.copy()
    else:
        out = base.merge(score_df, on="ticker", how="left")

    tickers = base["ticker"].tolist()
    all_cached = load_pead2_cache(tickers, max_hours=999999)

    def _status(ticker: str) -> str:
        blob = all_cached.get(ticker) or {}
        if blob.get("calc_version") != PEAD2_CALC_VERSION:
            return "Not scanned"
        if _pead2_scorable_blob(blob):
            return ""
        reason = safe_str(blob.get("no_pead_data_reason")).strip()
        return reason or "No PEAD data"

    out["pead_status"] = out["ticker"].map(_status)
    if "pead_score" not in out.columns:
        out["pead_score"] = pd.NA
    out = out.sort_values(
        by=["pead_score", "ticker"],
        ascending=[False, True],
        na_position="last",
    )
    return out.reset_index(drop=True)


def _pead2_scan_result_shell(
    *,
    coverage: Pead2ScanCoverage,
    cache_hits: int = 0,
    fetched: int = 0,
    fetch_failed: int = 0,
    saved: int = 0,
    tombstoned: int = 0,
    **extra,
) -> dict:
    return {
        "candidates": pd.DataFrame(),
        "candidates_previous": pd.DataFrame(),
        "scanned": coverage.universe_total,
        "hits": 0,
        "hits_previous": 0,
        "cache_hits": cache_hits,
        "cached": coverage.cached,
        "pending": coverage.pending,
        "stale": coverage.stale,
        "missing": coverage.missing,
        "fetched": fetched,
        "fetch_failed": fetch_failed,
        "saved": saved,
        "tombstoned": tombstoned,
        "cleared": saved + tombstoned,
        "coverage": coverage,
        **extra,
    }


def _normalize_cache_blob(row: dict) -> dict:
    """Support calc v2 flat rows and v3 ``lags`` payloads."""
    if "lags" in row and isinstance(row["lags"], dict):
        return row
    shared = {
        "ticker": row.get("ticker"),
        "market": row.get("market"),
        "market_cap_cr": row.get("market_cap_cr"),
        "calc_version": row.get("calc_version"),
    }
    lag0 = {
        k: v
        for k, v in row.items()
        if k
        not in {
            "ticker",
            "market",
            "market_cap_cr",
            "calc_version",
            "name",
            "sector",
            "screener_link",
            "tv_link",
        }
    }
    lag0.setdefault("quarter_lag", 0)
    return {**shared, "lags": {"0": lag0}}


def _has_usable_revenue(revenue: pd.Series) -> bool:
    """Reject distressed / bad Yahoo rows (zero or negative latest sales)."""
    s = revenue.dropna().sort_index().astype(float)
    if len(s) < 2:
        return False
    if float(s.iloc[-1]) <= 0:
        return False
    recent = s.iloc[-min(4, len(s)) :]
    return int((recent > 0).sum()) >= max(2, len(recent) // 2)


def _enrich_snapshot_profile(
    snapshot: dict,
    *,
    ticker: str,
    market: str | None,
) -> dict:
    return merge_company_profile(snapshot, ticker, market)


def _pead2_row_for_lag(
    *,
    ticker: str,
    market: str | None,
    market_cap_cr: float | None,
    price_val: float | None,
    revenue: pd.Series,
    ebidt: pd.Series,
    net_profit: pd.Series,
    eps: pd.Series,
    cfo: pd.Series | None,
    yt: yf.Ticker,
    info: dict,
    hist: pd.DataFrame,
    lag: int,
) -> dict | None:
    rev = series_through_lag(revenue, lag)
    eb = series_through_lag(ebidt, lag)
    np_s = series_through_lag(net_profit, lag)
    ep = series_through_lag(eps, lag)
    cf = series_through_lag(cfo, lag) if cfo is not None else None
    if rev is None or eb is None or np_s is None or ep is None:
        return None
    min_needed = PEAD2_MIN_QUARTERS if lag == 0 else max(4, PEAD2_MIN_QUARTERS - 1)
    if len(rev) < min_needed:
        return None
    if lag == 0 and not _has_usable_revenue(rev):
        return None

    nse_announced: list[pd.Timestamp] | None = None
    if lag == 0 and ticker:
        from stocks.market.nse_result_dates import nse_announced_dates

        nse_announced = nse_announced_dates(ticker, market=market)

    result_q_end = (
        result_quarter_end(
            revenue,
            yt,
            ticker=ticker,
            market=market,
            announced_dates=nse_announced,
        )
        if lag == 0
        else pd.Timestamp(rev.index[-1])
    )
    result_date = estimate_result_date(
        yt,
        result_q_end,
        ticker=ticker,
        market=market,
    )
    growth_offset = 0
    if lag == 0:
        growth_offset = unannounced_latest_offset(
            revenue,
            yt,
            ticker=ticker,
            market=market,
            announced_dates=nse_announced,
        )
        min_growth_quarters = min(4, PEAD2_QUARTER_PANEL)
        while growth_offset > 0:
            probe = series_through_lag(revenue, growth_offset)
            if probe is not None and len(probe) >= min_growth_quarters:
                break
            growth_offset -= 1
        rev_g = series_through_lag(revenue, growth_offset)
        eb_g = series_through_lag(ebidt, growth_offset)
        np_g = series_through_lag(net_profit, growth_offset)
        ep_g = series_through_lag(eps, growth_offset)
        cf_g = series_through_lag(cfo, growth_offset) if cfo is not None else None
        rev_g = rev_g if rev_g is not None else rev
        eb_g = eb_g if eb_g is not None else eb
        np_g = np_g if np_g is not None else np_s
        ep_g = ep_g if ep_g is not None else ep
        if cf_g is None:
            cf_g = cf
        quarter_end = pd.Timestamp(rev_g.index[-1])
    else:
        rev_g, eb_g, np_g, ep_g, cf_g = rev, eb, np_s, ep, cf
        quarter_end = pd.Timestamp(rev.index[-1])
    if price_val is not None:
        returns_pct = compute_returns_pct(
            hist, result_date, current_price=price_val
        )
    else:
        returns_pct = compute_returns_pct(
            hist,
            result_date,
            drift_days=PEAD2_DRIFT_DAYS,
        )
    daily_ret_pct = compute_daily_ret_ff(hist, result_date)
    growth = compute_growth_metrics(rev_g, np_g, eb_g, ep_g)
    if growth.get("eps_yoy") is not None:
        growth["eps_yoy"] = cap_eps_yoy_pct(growth["eps_yoy"])
    if growth.get("np_yoy") is not None:
        growth["np_yoy"] = cap_eps_yoy_pct(growth["np_yoy"])
    for qoq_key in ("sales_qoq", "np_qoq", "eps_qoq", "ebidt_qoq"):
        if growth.get(qoq_key) is not None:
            growth[qoq_key] = cap_growth_qoq_pct(growth[qoq_key])
    panel_lag = growth_offset if lag == 0 else 0
    rev_p = series_through_lag(revenue, panel_lag)
    eb_p = series_through_lag(ebidt, panel_lag)
    np_p = series_through_lag(net_profit, panel_lag)
    ep_p = series_through_lag(eps, panel_lag)
    if rev_p is None:
        rev_p = rev
    if eb_p is None:
        eb_p = eb
    if np_p is None:
        np_p = np_s
    if ep_p is None:
        ep_p = ep
    quarters = sanitize_quarter_panel(build_quarter_panel(rev_p, eb_p, np_p, ep_p))
    sales_bust, sales_streak = is_sales_bust(
        rev,
        growth.get("sales_qoq"),
        min_streak=PEAD2_SALES_BUST_STREAK,
        min_qoq_pct=PEAD2_SALES_BUST_QOQ_MIN,
    )

    row: dict = {
        "quarter_lag": lag,
        "result_date": pd.Timestamp(result_date).strftime("%Y-%m-%d"),
        "quarter_end": quarter_end.strftime("%Y-%m-%d"),
        "price": round(price_val, 2) if price_val is not None else None,
        "forward_pe": compute_forward_pe(price_val, ep_g, info),
        "pe_ratio": compute_trailing_pe(price_val, ep_g, info)
        if lag == 0
        else compute_forward_pe(price_val, ep_g, info),
        "returns_pct": returns_pct,
        "daily_ret_pct": daily_ret_pct,
        "cf_profit": compute_cf_profit(cf_g, np_g),
        **{k: round(v, 2) if v is not None else None for k, v in growth.items()},
        "sales_bust": sales_bust,
        "sales_streak": sales_streak,
    }
    if quarters:
        row["quarters"] = quarters
    if lag == 0:
        snapshot = build_price_snapshot(
            info,
            hist,
            revenue,
            price=price_val,
            pe_ratio=row.get("pe_ratio"),
            forward_pe=row.get("forward_pe"),
        )
        if snapshot:
            snapshot = _enrich_snapshot_profile(
                snapshot,
                ticker=ticker,
                market=market,
            )
            row["snapshot"] = snapshot
    return row


def _expand_lag_rows(blobs: list[dict], *, quarter_lag: int) -> list[dict]:
    rows: list[dict] = []
    key = str(quarter_lag)
    for blob in blobs:
        norm = _normalize_cache_blob(blob)
        lag_row = norm.get("lags", {}).get(key)
        if not lag_row:
            continue
        rows.append(
            {
                "ticker": norm.get("ticker"),
                "market": norm.get("market"),
                "market_cap_cr": norm.get("market_cap_cr"),
                **lag_row,
            }
        )
    return rows


def _score_pead_frame(
    rows: list[dict],
    meta: pd.DataFrame,
    *,
    weights: Pead2AbsoluteWeights | None = None,
) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = score_pead2_candidates(df, weights=weights)
    df["calculation_date"] = datetime.now(timezone.utc).isoformat()
    if not meta.empty:
        df = df.merge(meta, on="ticker", how="left", suffixes=("", "_meta"))
        for col in ("name", "market", "sector", "industry", "sub_sector"):
            meta_col = f"{col}_meta"
            if meta_col in df.columns:
                df[col] = df[col].fillna(df[meta_col])
                df = df.drop(columns=[meta_col])
    return attach_research_links(df)


def analyze_pead2_ticker(
    ticker: str,
    market: str | None,
    *,
    min_mcap_cr: float | None = None,
) -> dict | None:
    symbol = to_yfinance_symbol(ticker, market)

    def _fetch() -> dict | None:
        yt = yf.Ticker(symbol)
        info = _safe_yf_info(yt)
        market_cap_cr = _cache_market_cap(ticker, market, symbol, info)
        if (
            min_mcap_cr is not None
            and min_mcap_cr > 0
            and market_cap_cr is not None
            and market_cap_cr < min_mcap_cr
        ):
            return None

        income = yt.quarterly_income_stmt
        cashflow = yt.quarterly_cashflow
        revenue = _series_from_income(income, REVENUE_FIELDS)
        ebidt = _pead2_ebidt_series(income)
        net_profit = _series_from_income(income, NET_INCOME_FIELDS)
        eps = _series_from_income(income, EPS_FIELDS)
        cfo = _series_from_income(cashflow, CFO_FIELDS) if cashflow is not None else None

        revenue = trim_reported_quarters(revenue)
        ebidt = trim_reported_quarters(ebidt)
        net_profit = trim_reported_quarters(net_profit)
        eps = trim_reported_quarters(eps)
        if cfo is not None:
            cfo = trim_reported_quarters(cfo)

        if (
            revenue is None
            or revenue.empty
            or ebidt is None
            or ebidt.empty
            or net_profit is None
            or net_profit.empty
            or eps is None
            or eps.empty
        ):
            return None
        if len(revenue) < PEAD2_MIN_QUARTERS:
            return None

        if not _pead2_passes_earnings_quality(net_profit, eps):
            return None

        hist = yt.history(period="6y", interval="1d", auto_adjust=True)
        price_val = _info_price(info, hist)
        comfort = comfort_buy_fields(
            price=price_val,
            info=info,
            balance_sheet=yt.balance_sheet,
            financials=yt.financials,
            cashflow=yt.cashflow,
            hist=hist,
        )

        lags: dict[str, dict] = {}
        for lag in (0, 1):
            lag_row = _pead2_row_for_lag(
                ticker=ticker,
                market=market,
                market_cap_cr=market_cap_cr,
                price_val=price_val,
                revenue=revenue,
                ebidt=ebidt,
                net_profit=net_profit,
                eps=eps,
                cfo=cfo,
                yt=yt,
                info=info,
                hist=hist,
                lag=lag,
            )
            if lag_row:
                if lag == 0:
                    lag_row.update(comfort)
                lags[str(lag)] = lag_row

        if "0" not in lags:
            return None

        return {
            "ticker": safe_str(ticker).upper(),
            "market": safe_str(market) or None,
            "market_cap_cr": market_cap_cr,
            "calc_version": PEAD2_CALC_VERSION,
            "lags": lags,
        }

    def _log(exc: Exception) -> None:
        log_error(
            METRICS_ERROR,
            "PEAD2 fetch failed",
            ticker=ticker,
            symbol=symbol,
            error=str(exc),
        )

    return call_fast(_fetch, on_error=_log)


def _filter_df_by_recent_result(df: pd.DataFrame, recent_days: int) -> pd.DataFrame:
    """Keep rows whose result_date falls within the last ``recent_days`` calendar days."""
    if df is None or df.empty or "result_date" not in df.columns:
        return pd.DataFrame()
    cutoff = pd.Timestamp.now().tz_localize(None).normalize() - pd.Timedelta(days=recent_days)
    rd = pd.to_datetime(df["result_date"], errors="coerce")
    mask = rd.notna() & (rd >= cutoff)
    out = df.loc[mask].copy()
    if out.empty:
        return out
    return out.sort_values("result_date", ascending=False).reset_index(drop=True)


def run_pead2_recent_scan(
    universe: pd.DataFrame,
    *,
    recent_days: int,
    weights: Pead2AbsoluteWeights | None = None,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    min_mcap_cr: float | None = None,
    max_fetch: int | None = None,
) -> dict:
    """
    PEAD scan focused on recent result dates — uses SQLite cache first and only
    fetches tickers missing from cache (up to ``max_fetch``).
    """
    from stocks.core.config import PEAD2_RECENT_MAX_FETCH

    if universe.empty:
        return _pead2_scan_result_shell(
            coverage=Pead2ScanCoverage(0, 0, 0, 0, 0, 0),
            recent_days=recent_days,
        )

    fetch_cap = PEAD2_RECENT_MAX_FETCH if max_fetch is None else max(0, max_fetch)
    tickers, markets, universe_keys = _universe_ticker_lists(universe)
    workers = yfinance_worker_count(
        len(tickers),
        min(max_workers or PEAD2_MAX_WORKERS, STRATEGY_YFINANCE_MAX_INFLIGHT),
    )
    meta_cols = ["ticker", "name", "market", "sector"]
    for col in ("industry", "sub_sector"):
        if col in universe.columns:
            meta_cols.append(col)
    meta = universe[meta_cols].drop_duplicates("ticker")

    cached, pending_all, coverage, legacy_by_ticker = _partition_pead2_universe_cache(universe)
    rows = _scorable_cached_rows(cached, universe_keys)
    cache_hits = len(rows)
    pending = pending_all[:fetch_cap]

    total = coverage.universe_total
    fetch_total = len(pending)
    done = 0
    fetch_failed = 0
    if progress_callback and fetch_total == 0:
        progress_callback(1, 1)

    fresh_rows: list[dict] = []
    tombstone_rows: list[dict] = []
    if pending:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(analyze_pead2_ticker, t, m, min_mcap_cr=min_mcap_cr): (t, m)
                for t, m in pending
            }
            for future in as_completed(futures):
                ticker, market = futures[future]
                result = future.result()
                if result:
                    ticker_key = safe_str(result.get("ticker")).upper()
                    result = _backfill_blob_from_legacy(
                        result,
                        legacy_by_ticker.get(ticker_key),
                    )
                    if ticker_key in universe_keys:
                        fresh_rows.append(result)
                        rows.append(result)
                else:
                    fetch_failed += 1
                    if ticker not in cached:
                        tombstone_rows.append(_pead2_no_data_blob(ticker, market))
                done += 1
                if progress_callback:
                    progress_callback(done, fetch_total)
        if fresh_rows or tombstone_rows:
            save_pead2_cache(fresh_rows + tombstone_rows)
            cached, _, coverage, legacy_by_ticker = _partition_pead2_universe_cache(universe)
            rows = _scorable_cached_rows(cached, universe_keys)
            cache_hits = len(rows)

    if not rows:
        return _pead2_scan_result_shell(
            coverage=coverage,
            cache_hits=cache_hits,
            fetched=len(pending),
            fetch_failed=fetch_failed,
            saved=len(fresh_rows),
            tombstoned=len(tombstone_rows),
            recent_days=recent_days,
        )

    current_rows = _expand_lag_rows(rows, quarter_lag=0)
    previous_rows = _expand_lag_rows(rows, quarter_lag=1)
    df = _filter_df_by_recent_result(
        _score_pead_frame(current_rows, meta, weights=weights),
        recent_days,
    )
    df_prev = _filter_df_by_recent_result(
        _score_pead_frame(previous_rows, meta, weights=weights),
        recent_days,
    )

    return {
        "candidates": df,
        "candidates_previous": df_prev,
        "scanned": total,
        "hits": len(df),
        "hits_previous": len(df_prev),
        "cache_hits": cache_hits,
        "cached": coverage.cached,
        "pending": coverage.pending,
        "stale": coverage.stale,
        "missing": coverage.missing,
        "fetched": len(pending),
        "fetch_failed": fetch_failed,
        "saved": len(fresh_rows),
        "tombstoned": len(tombstone_rows),
        "cleared": len(fresh_rows) + len(tombstone_rows),
        "coverage": coverage,
        "recent_days": recent_days,
    }


def run_pead2_scan(
    universe: pd.DataFrame,
    *,
    weights: Pead2AbsoluteWeights | None = None,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    min_mcap_cr: float | None = None,
    only_pending: bool = False,
    pending_mode: PendingFetchMode = "all",
    max_fetch: int | None = None,
    check_breakouts: bool | None = None,
) -> dict:
    """
    Load PEAD rows from SQLite, then fetch Yahoo for tickers not cached at the
    current calc version. Set ``only_pending`` to skip Yahoo when nothing remains.
    Use ``pending_mode`` with ``only_pending`` to fetch only never-scanned or stale rows.
    When ``only_pending`` is true, Yahoo fetches are capped by ``max_fetch`` (default
    ``PEAD2_RECENT_MAX_FETCH``) so Remaining runs proceed in batches.
    When ``check_breakouts`` is true (default on real scans), also run BB weekly +
    TQ weekly on scored candidates and attach breakout signals.
    """
    from stocks.core.config import PEAD2_RECENT_MAX_FETCH

    fetch_mode: PendingFetchMode = pending_mode if only_pending else "all"
    tickers, markets, universe_keys = _universe_ticker_lists(universe)
    if not tickers:
        return _pead2_scan_result_shell(coverage=Pead2ScanCoverage(0, 0, 0, 0, 0, 0))

    workers = yfinance_worker_count(
        len(tickers),
        min(max_workers or PEAD2_MAX_WORKERS, STRATEGY_YFINANCE_MAX_INFLIGHT),
    )
    meta_cols = ["ticker", "name", "market", "sector"]
    for col in ("industry", "sub_sector"):
        if col in universe.columns:
            meta_cols.append(col)
    meta = universe[meta_cols].drop_duplicates("ticker")

    cached, pending_all, coverage, legacy_by_ticker = _partition_pead2_universe_cache(
        universe,
        pending_mode=fetch_mode,
    )
    if only_pending:
        fetch_cap = PEAD2_RECENT_MAX_FETCH if max_fetch is None else max(0, max_fetch)
        pending = pending_all[:fetch_cap]
    else:
        pending = pending_all
    rows = _scorable_cached_rows(cached, universe_keys)
    cache_hits = len(rows)

    total = coverage.universe_total
    fetch_total = len(pending)
    done = 0
    fetch_failed = 0
    if progress_callback:
        if fetch_total == 0:
            progress_callback(1, 1)
        elif cache_hits:
            progress_callback(0, fetch_total)

    fresh_rows: list[dict] = []
    tombstone_rows: list[dict] = []
    if pending and not (only_pending and fetch_total == 0):
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(analyze_pead2_ticker, t, m, min_mcap_cr=min_mcap_cr): (t, m)
                for t, m in pending
            }
            for future in as_completed(futures):
                ticker, market = futures[future]
                result = future.result()
                if result:
                    ticker_key = safe_str(result.get("ticker")).upper()
                    result = _backfill_blob_from_legacy(
                        result,
                        legacy_by_ticker.get(ticker_key),
                    )
                    if ticker_key in universe_keys:
                        fresh_rows.append(result)
                        rows.append(result)
                else:
                    fetch_failed += 1
                    if _should_tombstone_failed_fetch(fetch_mode):
                        tombstone_rows.append(_pead2_no_data_blob(ticker, market))
                done += 1
                if progress_callback:
                    progress_callback(done, fetch_total)
        if fresh_rows or tombstone_rows:
            save_pead2_cache(fresh_rows + tombstone_rows)
            cached, _, coverage, legacy_by_ticker = _partition_pead2_universe_cache(
                universe,
                pending_mode=fetch_mode,
            )
            rows = _scorable_cached_rows(cached, universe_keys)
            cache_hits = len(rows)

    if not rows:
        return _pead2_scan_result_shell(
            coverage=coverage,
            cache_hits=cache_hits,
            fetched=done,
            fetch_failed=fetch_failed,
            saved=len(fresh_rows),
            tombstoned=len(tombstone_rows),
            pending_mode=fetch_mode,
        )

    current_rows = _expand_lag_rows(rows, quarter_lag=0)
    previous_rows = _expand_lag_rows(rows, quarter_lag=1)
    df = _score_pead_frame(current_rows, meta, weights=weights)
    df_prev = _score_pead_frame(previous_rows, meta, weights=weights)

    do_breakouts = check_breakouts
    if do_breakouts is None:
        # Skip live TQ/BB on DB-only loads (e.g. holdings expand with max_fetch=0).
        do_breakouts = not (only_pending and (max_fetch == 0))

    tq_hits = 0
    bb_hits = 0
    if do_breakouts and not df.empty:
        df = attach_weekly_breakouts_to_pead(
            df,
            max_workers=max_workers,
            progress_callback=progress_callback,
            persist=True,
        )
        if "has_tq" in df.columns:
            tq_hits = int(df["has_tq"].fillna(False).astype(bool).sum())
        if "has_bb" in df.columns:
            bb_hits = int(df["has_bb"].fillna(False).astype(bool).sum())
        if not df_prev.empty:
            from stocks.strategies.pead2.strategy import attach_strategy_breakout_signals

            df_prev = attach_strategy_breakout_signals(df_prev)

    return {
        "candidates": df,
        "candidates_previous": df_prev,
        "scanned": total,
        "hits": len(df),
        "hits_previous": len(df_prev),
        "cache_hits": cache_hits,
        "cached": coverage.cached,
        "pending": coverage.pending,
        "stale": coverage.stale,
        "missing": coverage.missing,
        "fetched": done,
        "fetch_failed": fetch_failed,
        "saved": len(fresh_rows),
        "tombstoned": len(tombstone_rows),
        "cleared": len(fresh_rows) + len(tombstone_rows),
        "coverage": coverage,
        "pending_mode": fetch_mode,
        "tq_hits": tq_hits,
        "bb_hits": bb_hits,
        "checked_breakouts": bool(do_breakouts),
    }


__all__ = [
    "Pead2ScanCoverage",
    "PendingFetchMode",
    "PEAD2_PENDING_FETCH_MODES",
    "attach_weekly_breakouts_to_pead",
    "expand_pead_candidates_to_universe",
    "pead2_scan_coverage",
    "prepare_pead_universe",
    "run_pead2_scan",
    "run_pead2_recent_scan",
    "Pead2AbsoluteWeights",
]
