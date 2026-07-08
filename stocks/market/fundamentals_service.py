from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import yfinance as yf

from stocks.core.config import MIN_MARKET_CAP_CR, SCAN_MCAP_PREFETCH_LIMIT, yfinance_worker_count
from stocks.core.database import load_fundamentals_cache, load_market_cap_from_db, save_fundamentals_cache
from stocks.core.log_service import METRICS_ERROR, log_error
from stocks.market.price_service import to_yfinance_symbol
from stocks.scans.results_utils import analysis_universe
from stocks.core.text_utils import safe_str
from stocks.market.yfinance_limits import call_fast


def _safe_float(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _with_retry(fn, *, ticker: str, symbol: str):
    def _log(exc: Exception) -> None:
        log_error(
            METRICS_ERROR,
            "Failed to fetch fundamentals",
            ticker=ticker,
            symbol=symbol,
            error=str(exc),
        )

    return call_fast(
        fn,
        on_error=_log,
    )


from stocks.strategies.earnings.strategy import EBIDT_FIELDS as _OP_FIELDS


def _to_inr_cr(value: float | None) -> float | None:
    if value is None:
        return None
    if abs(value) >= 1e5:
        return round(value / 1e7, 2)
    return round(value, 2)


def compute_roce_metrics(
    inc: pd.DataFrame | None,
    bs: pd.DataFrame | None,
) -> dict:
    """ROCE = operating profit / capital employed; capital employed = assets − current liabilities."""
    op_profit = None
    if inc is not None and not inc.empty:
        for row in _OP_FIELDS:
            if row in inc.index:
                op_profit = _safe_float(inc.loc[row, inc.columns[0]])
                break

    total_assets = None
    current_liabilities = None
    if bs is not None and not bs.empty:
        if "Total Assets" in bs.index:
            total_assets = _safe_float(bs.loc["Total Assets", bs.columns[0]])
        if "Current Liabilities" in bs.index:
            current_liabilities = _safe_float(bs.loc["Current Liabilities", bs.columns[0]])

    capital_employed = None
    if total_assets is not None and current_liabilities is not None:
        capital_employed = total_assets - current_liabilities
        if capital_employed <= 0:
            capital_employed = None

    roce_pct = None
    if op_profit is not None and capital_employed is not None:
        roce_pct = round((op_profit / capital_employed) * 100, 2)

    return {
        "operating_profit_cr": _to_inr_cr(op_profit),
        "total_assets_cr": _to_inr_cr(total_assets),
        "current_liabilities_cr": _to_inr_cr(current_liabilities),
        "capital_employed_cr": _to_inr_cr(capital_employed),
        "roce_pct": roce_pct,
    }


def compute_ev_ebitda_metrics(info: dict | None) -> dict:
    """Screener-style EV/EBITDA from yfinance info (enterpriseToEbitda)."""
    info = info or {}
    ev_ebitda = _safe_float(info.get("enterpriseToEbitda"))
    market_cap = _safe_float(info.get("marketCap"))
    pe = _safe_float(info.get("trailingPE"))
    return {
        "ev_ebitda": round(ev_ebitda, 2) if ev_ebitda is not None else None,
        "market_cap_cr": round(market_cap / 1e7, 1) if market_cap is not None else None,
        "pe": round(pe, 1) if pe is not None else None,
    }


def _compute_roce_pct(
    yt: yf.Ticker,
    info: dict,
    *,
    ticker: str,
    symbol: str,
) -> float | None:
    def _from_financials():
        return compute_roce_metrics(yt.financials, yt.balance_sheet).get("roce_pct")

    roce = _with_retry(_from_financials, ticker=ticker, symbol=symbol)
    if roce is not None:
        return roce

    roe = _safe_float(info.get("returnOnEquity"))
    if roe is not None:
        return round(roe * 100, 2)
    return None


def _fetch_single_fundamentals(ticker: str, market: str | None) -> dict:
    symbol = to_yfinance_symbol(ticker, market)
    row: dict = {
        "ticker": safe_str(ticker).upper(),
        "yf_symbol": symbol,
        "roce_pct": None,
        "ev_ebitda": None,
        "debt_to_equity": None,
        "current_ratio": None,
        "book_value": None,
        "price": None,
        "market_cap_cr": None,
    }

    def _load_info():
        return yf.Ticker(symbol).info or {}

    info = _with_retry(_load_info, ticker=ticker, symbol=symbol)
    if not info:
        return row

    yt = yf.Ticker(symbol)
    row["roce_pct"] = _compute_roce_pct(yt, info, ticker=ticker, symbol=symbol)

    ev_ebitda = _safe_float(info.get("enterpriseToEbitda"))
    if ev_ebitda is not None:
        row["ev_ebitda"] = round(ev_ebitda, 2)

    dte = _safe_float(info.get("debtToEquity"))
    if dte is not None:
        row["debt_to_equity"] = round(dte, 2)

    cr = _safe_float(info.get("currentRatio"))
    if cr is not None:
        row["current_ratio"] = round(cr, 2)

    bv = _safe_float(info.get("bookValue"))
    if bv is not None:
        row["book_value"] = round(bv, 2)

    price = _safe_float(info.get("currentPrice") or info.get("regularMarketPrice"))
    if price is not None:
        row["price"] = round(price, 2)

    market_cap = _safe_float(info.get("marketCap"))
    if market_cap is not None:
        row["market_cap_cr"] = round(market_cap / 1e7, 1)

    return row


def fetch_fundamentals(
    stocks: pd.DataFrame,
    *,
    max_workers: int | None = None,
    progress_callback=None,
) -> pd.DataFrame:
    """Fetch ROCE, EV/EBITDA, and balance-sheet ratios via yfinance (cached in SQLite per ticker)."""
    if stocks.empty or "ticker" not in stocks.columns:
        return pd.DataFrame()

    universe = analysis_universe(stocks, limit=0)
    markets = (
        universe["market"].tolist() if "market" in universe.columns else [None] * len(universe)
    )
    tickers = universe["ticker"].tolist()
    workers = yfinance_worker_count(len(tickers), max_workers)
    total = len(tickers)

    cached_df = load_fundamentals_cache(tickers)
    cached_tickers: set[str] = set()
    if not cached_df.empty:
        cached_tickers = set(cached_df["ticker"].astype(str))

    missing = [(t, m) for t, m in zip(tickers, markets) if t not in cached_tickers]
    fetched_rows: list[dict] = []

    if missing:
        done = sum(1 for t in tickers if t in cached_tickers)
        if progress_callback:
            progress_callback(done, total)

        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {
                pool.submit(_fetch_single_fundamentals, ticker, market): (ticker, market)
                for ticker, market in missing
            }
            for future in as_completed(futures):
                ticker, market = futures[future]
                row = future.result()
                fetched_rows.append(row)
                save_fundamentals_cache(pd.DataFrame([row]), [market])
                done += 1
                if progress_callback:
                    progress_callback(done, total)

        if fetched_rows:
            fetched_df = pd.DataFrame(fetched_rows)
            if not cached_df.empty:
                metrics = pd.concat([cached_df, fetched_df], ignore_index=True)
            else:
                metrics = fetched_df
        else:
            metrics = cached_df
    else:
        metrics = cached_df

    if metrics.empty:
        return pd.DataFrame()

    meta = universe[["ticker", "name", "market", "sector"]].drop_duplicates(
        subset="ticker", keep="first"
    )
    # Keep listing market from meta; metrics also carries market and would collide on merge.
    metric_cols = [c for c in metrics.columns if c not in {"ticker", "market"}]
    return meta.merge(metrics[["ticker", *metric_cols]], on="ticker", how="left")


def fundamentals_cache_status(tickers: list[str]) -> dict[str, int]:
    """How many tickers already have fresh fundamentals in SQLite."""
    total = len(tickers)
    if not total:
        return {"cached": 0, "missing": 0, "total": 0}
    cached_df = load_fundamentals_cache(tickers)
    cached = len(cached_df) if not cached_df.empty else 0
    return {"cached": cached, "missing": total - cached, "total": total}


def apply_cap_tier_filter(
    df: pd.DataFrame,
    tier_id: str = "all",
) -> tuple[pd.DataFrame, int]:
    """Filter by market-cap tier (INR Crores). Returns (filtered_df, excluded_count)."""
    if df.empty or "market_cap_cr" not in df.columns or tier_id in ("all", ""):
        return df, 0

    from stocks.core.config import CAP_TIERS

    tier = next((t for t in CAP_TIERS if t["id"] == tier_id), None)
    if tier is None:
        return df, 0

    lo = tier["min"]
    hi = tier["max"]
    cap = pd.to_numeric(df["market_cap_cr"], errors="coerce")
    mask = cap.notna()
    if lo is not None:
        mask &= cap >= float(lo)
    if hi is not None:
        mask &= cap < float(hi)

    kept = df[mask].copy()
    return kept, len(df) - len(kept)


def cap_tier_label(tier_id: str) -> str:
    from stocks.core.config import CAP_TIERS

    tier = next((t for t in CAP_TIERS if t["id"] == tier_id), None)
    return str(tier["label"]) if tier else "All caps"


def filter_listings_by_cap_tier(
    stocks: pd.DataFrame,
    tier_id: str = "all",
    *,
    max_workers: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, int, int]:
    """Apply cap-tier filter. Returns (listings, universe, excluded, missing_cap_count)."""
    universe = analysis_universe(stocks, limit=0)
    if tier_id in ("all", "") or universe.empty:
        return stocks, universe, 0, 0

    universe = attach_market_cap_for_scan_filter(
        universe,
        max_workers=max_workers,
    )

    missing_cap = 0
    if "market_cap_cr" in universe.columns:
        missing_cap = int(universe["market_cap_cr"].isna().sum())

    tier_universe, excluded = apply_cap_tier_filter(universe, tier_id)
    if tier_universe.empty:
        return stocks.iloc[0:0], tier_universe, excluded, missing_cap

    tickers = set(tier_universe["ticker"].astype(str))
    listings = stocks[stocks["ticker"].astype(str).isin(tickers)].copy()
    return listings, tier_universe, excluded, missing_cap


def attach_market_cap_for_scan_filter(
    universe: pd.DataFrame,
    *,
    max_workers: int | None = None,
    prefetch_limit: int | None = None,
) -> pd.DataFrame:
    """Merge market_cap_cr from SQLite cache; bulk-fetch only for small universes."""
    if universe.empty or "market_cap_cr" in universe.columns:
        return universe

    tickers = universe["ticker"].tolist()
    markets = universe["market"].tolist() if "market" in universe.columns else [None] * len(tickers)
    ticker_market = dict(zip(tickers, markets))

    cached = load_market_cap_from_db(tickers)
    out = universe
    if not cached.empty:
        merge_cols = ["ticker", "market_cap_cr"]
        out = out.merge(
            cached[merge_cols].drop_duplicates("ticker"),
            on="ticker",
            how="left",
        )

    limit = prefetch_limit if prefetch_limit is not None else SCAN_MCAP_PREFETCH_LIMIT
    cached_tickers = set(cached["ticker"].astype(str)) if not cached.empty else set()
    missing = [t for t in tickers if t not in cached_tickers]
    if not missing or len(tickers) > limit:
        return out

    from stocks.market.price_service import fetch_stock_metrics

    fetched = fetch_stock_metrics(
        missing,
        [ticker_market[t] for t in missing],
        use_cache=True,
        max_workers=yfinance_worker_count(len(missing), max_workers),
    )
    if fetched.empty or "market_cap_cr" not in fetched.columns:
        return out

    cap_df = pd.concat(
        [
            cached[["ticker", "market_cap_cr"]] if not cached.empty else pd.DataFrame(),
            fetched[["ticker", "market_cap_cr"]],
        ],
        ignore_index=True,
    ).drop_duplicates("ticker")
    if "market_cap_cr" in out.columns:
        out = out.drop(columns=["market_cap_cr"])
    return out.merge(cap_df, on="ticker", how="left")


def apply_market_cap_filter(
    df: pd.DataFrame,
    *,
    min_cr: float | None = None,
) -> tuple[pd.DataFrame, int]:
    """Keep only stocks with market cap >= min_cr (Crores). Returns (filtered_df, excluded_count)."""
    if df.empty or "market_cap_cr" not in df.columns:
        return df, 0

    from stocks.core.config import MIN_MARKET_CAP_CR

    floor = MIN_MARKET_CAP_CR if min_cr is None else min_cr
    if floor <= 0:
        return df, 0

    cap = pd.to_numeric(df["market_cap_cr"], errors="coerce")
    kept = df[cap.notna() & (cap >= floor)].copy()
    excluded = len(df) - len(kept)
    return kept, excluded


def rank_by_roce(df: pd.DataFrame, *, top_n: int = 0) -> pd.DataFrame:
    """Higher ROCE = stronger capital efficiency (rank 1 = best)."""
    if df.empty or "roce_pct" not in df.columns:
        return df
    ranked = df[df["roce_pct"].notna()].copy()
    ranked = ranked.sort_values("roce_pct", ascending=False)
    ranked.insert(0, "rank", range(1, len(ranked) + 1))
    if top_n and top_n > 0:
        ranked = ranked.head(top_n)
    return ranked.reset_index(drop=True)


def rank_by_ev_ebitda(df: pd.DataFrame, *, top_n: int = 0) -> pd.DataFrame:
    """Lower EV/EBITDA = cheaper valuation (rank 1 = best value)."""
    if df.empty or "ev_ebitda" not in df.columns:
        return df
    ranked = df[(df["ev_ebitda"].notna()) & (df["ev_ebitda"] > 0)].copy()
    ranked = ranked.sort_values("ev_ebitda", ascending=True)
    ranked.insert(0, "rank", range(1, len(ranked) + 1))
    if top_n and top_n > 0:
        ranked = ranked.head(top_n)
    return ranked.reset_index(drop=True)


def rank_by_composite(df: pd.DataFrame, *, top_n: int = 0) -> pd.DataFrame:
    """50% ROCE strength + 50% EV/EBITDA value (percentile ranks)."""
    if df.empty:
        return df

    eligible = df[
        df["roce_pct"].notna() & df["ev_ebitda"].notna() & (df["ev_ebitda"] > 0)
    ].copy()
    if eligible.empty:
        return eligible

    eligible["roce_score"] = eligible["roce_pct"].rank(pct=True, method="average") * 100
    eligible["value_score"] = (1 - eligible["ev_ebitda"].rank(pct=True, method="average")) * 100
    eligible["composite_score"] = round(
        0.5 * eligible["roce_score"] + 0.5 * eligible["value_score"],
        2,
    )
    ranked = eligible.sort_values("composite_score", ascending=False)
    ranked.insert(0, "rank", range(1, len(ranked) + 1))
    if top_n and top_n > 0:
        ranked = ranked.head(top_n)
    return ranked.reset_index(drop=True)
