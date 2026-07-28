"""Low volatility factor — short-term + long-term realized vol."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from stocks.core.text_utils import safe_str

SHORT_WINDOW = 21   # ~1 month trading days
LONG_WINDOW = 252   # ~1 year trading days
MIN_BARS = LONG_WINDOW + 5
HISTORY_PERIOD = "2y"
HISTORY_INTERVAL = "1d"


def _annualized_vol_pct(close: pd.Series, window: int) -> float | None:
    s = pd.to_numeric(close, errors="coerce").dropna()
    if len(s) < window + 1:
        return None
    rets = s.pct_change().dropna().iloc[-window:]
    if len(rets) < max(10, window // 2):
        return None
    std = float(rets.std(ddof=1))
    if not np.isfinite(std) or std < 0:
        return None
    return round(std * np.sqrt(252) * 100.0, 2)


def analyze_low_volatility(
    ticker: str,
    market: str | None,
    data: pd.DataFrame,
) -> dict[str, Any] | None:
    if data is None or len(data) < MIN_BARS or "Close" not in data.columns:
        return None
    close = pd.to_numeric(data["Close"], errors="coerce").dropna()
    if len(close) < MIN_BARS:
        return None

    short_vol = _annualized_vol_pct(close, SHORT_WINDOW)
    long_vol = _annualized_vol_pct(close, LONG_WINDOW)
    if short_vol is None or long_vol is None:
        return None

    # Prefer both low: equal-weight composite (lower = better).
    composite = round(0.5 * short_vol + 0.5 * long_vol, 2)
    price = float(close.iloc[-1])
    latest = data.iloc[-1]
    date = ""
    try:
        date = latest.name.strftime("%Y-%m-%d")
    except Exception:
        date = safe_str(latest.name)[:10]

    # Score for UI: invert so higher score = lower volatility (0–100-ish).
    # 40% ann. vol → low score; 10% → high score.
    score = float(max(0.0, min(100.0, round(100.0 - composite * 1.5, 1))))

    return {
        "ticker": safe_str(ticker).upper(),
        "market": safe_str(market) or None,
        "price": round(price, 2),
        "short_vol": short_vol,
        "long_vol": long_vol,
        "composite_vol": composite,
        "signal": "LOW_VOL",
        "score": score,
        "detail": f"ST {short_vol:.1f}% · LT {long_vol:.1f}% · avg {composite:.1f}%",
        "date": date,
        "timeframe": "daily",
        "pattern": "Low Volatility",
        "pattern_code": "LOW_VOL",
    }
