"""PEAD data fetch (yfinance) + SQLite cache + scan orchestration."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

import pandas as pd
import yfinance as yf

from stocks.core.config import (
    DEFAULT_CAP_TIER,
    EARNINGS_JUMP_MIN,
    EARNINGS_MAX_STREAK,
    EARNINGS_MIN_GAP_PCT,
    EARNINGS_MIN_MARGIN_ROOM_PP,
    EARNINGS_MIN_VOL_RATIO,
    EARNINGS_REQUIRE_PRICE,
    EARNINGS_TRAIL_QUARTERS,
    MIN_MARKET_CAP_CR,
    PEAD_CACHE_HOURS,
    YFINANCE_REQUEST_DELAY,
    yfinance_worker_count,
)
from stocks.core.database import get_connection, init_db, save_market_cap_to_db
from stocks.strategies.earnings.strategy import (
    EPS_FIELDS,
    NET_INCOME_FIELDS,
    OP_FIELDS,
    REVENUE_FIELDS,
    EarningsScanParams,
    _sorted_series,
    classify_signal,
    composite_score,
    evaluate_fundamentals,
    evaluate_price_volume,
    rank_earnings_results,
)
from stocks.strategies.earnings.quality import passes_earnings_quality
from stocks.market.fundamentals_service import filter_listings_by_cap_tier
from stocks.core.log_service import METRICS_ERROR, log_error
from stocks.market.price_service import to_yfinance_symbol
from stocks.scans.results_utils import analysis_universe
from stocks.shared.links import attach_research_links
from stocks.core.text_utils import safe_str
from stocks.market.yfinance_limits import call_fast, call_throttled
from stocks.strategies.pead2.quarters import build_quarter_panel, sanitize_quarter_panel
from stocks.strategies.pead2.strategy import compute_forward_pe, compute_trailing_pe
from stocks.strategies.pead2.technicals import build_price_snapshot

_EPS_FIELDS = (
    "Diluted EPS",
    "Basic EPS",
    "Diluted EPS Including Extra Items",
    "Basic EPS Including Extra Items",
)


def _utc_now() -> str:
    from stocks.core.database import _utc_now as db_now

    return db_now()


def _is_fresh(fetched_at: str | None, max_hours: int) -> bool:
    from stocks.core.database import _is_fresh as db_fresh

    return db_fresh(fetched_at, max_hours)


def _eps_row(quarterly_income: pd.DataFrame) -> pd.Series | None:
    if quarterly_income is None or quarterly_income.empty:
        return None
    for field in _EPS_FIELDS:
        if field in quarterly_income.index:
            series = quarterly_income.loc[field, :]
            if series is not None and not series.empty:
                return series
    return None


def _ts_naive(ts: pd.Timestamp | str) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if getattr(t, "tzinfo", None) is not None:
        t = t.tz_convert(None)
    return t.normalize()


def estimate_result_date(
    yt: yf.Ticker,
    quarter_end: pd.Timestamp,
    *,
    result_lag_days: int | None = None,
    ticker: str | None = None,
    market: str | None = None,
    as_of: pd.Timestamp | None = None,
) -> pd.Timestamp:
    """Earnings date — NSE filing, then Yahoo calendar in [q_end, today], else q_end + lag."""
    from stocks.core.config import PEAD_RESULT_LAG_DAYS

    lag = PEAD_RESULT_LAG_DAYS if result_lag_days is None else result_lag_days
    q_end = _ts_naive(quarter_end)
    today = _ts_naive(as_of or pd.Timestamp.now())
    fallback = min(q_end + timedelta(days=lag), today)

    if ticker:
        from stocks.market.nse_result_dates import nse_result_date_for_quarter

        nse_date = nse_result_date_for_quarter(
            ticker,
            q_end,
            market=market,
            as_of=today,
        )
        if nse_date is not None:
            return _ts_naive(nse_date)

    try:
        earnings_dates = yt.get_earnings_dates(limit=24)
    except Exception:
        return fallback
    if earnings_dates is None or earnings_dates.empty:
        return fallback

    candidates: list[pd.Timestamp] = []
    for ed in earnings_dates.index:
        ed_ts = _ts_naive(ed)
        if ed_ts > today:
            continue
        delta = (ed_ts.date() - q_end.date()).days
        if 0 <= delta <= 90:
            candidates.append(ed_ts)
    if candidates:
        return max(candidates)

    # Wider match — announced after quarter end but outside 90d window.
    wide = [
        _ts_naive(ed)
        for ed in earnings_dates.index
        if q_end <= _ts_naive(ed) <= today
    ]
    if wide:
        return max(wide)

    return fallback


def _estimate_result_date_legacy(quarter_end: pd.Timestamp) -> pd.Timestamp:
    return quarter_end + timedelta(days=35)


def fetch_quarterly_earnings(ticker: str, market: str | None) -> list[dict]:
    """Fetch quarterly EPS rows for one ticker via yfinance."""
    symbol = to_yfinance_symbol(ticker, market)
    rows: list[dict] = []

    def _fetch() -> list[dict]:
        yt = yf.Ticker(symbol)
        income = yt.quarterly_income_stmt
        eps_series = _eps_row(income)
        if eps_series is None:
            return []

        earnings_dates = pd.DataFrame()
        try:
            earnings_dates = yt.get_earnings_dates(limit=12)
        except Exception:
            pass

        out: list[dict] = []
        for quarter_end, eps in eps_series.items():
            if eps is None or pd.isna(eps):
                continue
            q_end = pd.Timestamp(quarter_end)
            result_date = _estimate_result_date_legacy(q_end)
            if earnings_dates is not None and not earnings_dates.empty:
                for ed in earnings_dates.index:
                    ed_ts = pd.Timestamp(ed)
                    if abs((ed_ts.date() - q_end.date()).days) <= 60 and ed_ts >= q_end:
                        result_date = ed_ts
                        break
            out.append(
                {
                    "ticker": safe_str(ticker).upper(),
                    "quarter_end": q_end.strftime("%Y-%m-%d"),
                    "result_date": result_date.strftime("%Y-%m-%d"),
                    "eps": float(eps),
                }
            )
        return out

    def _log(exc: Exception) -> None:
        log_error(
            METRICS_ERROR,
            "PEAD earnings fetch failed",
            ticker=ticker,
            symbol=symbol,
            error=str(exc),
        )

    result = call_throttled(_fetch, delay=YFINANCE_REQUEST_DELAY, on_error=_log)
    return result or rows


def fetch_daily_prices(ticker: str, market: str | None, *, period: str = "2y") -> list[dict]:
    symbol = to_yfinance_symbol(ticker, market)
    rows: list[dict] = []

    def _fetch() -> list[dict]:
        hist = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=True)
        if hist is None or hist.empty:
            return []
        out: list[dict] = []
        for dt, row in hist.iterrows():
            close = row.get("Close")
            if close is None or pd.isna(close):
                continue
            out.append(
                {
                    "ticker": safe_str(ticker).upper(),
                    "date": pd.Timestamp(dt).strftime("%Y-%m-%d"),
                    "close": float(close),
                }
            )
        return out

    def _log(exc: Exception) -> None:
        log_error(
            METRICS_ERROR,
            "PEAD price fetch failed",
            ticker=ticker,
            symbol=symbol,
            error=str(exc),
        )

    result = call_throttled(_fetch, delay=YFINANCE_REQUEST_DELAY, on_error=_log)
    return result or rows


def save_pead_earnings(rows: list[dict]) -> None:
    if not rows:
        return
    init_db()
    now = _utc_now()
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO pead_earnings (ticker, quarter_end, result_date, eps, fetched_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(ticker, quarter_end) DO UPDATE SET
                result_date=excluded.result_date,
                eps=excluded.eps,
                fetched_at=excluded.fetched_at
            """,
            [
                (r["ticker"], r["quarter_end"], r["result_date"], r["eps"], now)
                for r in rows
            ],
        )


def save_pead_prices(rows: list[dict]) -> None:
    if not rows:
        return
    init_db()
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO pead_prices (ticker, date, close)
            VALUES (?, ?, ?)
            ON CONFLICT(ticker, date) DO UPDATE SET close=excluded.close
            """,
            [(r["ticker"], r["date"], r["close"]) for r in rows],
        )


def _stale_earnings_tickers(tickers: list[str]) -> list[str]:
    if not tickers:
        return []
    init_db()
    placeholders = ",".join("?" * len(tickers))
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT ticker, MAX(fetched_at) AS fetched_at
            FROM pead_earnings
            WHERE ticker IN ({placeholders})
            GROUP BY ticker
            """,
            tickers,
        ).fetchall()
    fresh = {r["ticker"] for r in rows if _is_fresh(r["fetched_at"], PEAD_CACHE_HOURS)}
    return [t for t in tickers if t not in fresh]


def _needs_prices(tickers: list[str]) -> list[str]:
    if not tickers:
        return []
    init_db()
    placeholders = ",".join("?" * len(tickers))
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT ticker, COUNT(*) AS n
            FROM pead_prices
            WHERE ticker IN ({placeholders})
            GROUP BY ticker
            """,
            tickers,
        ).fetchall()
    have = {r["ticker"] for r in rows if r["n"] >= 120}
    return [t for t in tickers if t not in have]


def sync_pead_data(
    tickers: list[str],
    markets: list[str | None],
    *,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> tuple[int, int]:
    """Fetch missing earnings + prices into SQLite. Returns (earnings_rows, price_rows)."""
    ticker_market = dict(zip(tickers, markets))

    stale = _stale_earnings_tickers(tickers)
    need_prices = _needs_prices(tickers)
    total = len(stale) + len(need_prices)
    workers = yfinance_worker_count(total, max_workers)
    done = 0
    earnings_count = 0
    price_count = 0

    if stale:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(fetch_quarterly_earnings, t, ticker_market.get(t)): t
                for t in stale
            }
            for future in as_completed(futures):
                rows = future.result()
                if rows:
                    save_pead_earnings(rows)
                    earnings_count += len(rows)
                done += 1
                if progress_callback:
                    progress_callback(done, total, "earnings")

    if need_prices:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(fetch_daily_prices, t, ticker_market.get(t)): t
                for t in need_prices
            }
            for future in as_completed(futures):
                rows = future.result()
                if rows:
                    save_pead_prices(rows)
                    price_count += len(rows)
                done += 1
                if progress_callback:
                    progress_callback(done, total, "prices")

    return earnings_count, price_count


def load_earnings_data(tickers: list[str] | None = None) -> pd.DataFrame:
    init_db()
    with get_connection() as conn:
        if tickers:
            placeholders = ",".join("?" * len(tickers))
            rows = conn.execute(
                f"""
                SELECT ticker AS symbol, quarter_end, result_date, eps
                FROM pead_earnings
                WHERE ticker IN ({placeholders})
                ORDER BY symbol, quarter_end
                """,
                tickers,
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT ticker AS symbol, quarter_end, result_date, eps
                FROM pead_earnings
                ORDER BY symbol, quarter_end
                """
            ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows])
    df["quarter_end"] = pd.to_datetime(df["quarter_end"])
    df["result_date"] = pd.to_datetime(df["result_date"])
    return df


def load_prices_data(tickers: list[str] | None = None) -> pd.DataFrame:
    init_db()
    with get_connection() as conn:
        if tickers:
            placeholders = ",".join("?" * len(tickers))
            rows = conn.execute(
                f"""
                SELECT ticker AS symbol, date, close
                FROM pead_prices
                WHERE ticker IN ({placeholders})
                ORDER BY symbol, date
                """,
                tickers,
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT ticker AS symbol, date, close
                FROM pead_prices
                ORDER BY symbol, date
                """
            ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows])
    df["date"] = pd.to_datetime(df["date"])
    return df


def _enrich_pead(df: pd.DataFrame, meta: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.rename(columns={"symbol": "ticker"})
    if not meta.empty:
        out = out.merge(
            meta[["ticker", "name", "market", "sector"]],
            on="ticker",
            how="left",
        )
    return attach_research_links(out)


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


def analyze_pead_stock(
    ticker: str,
    market: str | None,
    *,
    params: EarningsScanParams | None = None,
) -> dict | None:
    """PEAD 1 — Earnings Explosion: rev/op/EPS burst · margin · gap+volume."""
    symbol = to_yfinance_symbol(ticker, market)
    scan = params or EarningsScanParams(
        jump_min=EARNINGS_JUMP_MIN,
        trail_quarters=EARNINGS_TRAIL_QUARTERS,
        max_streak=EARNINGS_MAX_STREAK,
        min_margin_room_pp=EARNINGS_MIN_MARGIN_ROOM_PP,
        min_gap_pct=EARNINGS_MIN_GAP_PCT,
        min_vol_ratio=EARNINGS_MIN_VOL_RATIO,
        require_price=EARNINGS_REQUIRE_PRICE,
    )

    def _fetch() -> dict | None:
        yt = yf.Ticker(symbol)
        info = yt.info or {}
        market_cap_cr = _cache_market_cap(ticker, market, symbol, info)
        if market_cap_cr is not None and market_cap_cr < MIN_MARKET_CAP_CR:
            return None

        income = yt.quarterly_income_stmt
        revenue = _sorted_series(income, REVENUE_FIELDS)
        op_profit = _sorted_series(income, OP_FIELDS)
        eps = _sorted_series(income, EPS_FIELDS)
        net_profit = _sorted_series(income, NET_INCOME_FIELDS)
        if revenue is None or op_profit is None or eps is None or net_profit is None:
            return None
        if len(revenue) < scan.trail_quarters + 1:
            return None

        ok, _reason = passes_earnings_quality(net_profit, eps)
        if not ok:
            return None

        fund = evaluate_fundamentals(revenue, op_profit, eps, scan)
        if not fund["passed_fundamental"]:
            return None

        quarter_end = pd.Timestamp(revenue.index[-1])
        result_date = estimate_result_date(yt, quarter_end, ticker=ticker, market=market)
        # 2y history matches PEAD 2 expand (MAs / 52w); also feeds gap+volume gate.
        hist = yt.history(period="2y", interval="1d", auto_adjust=True)
        if hist is None:
            hist = pd.DataFrame()
        price = evaluate_price_volume(hist, result_date, scan)
        signal = classify_signal(fund, price, require_price=scan.require_price)

        price_val = None
        if not hist.empty and "Close" in hist.columns:
            closes = hist["Close"].dropna()
            if not closes.empty:
                price_val = float(closes.iloc[-1])

        pe_ratio = compute_trailing_pe(price_val, eps, info)
        forward_pe = compute_forward_pe(price_val, eps, info)
        quarters = sanitize_quarter_panel(
            build_quarter_panel(revenue, op_profit, net_profit, eps)
        )
        snapshot = build_price_snapshot(
            info,
            hist,
            revenue,
            price=price_val,
            pe_ratio=pe_ratio,
            forward_pe=forward_pe,
        )

        float_shares = info.get("floatShares")
        row = {
            "ticker": safe_str(ticker).upper(),
            "market": safe_str(market) or None,
            "signal": signal,
            "quarter_end": quarter_end.strftime("%Y-%m-%d"),
            **fund,
            **price,
            "market_cap_cr": market_cap_cr,
            "float_shares": float(float_shares) if float_shares else None,
            "price": round(price_val, 2) if price_val is not None else None,
            "pe_ratio": pe_ratio,
            "forward_pe": forward_pe,
        }
        if quarters:
            row["quarters"] = quarters
        if snapshot:
            row["snapshot"] = snapshot
        row["score"] = composite_score(row)
        return row

    def _log(exc: Exception) -> None:
        log_error(
            METRICS_ERROR,
            "PEAD 1 screen fetch failed",
            ticker=ticker,
            symbol=symbol,
            error=str(exc),
        )

    return call_fast(_fetch, on_error=_log)


def run_pead_scan(
    universe: pd.DataFrame,
    *,
    params: EarningsScanParams | None = None,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict:
    """Scan universe for PEAD 1 (Earnings Explosion) candidates."""
    if universe.empty:
        return {
            "buy": pd.DataFrame(),
            "fundamental": pd.DataFrame(),
            "candidates": pd.DataFrame(),
            "scanned": 0,
            "hits": 0,
        }

    scan_params = params or EarningsScanParams(
        jump_min=EARNINGS_JUMP_MIN,
        trail_quarters=EARNINGS_TRAIL_QUARTERS,
        max_streak=EARNINGS_MAX_STREAK,
        min_margin_room_pp=EARNINGS_MIN_MARGIN_ROOM_PP,
        min_gap_pct=EARNINGS_MIN_GAP_PCT,
        min_vol_ratio=EARNINGS_MIN_VOL_RATIO,
        require_price=EARNINGS_REQUIRE_PRICE,
    )

    tickers = universe["ticker"].tolist()
    markets = universe["market"].tolist() if "market" in universe.columns else [None] * len(tickers)
    workers = yfinance_worker_count(len(tickers), max_workers)
    meta = universe[["ticker", "name", "market", "sector"]].drop_duplicates("ticker")

    rows: list[dict] = []
    total = len(tickers)
    done = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(analyze_pead_stock, t, m, params=scan_params): t
            for t, m in zip(tickers, markets)
        }
        for future in as_completed(futures):
            result = future.result()
            if result:
                rows.append(result)
            done += 1
            if progress_callback:
                progress_callback(done, total)

    if rows and "sector" in meta.columns:
        sector_counts: dict[str, int] = {}
        for row in rows:
            match = meta[meta["ticker"] == row["ticker"]]
            sector = str(match.iloc[0]["sector"]) if not match.empty else ""
            row["sector"] = sector
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
        for row in rows:
            row["sector_peers"] = sector_counts.get(row.get("sector", ""), 1)

    buy, fundamental = rank_earnings_results(rows)

    def _enrich(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        out = df.merge(meta, on="ticker", how="left", suffixes=("", "_meta"))
        for col in ("name", "market", "sector"):
            meta_col = f"{col}_meta"
            if meta_col in out.columns:
                out[col] = out[col].fillna(out[meta_col])
                out = out.drop(columns=[meta_col])
        return attach_research_links(out)

    buy = _enrich(buy)
    fundamental = _enrich(fundamental)
    candidates = pd.concat([buy, fundamental], ignore_index=True) if not buy.empty or not fundamental.empty else pd.DataFrame()

    return {
        "buy": buy,
        "fundamental": fundamental,
        "candidates": candidates,
        "scanned": total,
        "hits": len(rows),
        "params": scan_params,
    }


def prepare_pead_universe(
    stocks: pd.DataFrame,
    *,
    cap_tier_id: str = DEFAULT_CAP_TIER,
) -> tuple[pd.DataFrame, int, int]:
    """Filter listings → universe; cap tier optional (default All caps = no mcap floor)."""
    universe = analysis_universe(stocks, limit=0)
    cap_excluded = 0

    tier_id = cap_tier_id if cap_tier_id not in ("", None) else "all"
    if tier_id not in ("all",):
        _listings, universe, cap_excluded, _missing = filter_listings_by_cap_tier(
            stocks,
            tier_id,
        )

    return universe, cap_excluded, 0
