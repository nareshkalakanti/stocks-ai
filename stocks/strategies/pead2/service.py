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
from stocks.core.database import load_pead2_cache, save_market_cap_to_db, save_pead2_cache
from stocks.strategies.earnings.quality import cap_eps_yoy_pct, cap_growth_qoq_pct, passes_earnings_quality
from stocks.strategies.earnings.strategy import EBIDT_FIELDS, EPS_FIELDS
from stocks.strategies.valuation_formula.strategy import comfort_buy_fields
from stocks.core.log_service import METRICS_ERROR, log_error
from stocks.strategies.pead2.strategy import (
    CFO_FIELDS,
    NET_INCOME_FIELDS,
    Pead2AbsoluteWeights,
    compute_cf_profit,
    compute_daily_ret_ff,
    compute_daily_ret_pct,
    compute_forward_pe,
    compute_growth_metrics,
    compute_returns_pct,
    compute_return_since_result,
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
from stocks.strategies.formula_100x.strategy import compute_100x_cfo_checks
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


def _series_from_income(income: pd.DataFrame, fields: tuple[str, ...]) -> pd.Series | None:
    if income is None or income.empty:
        return None
    for field in fields:
        if field in income.index:
            series = income.loc[field, :].dropna().sort_index()
            if not series.empty:
                return series.astype(float)
    return None


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


PendingFetchMode = Literal["all", "missing", "stale"]
PEAD2_PENDING_FETCH_MODES: tuple[PendingFetchMode, ...] = ("all", "missing", "stale")


@dataclass(frozen=True)
class Pead2ScanCoverage:
    """How much of a scan universe is already in ``pead2_cache`` (current calc version)."""

    universe_total: int
    cached: int
    stale: int
    missing: int

    @property
    def pending(self) -> int:
        return self.stale + self.missing

    @property
    def complete(self) -> bool:
        return self.universe_total > 0 and self.pending == 0

    def pending_count(self, mode: PendingFetchMode = "all") -> int:
        if mode == "missing":
            return self.missing
        if mode == "stale":
            return self.stale
        return self.pending


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


def _filter_pending_tickers(
    tickers: list[str],
    markets: list[str | None],
    cached: dict[str, dict],
    all_cached: dict[str, dict],
    *,
    mode: PendingFetchMode = "all",
) -> list[tuple[str, str | None]]:
    pending: list[tuple[str, str | None]] = []
    for ticker, market in zip(tickers, markets):
        if ticker in cached:
            continue
        raw = all_cached.get(ticker)
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
        empty = Pead2ScanCoverage(0, 0, 0, 0)
        return {}, [], empty, {}

    all_cached = load_pead2_cache(tickers, max_hours=999999)
    legacy_by_ticker = _newest_legacy_cache(all_cached)

    cached: dict[str, dict] = {}
    stale = 0
    missing = 0
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

    pending = _filter_pending_tickers(
        tickers,
        markets,
        cached,
        all_cached,
        mode=pending_mode,
    )

    coverage = Pead2ScanCoverage(
        universe_total=len(tickers),
        cached=len(cached),
        stale=stale,
        missing=missing,
    )
    return cached, pending, coverage, legacy_by_ticker


def pead2_scan_coverage(universe: pd.DataFrame) -> Pead2ScanCoverage:
    """DB-only count of cached vs remaining tickers for the current universe."""
    _, _, coverage, _ = _partition_pead2_universe_cache(universe)
    return coverage


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

    quarter_end = pd.Timestamp(rev.index[-1])
    result_q_end = result_quarter_end(revenue, yt) if lag == 0 else quarter_end
    result_date = estimate_result_date(yt, result_q_end)
    if price_val is not None:
        returns_pct = compute_return_since_result(
            hist, result_date, current_price=price_val
        )
    else:
        returns_pct = compute_returns_pct(
            hist,
            result_date,
            drift_days=PEAD2_DRIFT_DAYS,
        )
    daily_ret_pct = compute_daily_ret_ff(hist, result_date)
    growth = compute_growth_metrics(rev, np_s, eb, ep)
    if growth.get("eps_yoy") is not None:
        growth["eps_yoy"] = cap_eps_yoy_pct(growth["eps_yoy"])
    if growth.get("np_yoy") is not None:
        growth["np_yoy"] = cap_eps_yoy_pct(growth["np_yoy"])
    for qoq_key in ("sales_qoq", "np_qoq", "eps_qoq", "ebidt_qoq"):
        if growth.get(qoq_key) is not None:
            growth[qoq_key] = cap_growth_qoq_pct(growth[qoq_key])
    panel_lag = unannounced_latest_offset(revenue, yt) if lag == 0 else 0
    min_panel_quarters = min(4, PEAD2_QUARTER_PANEL)
    while panel_lag > 0:
        probe = series_through_lag(revenue, panel_lag)
        if probe is not None and len(probe) >= min_panel_quarters:
            break
        panel_lag -= 1
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
        "forward_pe": compute_forward_pe(price_val, ep, info),
        "pe_ratio": compute_trailing_pe(price_val, ep, info)
        if lag == 0
        else compute_forward_pe(price_val, ep, info),
        "returns_pct": returns_pct,
        "daily_ret_pct": daily_ret_pct,
        "cf_profit": compute_cf_profit(cf, np_s),
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
        ebidt = _series_from_income(income, EBIDT_FIELDS)
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
            revenue.empty
            or ebidt.empty
            or net_profit.empty
            or eps.empty
        ):
            return None
        if len(revenue) < PEAD2_MIN_QUARTERS:
            return None

        ok, _reason = passes_earnings_quality(net_profit, eps)
        if not ok:
            return None

        hist = yt.history(period="6y", interval="1d", auto_adjust=True)
        price_val = _info_price(info, hist)
        cfo_checks = compute_100x_cfo_checks(yt.cashflow, yt.financials) or {}
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
                    lag_row.update(
                        {
                            "pass_rising_cfo": bool(cfo_checks.get("pass_rising_cfo")),
                            "pass_cfo_ebit": bool(cfo_checks.get("pass_cfo_ebit")),
                            "cfo_ebit_pct": cfo_checks.get("cfo_ebit_pct"),
                        }
                    )
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
            coverage=Pead2ScanCoverage(0, 0, 0, 0),
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
) -> dict:
    """
    Load PEAD rows from SQLite, then fetch Yahoo for tickers not cached at the
    current calc version. Set ``only_pending`` to skip Yahoo when nothing remains.
    Use ``pending_mode`` with ``only_pending`` to fetch only never-scanned or stale rows.
    When ``only_pending`` is true, Yahoo fetches are capped by ``max_fetch`` (default
    ``PEAD2_RECENT_MAX_FETCH``) so Remaining runs proceed in batches.
    """
    from stocks.core.config import PEAD2_RECENT_MAX_FETCH

    fetch_mode: PendingFetchMode = pending_mode if only_pending else "all"
    tickers, markets, universe_keys = _universe_ticker_lists(universe)
    if not tickers:
        return _pead2_scan_result_shell(coverage=Pead2ScanCoverage(0, 0, 0, 0))

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
                    if only_pending:
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
    }


__all__ = [
    "Pead2ScanCoverage",
    "PendingFetchMode",
    "PEAD2_PENDING_FETCH_MODES",
    "pead2_scan_coverage",
    "prepare_pead_universe",
    "run_pead2_scan",
    "run_pead2_recent_scan",
    "Pead2AbsoluteWeights",
]
