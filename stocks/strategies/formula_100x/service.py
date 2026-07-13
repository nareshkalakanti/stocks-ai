"""100X Formula scan — yfinance annual statements per ticker."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import yfinance as yf

from stocks.core.config import FORMULA_100X_MAX_WORKERS, yfinance_worker_count
from stocks.core.log_service import METRICS_ERROR, log_error
from stocks.core.text_utils import resolve_company_name, safe_str
from stocks.market.price_service import to_yfinance_symbol
from stocks.market.yfinance_limits import call_fast
from stocks.shared.links import attach_research_links
from stocks.market.company_profile import merge_company_profile
from stocks.strategies.formula_100x.strategy import evaluate_100x_formula
from stocks.strategies.pead.service import prepare_pead_universe
from stocks.strategies.pead2.technicals import _profile_from_info


def _cache_market_cap(
    ticker: str,
    market: str | None,
    symbol: str,
    info: dict,
) -> float | None:
    from stocks.core.database import save_market_cap_to_db

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


def _build_100x_snapshot(
    info: dict,
    *,
    price: float | None,
    market_cap_cr: float | None,
    ticker: str,
    market: str | None,
) -> dict:
    w52_low = info.get("fiftyTwoWeekLow")
    w52_high = info.get("fiftyTwoWeekHigh")
    low = float(w52_low) if w52_low is not None and not pd.isna(w52_low) else None
    high = float(w52_high) if w52_high is not None and not pd.isna(w52_high) else None

    growth = info.get("revenueGrowth") or info.get("earningsGrowth")
    cagr = None
    if growth is not None and not pd.isna(growth):
        cagr = round(float(growth) * 100, 2)

    snapshot = {
        "price": round(price, 2) if price is not None else None,
        "market_cap_cr": market_cap_cr,
        "cagr": cagr,
        "w52_low": round(low, 2) if low is not None else None,
        "w52_high": round(high, 2) if high is not None else None,
        "moving_averages": [],
        "price_trend": [],
        **_profile_from_info(info),
    }
    return merge_company_profile(snapshot, ticker, market)


def analyze_100x_ticker(
    ticker: str,
    market: str | None,
    *,
    min_mcap_cr: float | None = None,
) -> dict | None:
    symbol = to_yfinance_symbol(ticker, market)

    def _fetch() -> dict | None:
        yt = yf.Ticker(symbol)
        info = yt.info or {}
        market_cap_cr = _cache_market_cap(ticker, market, symbol, info)
        if (
            min_mcap_cr is not None
            and min_mcap_cr > 0
            and market_cap_cr is not None
            and market_cap_cr < min_mcap_cr
        ):
            return None

        metrics = evaluate_100x_formula(
            cashflow=yt.cashflow,
            financials=yt.financials,
            balance_sheet=yt.balance_sheet,
            info=info,
            market_cap_cr=market_cap_cr,
        )
        if metrics is None:
            return None

        price = info.get("regularMarketPrice") or info.get("currentPrice")
        price_val = float(price) if price is not None and not pd.isna(price) else None
        snapshot = _build_100x_snapshot(
            info,
            price=price_val,
            market_cap_cr=market_cap_cr,
            ticker=ticker,
            market=market,
        )

        row = {
            "ticker": safe_str(ticker).upper(),
            "market": safe_str(market) or None,
            "name": resolve_company_name(info.get("longName") or info.get("shortName"), ticker=ticker),
            "sector": safe_str(info.get("sector")) or None,
            "industry": safe_str(info.get("industry")) or None,
            "price": snapshot.get("price"),
            "market_cap_cr": market_cap_cr,
            "snapshot": snapshot,
            **metrics,
        }
        if snapshot.get("website"):
            row["website"] = snapshot["website"]
        if snapshot.get("long_description"):
            row["long_description"] = snapshot["long_description"]
        for key in ("company_sector", "company_industry", "headquarters", "employees"):
            if snapshot.get(key) is not None:
                row[key] = snapshot[key]
        return row

    def _log(exc: Exception) -> None:
        log_error(
            METRICS_ERROR,
            "100X fetch failed",
            ticker=ticker,
            symbol=symbol,
            error=str(exc),
        )

    return call_fast(_fetch, on_error=_log)


def run_100x_scan(
    universe: pd.DataFrame,
    *,
    min_mcap_cr: float | None = None,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> pd.DataFrame:
    if universe.empty:
        return pd.DataFrame()

    workers = yfinance_worker_count(len(universe), max_workers or FORMULA_100X_MAX_WORKERS)
    rows: list[dict] = []
    tickers = universe["ticker"].astype(str).tolist()
    markets = (
        universe["market"].astype(str).tolist()
        if "market" in universe.columns
        else [None] * len(tickers)
    )
    total = len(tickers)
    done = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                analyze_100x_ticker,
                ticker,
                market if market and market.lower() not in ("nan", "none", "") else None,
                min_mcap_cr=min_mcap_cr,
            ): ticker
            for ticker, market in zip(tickers, markets)
        }
        for fut in as_completed(futures):
            if should_stop and should_stop():
                break
            done += 1
            if progress_callback:
                progress_callback(done, total)
            try:
                row = fut.result()
            except Exception:
                continue
            if row:
                rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    meta_cols = [c for c in ("name", "market", "sector", "industry") if c in universe.columns]
    if meta_cols:
        meta = universe[["ticker", *meta_cols]].copy()
        meta["ticker"] = meta["ticker"].astype(str).str.upper()
        df = df.merge(meta, on="ticker", how="left", suffixes=("", "_u"))
        for col in meta_cols:
            ucol = f"{col}_u"
            if ucol in df.columns:
                df[col] = df[col].fillna(df[ucol])
                df = df.drop(columns=[ucol])
    df = df.sort_values(
        ["criteria_score", "cfo_ebit_pct", "ebt_capital_pct"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    return attach_research_links(df)


def prepare_100x_universe(
    filtered: pd.DataFrame,
    *,
    cap_tier_id: str,
) -> tuple[pd.DataFrame, int, int]:
    return prepare_pead_universe(filtered, cap_tier_id=cap_tier_id)
