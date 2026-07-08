"""12-month price momentum with 1-month lag (Google Finance / stock-analysis style)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import yfinance as yf

from stocks.core.config import YFINANCE_REQUEST_DELAY
from stocks.core.text_utils import safe_str
from stocks.market.price_service import to_yfinance_symbol
from stocks.market.yfinance_limits import call_throttled

LOOKBACK_1Y = 395  # ~1 year of trading days
LOOKBACK_1M = 30   # ~1 month of trading days
MIN_HISTORY = 400


def momentum_from_close(close: pd.Series) -> dict[str, float | None]:
    """
    Momentum % = (Price 1M / Price 1Y − 1) × 100.

    Price 1Y = close ~395 sessions ago; Price 1M = close ~30 sessions ago.
    """
    s = close.dropna().astype(float)
    if len(s) < MIN_HISTORY:
        return {}

    price = float(s.iloc[-1])
    price_1y = float(s.iloc[-LOOKBACK_1Y])
    price_1m = float(s.iloc[-LOOKBACK_1M])
    momentum = None
    if price_1y > 0:
        momentum = round(((price_1m / price_1y) - 1) * 100, 2)

    return {
        "current_price": round(price, 2),
        "price_1y": round(price_1y, 2),
        "price_1m": round(price_1m, 2),
        "momentum_pct": momentum,
    }


def fetch_ticker_momentum(ticker: str, market: str | None) -> dict[str, float | None]:
    symbol = to_yfinance_symbol(ticker, market)

    def _fetch() -> dict[str, float | None]:
        hist = yf.Ticker(symbol).history(period="2y", interval="1d", auto_adjust=True)
        if hist is None or hist.empty or "Close" not in hist.columns:
            return {}
        return momentum_from_close(hist["Close"])

    result = call_throttled(_fetch, delay=YFINANCE_REQUEST_DELAY, on_error=lambda _e: None)
    return result or {}


def rank_by_momentum(df: pd.DataFrame) -> pd.DataFrame:
    """Sort by momentum descending; rank 1 = highest momentum."""
    if df.empty:
        return df
    out = df.copy()
    if "momentum_pct" not in out.columns:
        out["momentum_rank"] = range(1, len(out) + 1)
        return out
    out = out.sort_values("momentum_pct", ascending=False, na_position="last").reset_index(
        drop=True
    )
    out["momentum_rank"] = range(1, len(out) + 1)
    return out


def attach_holdings_momentum(
    df: pd.DataFrame,
    *,
    max_workers: int = 8,
) -> pd.DataFrame:
    """Fetch 2y daily history per holding and attach price / momentum columns."""
    if df.empty or "ticker" not in df.columns:
        return df

    out = df.copy()
    for col in ("current_price", "price_1y", "price_1m", "momentum_pct"):
        if col not in out.columns:
            out[col] = pd.NA

    markets = out["market"].tolist() if "market" in out.columns else [None] * len(out)
    tickers = out["ticker"].astype(str).tolist()
    results: dict[str, dict[str, float | None]] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(fetch_ticker_momentum, ticker, market): safe_str(ticker).upper()
            for ticker, market in zip(tickers, markets)
            if safe_str(ticker)
        }
        for fut in as_completed(futures):
            key = futures[fut]
            try:
                payload = fut.result()
            except Exception:
                payload = {}
            if payload:
                results[key] = payload

    for idx, row in out.iterrows():
        key = safe_str(row.get("ticker")).upper()
        payload = results.get(key)
        if not payload:
            continue
        for col in ("current_price", "price_1y", "price_1m", "momentum_pct"):
            if payload.get(col) is not None:
                out.at[idx, col] = payload[col]

    return rank_by_momentum(out)
