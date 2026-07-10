"""12-month price momentum with 1-month lag (Google Finance / stock-analysis style)."""

from __future__ import annotations

import pandas as pd
import yfinance as yf

from stocks.core.text_utils import safe_str
from stocks.market.price_service import to_yfinance_symbol

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


def _close_from_download(data: pd.DataFrame, symbol: str, *, multi: bool) -> pd.Series | None:
    try:
        if multi:
            block = data[symbol]
            if block is None or "Close" not in block.columns:
                return None
            return block["Close"]
        if "Close" not in data.columns:
            return None
        return data["Close"]
    except (KeyError, TypeError, AttributeError):
        return None


def bulk_fetch_momentum(symbols: list[str]) -> dict[str, dict[str, float | None]]:
    """Fetch 2y daily history for many tickers in one yfinance batch call."""
    unique = list(dict.fromkeys(symbols))
    if not unique:
        return {}

    try:
        data = yf.download(
            unique,
            period="2y",
            interval="1d",
            group_by="ticker",
            progress=False,
            threads=True,
            auto_adjust=True,
        )
    except Exception:
        return {}

    if data is None or data.empty:
        return {}

    multi = len(unique) > 1
    out: dict[str, dict[str, float | None]] = {}
    for symbol in unique:
        close = _close_from_download(data, symbol, multi=multi)
        if close is None:
            continue
        payload = momentum_from_close(close)
        if payload:
            out[symbol] = payload
    return out


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


def attach_holdings_momentum(df: pd.DataFrame) -> pd.DataFrame:
    """Fetch 2y daily history and attach price / momentum columns (batch download)."""
    if df.empty or "ticker" not in df.columns:
        return df

    out = df.copy()
    for col in ("current_price", "price_1y", "price_1m", "momentum_pct"):
        if col not in out.columns:
            out[col] = pd.NA

    markets = out["market"].tolist() if "market" in out.columns else [None] * len(out)
    tickers = out["ticker"].astype(str).tolist()

    symbol_by_ticker: dict[str, str] = {}
    for ticker, market in zip(tickers, markets):
        key = safe_str(ticker).upper()
        if not key:
            continue
        symbol_by_ticker[key] = to_yfinance_symbol(ticker, market)

    momentum_by_symbol = bulk_fetch_momentum(list(symbol_by_ticker.values()))
    results: dict[str, dict[str, float | None]] = {}
    for ticker, symbol in symbol_by_ticker.items():
        payload = momentum_by_symbol.get(symbol)
        if payload:
            results[ticker] = payload

    for idx, row in out.iterrows():
        key = safe_str(row.get("ticker")).upper()
        payload = results.get(key)
        if not payload:
            continue
        for col in ("current_price", "price_1y", "price_1m", "momentum_pct"):
            if payload.get(col) is not None:
                out.at[idx, col] = payload[col]

    return rank_by_momentum(out)
