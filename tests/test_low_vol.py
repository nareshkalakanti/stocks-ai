"""Low volatility factor tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stocks.strategies.low_vol.detect import analyze_low_volatility
from stocks.strategies.low_vol.html import build_low_vol_html


def _ohlc(n: int = 280, *, seed: int = 1, vol_scale: float = 0.01) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0002, vol_scale, n)
    close = 100 * np.cumprod(1 + rets)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {
            "Open": close,
            "High": close * 1.005,
            "Low": close * 0.995,
            "Close": close,
            "Volume": np.full(n, 1_000_000.0),
        },
        index=idx,
    )


def test_analyze_low_volatility_returns_metrics():
    hit = analyze_low_volatility("DEMO", "NSE", _ohlc(vol_scale=0.008))
    assert hit is not None
    assert hit["pattern_code"] == "LOW_VOL"
    assert hit["short_vol"] > 0
    assert hit["long_vol"] > 0
    assert hit["composite_vol"] > 0


def test_quiet_stock_has_lower_composite_than_noisy():
    quiet = analyze_low_volatility("Q", "NSE", _ohlc(seed=2, vol_scale=0.005))
    noisy = analyze_low_volatility("N", "NSE", _ohlc(seed=3, vol_scale=0.03))
    assert quiet is not None and noisy is not None
    assert quiet["composite_vol"] < noisy["composite_vol"]


def test_build_low_vol_html():
    df = pd.DataFrame(
        [
            {
                "ticker": "DEMO",
                "name": "Demo Ltd",
                "market": "NSE",
                "vol_rank": 1,
                "short_vol": 12.0,
                "long_vol": 14.0,
                "composite_vol": 13.0,
                "score": 80.0,
                "price": 100.0,
                "date": "2026-07-01",
            }
        ]
    )
    html = build_low_vol_html(df, standalone=False)
    assert "Low Volatility" in html
    assert "DEMO" in html
