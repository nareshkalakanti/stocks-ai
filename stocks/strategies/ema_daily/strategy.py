"""Daily EMA strategy — price above 20/50/100/200 EMAs."""

from __future__ import annotations

from stocks.core.text_utils import safe_str
from stocks.strategies.pead2.technicals import _EMA_PERIODS, _build_ema_averages

EMA_HISTORY_PERIOD = "2y"
EMA_INTERVAL = "1d"
EMA_MIN_BARS = max(_EMA_PERIODS)


def ema_values_by_period(ema_averages: list[dict]) -> dict[int, float]:
    out: dict[int, float] = {}
    for row in ema_averages:
        period = row.get("period")
        value = row.get("value")
        if period is None or value is None:
            continue
        out[int(period)] = float(value)
    return out


def analyze_ema_daily(
    ticker: str,
    market: str | None = None,
    *,
    hist,
) -> dict | None:
    """Return row when daily close is above all four EMAs."""
    if hist is None or hist.empty or len(hist) < EMA_MIN_BARS:
        return None

    close = hist["Close"].dropna().sort_index()
    if len(close) < EMA_MIN_BARS:
        return None

    px = float(close.iloc[-1])
    ema_averages, above_all = _build_ema_averages(close, px)
    if above_all is not True or len(ema_averages) != len(_EMA_PERIODS):
        return None

    by_period = ema_values_by_period(ema_averages)
    ema_200 = by_period.get(200)
    stretch = None
    if ema_200 and ema_200 > 0:
        stretch = round((px / ema_200 - 1.0) * 100, 2)

    latest = hist.iloc[-1]
    return {
        "ticker": safe_str(ticker).upper(),
        "market": safe_str(market) or None,
        "price": round(px, 2),
        "ema_20": by_period.get(20),
        "ema_50": by_period.get(50),
        "ema_100": by_period.get(100),
        "ema_200": by_period.get(200),
        "above_all_emas": True,
        "ema_stretch_pct": stretch,
        "date": latest.name.strftime("%Y-%m-%d"),
        "timeframe": "daily",
        "score": stretch if stretch is not None else 0.0,
    }


__all__ = [
    "EMA_HISTORY_PERIOD",
    "EMA_INTERVAL",
    "EMA_MIN_BARS",
    "analyze_ema_daily",
    "ema_values_by_period",
]
