"""Momentum factor scores from price history (12m–skip-1m)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from stocks.core.text_utils import safe_str
from stocks.market.momentum import LOOKBACK_1M, momentum_from_close

HISTORY_PERIOD = "2y"
HISTORY_INTERVAL = "1d"
# Include any Yahoo-priced name; full 12–1 momentum still needs longer history.
MIN_BARS = 1


def analyze_factor_stock(
    ticker: str,
    market: str | None,
    data: pd.DataFrame,
) -> dict[str, Any] | None:
    if data is None or len(data) < MIN_BARS or "Close" not in data.columns:
        return None
    close = pd.to_numeric(data["Close"], errors="coerce").dropna()
    if len(close) < MIN_BARS:
        return None

    mom = momentum_from_close(close)
    momentum_pct = mom.get("momentum_pct")
    price = float(mom.get("current_price") or close.iloc[-1])
    price_1y = mom.get("price_1y")
    price_1m = mom.get("price_1m")
    # Short history: still surface last price (and 1M if available).
    if price_1m is None and len(close) > LOOKBACK_1M:
        price_1m = round(float(close.iloc[-LOOKBACK_1M]), 2)

    latest = data.iloc[-1]
    date = ""
    try:
        date = latest.name.strftime("%Y-%m-%d")
    except Exception:
        date = safe_str(latest.name)[:10]

    detail = (
        f"Mom {float(momentum_pct):+.1f}%"
        if momentum_pct is not None
        else "price only (short history)"
    )
    return {
        "ticker": safe_str(ticker).upper(),
        "market": safe_str(market) or None,
        "price": round(price, 2),
        "price_1y": price_1y,
        "price_1m": price_1m,
        "momentum_pct": momentum_pct,
        "signal": "FACTOR",
        "date": date,
        "timeframe": "daily",
        "pattern": "Momentum",
        "pattern_code": "FACTOR",
        "detail": detail,
    }


def _rank_pct(series: pd.Series, *, ascending: bool) -> pd.Series:
    """Percentile rank 0–100 (NaN stays NaN)."""
    s = pd.to_numeric(series, errors="coerce")
    if s.notna().sum() < 2:
        return pd.Series(np.nan, index=series.index)
    return s.rank(ascending=ascending, pct=True, method="average") * 100.0


def attach_factor_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional momentum score (0–100, higher = stronger 12–1 momentum)."""
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()

    out = df.copy()
    out["f_momentum"] = _rank_pct(out["momentum_pct"], ascending=True)
    out["score"] = out["f_momentum"].round(1)
    out["factors_used"] = out["f_momentum"].notna().astype(int)
    out["detail"] = out.apply(
        lambda row: (
            f"Mom {row['momentum_pct']:+.1f}%"
            if pd.notna(row.get("momentum_pct"))
            else "momentum"
        ),
        axis=1,
    )
    return out
