"""PEAD 2 — fetch quarterly metrics + score for dashboard."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

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
        return {
            "candidates": pd.DataFrame(),
            "candidates_previous": pd.DataFrame(),
            "scanned": 0,
            "hits": 0,
            "hits_previous": 0,
            "cache_hits": 0,
            "recent_days": recent_days,
        }

    fetch_cap = PEAD2_RECENT_MAX_FETCH if max_fetch is None else max(0, max_fetch)
    tickers = universe["ticker"].tolist()
    markets = universe["market"].tolist() if "market" in universe.columns else [None] * len(tickers)
    workers = yfinance_worker_count(
        len(tickers),
        min(max_workers or PEAD2_MAX_WORKERS, STRATEGY_YFINANCE_MAX_INFLIGHT),
    )
    meta_cols = ["ticker", "name", "market", "sector"]
    for col in ("industry", "sub_sector"):
        if col in universe.columns:
            meta_cols.append(col)
    meta = universe[meta_cols].drop_duplicates("ticker")
    universe_keys = {safe_str(t).upper() for t in tickers if safe_str(t)}

    all_cached = load_pead2_cache(tickers, max_hours=999999)
    legacy_by_ticker = _newest_legacy_cache(all_cached)
    cached = {
        k: hydrate_blob_profile(
            _backfill_blob_from_legacy(v, legacy_by_ticker.get(k))
        )
        for k, v in all_cached.items()
        if v.get("calc_version") == PEAD2_CALC_VERSION
    }
    rows: list[dict] = [blob for blob in cached.values() if safe_str(blob.get("ticker")).upper() in universe_keys]
    cache_hits = len(rows)

    pending: list[tuple[str, str | None]] = []
    for t, m in zip(tickers, markets):
        key = safe_str(t).upper()
        if key and key not in cached:
            pending.append((t, m))
    pending = pending[:fetch_cap]

    total = len(tickers)
    fetch_total = len(pending)
    done = 0
    if progress_callback and fetch_total == 0:
        progress_callback(1, 1)

    fresh_rows: list[dict] = []
    if pending:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(analyze_pead2_ticker, t, m, min_mcap_cr=min_mcap_cr): t
                for t, m in pending
            }
            for future in as_completed(futures):
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
                done += 1
                if progress_callback:
                    progress_callback(done, fetch_total)
        if fresh_rows:
            save_pead2_cache(fresh_rows)

    if not rows:
        return {
            "candidates": pd.DataFrame(),
            "candidates_previous": pd.DataFrame(),
            "scanned": total,
            "hits": 0,
            "hits_previous": 0,
            "cache_hits": cache_hits,
            "recent_days": recent_days,
            "fetched": len(pending),
        }

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
        "recent_days": recent_days,
        "fetched": len(pending),
    }


def run_pead2_scan(
    universe: pd.DataFrame,
    *,
    weights: Pead2AbsoluteWeights | None = None,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    min_mcap_cr: float | None = None,
) -> dict:
    if universe.empty:
        return {
            "candidates": pd.DataFrame(),
            "candidates_previous": pd.DataFrame(),
            "scanned": 0,
            "hits": 0,
            "hits_previous": 0,
            "cache_hits": 0,
        }

    tickers = universe["ticker"].tolist()
    markets = universe["market"].tolist() if "market" in universe.columns else [None] * len(tickers)
    workers = yfinance_worker_count(
        len(tickers),
        min(max_workers or PEAD2_MAX_WORKERS, STRATEGY_YFINANCE_MAX_INFLIGHT),
    )
    meta_cols = ["ticker", "name", "market", "sector"]
    for col in ("industry", "sub_sector"):
        if col in universe.columns:
            meta_cols.append(col)
    meta = universe[meta_cols].drop_duplicates("ticker")

    all_cached = load_pead2_cache(tickers, max_hours=999999)
    legacy_by_ticker = _newest_legacy_cache(all_cached)
    cached = {
        k: hydrate_blob_profile(
            _backfill_blob_from_legacy(v, legacy_by_ticker.get(k))
        )
        for k, v in all_cached.items()
        if v.get("calc_version") == PEAD2_CALC_VERSION
    }
    rows: list[dict] = list(cached.values())
    cache_hits = len(cached)
    pending: list[tuple[str, str | None]] = [
        (t, m) for t, m in zip(tickers, markets) if safe_str(t).upper() not in cached
    ]

    total = len(tickers)
    done = cache_hits
    if progress_callback and cache_hits:
        progress_callback(done, total)

    fresh_rows: list[dict] = []
    if pending:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(analyze_pead2_ticker, t, m, min_mcap_cr=min_mcap_cr): t
                for t, m in pending
            }
            for future in as_completed(futures):
                result = future.result()
                if result:
                    ticker_key = safe_str(result.get("ticker")).upper()
                    result = _backfill_blob_from_legacy(
                        result,
                        legacy_by_ticker.get(ticker_key),
                    )
                    fresh_rows.append(result)
                    rows.append(result)
                done += 1
                if progress_callback:
                    progress_callback(done, total)
        if fresh_rows:
            save_pead2_cache(fresh_rows)

    if not rows:
        return {
            "candidates": pd.DataFrame(),
            "candidates_previous": pd.DataFrame(),
            "scanned": total,
            "hits": 0,
            "hits_previous": 0,
            "cache_hits": cache_hits,
        }

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
    }


__all__ = [
    "prepare_pead_universe",
    "run_pead2_scan",
    "run_pead2_recent_scan",
    "Pead2AbsoluteWeights",
]
