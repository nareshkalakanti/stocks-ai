"""Fetch annual financials and run valuation framework per ticker."""

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
from stocks.strategies.formula_100x.strategy import _to_inr_cr
from stocks.strategies.pead.service import prepare_pead_universe
from stocks.strategies.valuation_formula.strategy import REVENUE_FIELDS, _first_row
from stocks.strategies.valuation_framework.strategy import (
    FrameworkAssumptions,
    annual_profit_and_loss,
    run_valuation_framework,
    scan_row_from_result,
)


def _latest_annual_sales_cr(financials: pd.DataFrame | None) -> float | None:
    rev = _first_row(financials, REVENUE_FIELDS)
    if rev is None or rev.empty:
        return None
    latest = float(rev.sort_index().iloc[-1])
    if pd.isna(latest):
        return None
    return _to_inr_cr(latest)


def analyze_valuation_ticker(
    ticker: str,
    market: str | None,
    *,
    assumptions: FrameworkAssumptions | None = None,
    min_mcap_cr: float = 0.0,
) -> dict | None:
    symbol = to_yfinance_symbol(ticker, market)

    def _fetch() -> dict | None:
        yt = yf.Ticker(symbol)
        info = yt.info or {}
        financials = yt.financials
        sales_cr = _latest_annual_sales_cr(financials)
        if sales_cr is None or sales_cr <= 0:
            return None

        market_cap = info.get("marketCap")
        if market_cap is None or pd.isna(market_cap):
            return None
        market_cap_cr = round(float(market_cap) / 1e7, 1)
        if min_mcap_cr > 0 and market_cap_cr < min_mcap_cr:
            return None

        base = assumptions or FrameworkAssumptions(
            base_year=pd.Timestamp.now().year,
            current_sales_cr=sales_cr,
            market_cap_cr=market_cap_cr,
        )
        if assumptions is not None:
            base = FrameworkAssumptions(
                base_year=assumptions.base_year,
                current_sales_cr=sales_cr,
                market_cap_cr=market_cap_cr,
                sales_multiple=assumptions.sales_multiple,
                discount_rate_pct=assumptions.discount_rate_pct,
                projection_years=assumptions.projection_years,
                growth_rates_pct=assumptions.growth_rates_pct,
            )

        result = run_valuation_framework(base)
        pl = annual_profit_and_loss(financials)
        row = scan_row_from_result(
            safe_str(ticker).upper(),
            resolve_company_name(ticker, info.get("longName") or info.get("shortName")),
            result,
            market=market,
        )
        row["pl_rows"] = pl
        return row

    def _log(exc: Exception) -> None:
        log_error(
            METRICS_ERROR,
            "Valuation framework fetch failed",
            ticker=ticker,
            symbol=symbol,
            error=str(exc),
        )

    return call_fast(_fetch, on_error=_log)


def run_valuation_scan(
    universe: pd.DataFrame,
    *,
    assumptions: FrameworkAssumptions | None = None,
    min_mcap_cr: float = 0.0,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> pd.DataFrame:
    if universe.empty:
        return pd.DataFrame()

    workers = yfinance_worker_count(max_workers or FORMULA_100X_MAX_WORKERS)
    tickers = list(universe.itertuples(index=False))
    total = len(tickers)
    rows: list[dict] = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                analyze_valuation_ticker,
                safe_str(getattr(row, "ticker", "")),
                safe_str(getattr(row, "market", "")) or None,
                assumptions=assumptions,
                min_mcap_cr=min_mcap_cr,
            ): row
            for row in tickers
        }
        done = 0
        for fut in as_completed(futures):
            done += 1
            if progress_callback:
                progress_callback(done, total)
            try:
                item = fut.result()
            except Exception:
                continue
            if item:
                rows.append(item)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    return attach_research_links(df)


def prepare_valuation_universe(
    filtered: pd.DataFrame,
    *,
    cap_tier_id: str | None,
) -> tuple[pd.DataFrame, int, int]:
    return prepare_pead_universe(filtered, cap_tier_id=cap_tier_id)
