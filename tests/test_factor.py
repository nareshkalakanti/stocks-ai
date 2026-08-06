"""Factor investing (momentum) scan tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stocks.strategies.factor.detect import analyze_factor_stock, attach_factor_scores
from stocks.strategies.factor.html import build_factor_html


def _ohlc(n: int = 420, *, seed: int = 1, drift: float = 0.001, vol: float = 0.01) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, n)
    close = 100 * np.cumprod(1 + rets)
    idx = pd.date_range("2023-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {
            "Open": close,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": rng.integers(500_000, 2_000_000, n).astype(float),
        },
        index=idx,
    )


def test_analyze_factor_stock_has_momentum():
    hit = analyze_factor_stock("DEMO", "NSE", _ohlc())
    assert hit is not None
    assert hit["pattern_code"] == "FACTOR"
    assert hit["momentum_pct"] is not None
    assert hit["price_1y"] is not None
    assert hit["price_1m"] is not None
    assert "long_vol" not in hit
    assert "roe" not in hit


def test_analyze_factor_stock_short_history_keeps_price():
    """Yahoo-priced names with <400 bars still appear (momentum blank)."""
    hit = analyze_factor_stock("NIBE", "NSE", _ohlc(n=360))
    assert hit is not None
    assert hit["price"] is not None
    assert hit["momentum_pct"] is None
    assert hit["price_1y"] is None
    assert hit["price_1m"] is not None


def test_attach_factor_scores_ranks_by_momentum():
    df = pd.DataFrame(
        [
            {"ticker": "A", "momentum_pct": 40},
            {"ticker": "B", "momentum_pct": 5},
            {"ticker": "C", "momentum_pct": 25},
        ]
    )
    scored = attach_factor_scores(df)
    assert "score" in scored.columns
    assert scored.loc[scored["ticker"] == "A", "score"].iloc[0] > scored.loc[
        scored["ticker"] == "B", "score"
    ].iloc[0]


def test_build_factor_html():
    df = pd.DataFrame(
        [
            {
                "ticker": "BSE",
                "name": "BSE Ltd.",
                "market": "NSE",
                "sector": "Banking & Finance",
                "sub_sector": "Stock Exchanges & Ratings",
                "factor_rank": 1,
                "score": 0.85,
                "composite": 0.85,
                "mom_21": 0.042,
                "value_proxy": 0.12,
                "vol_factor": 0.22,
                "sector_rel_mom": 0.01,
                "price": 3514.0,
                "date": "2026-07-01",
            }
        ]
    )
    html = build_factor_html(df, standalone=False, validation={"test_mean_ic": 0.05})
    assert "Factor" in html
    assert "Composite" in html
    assert "BSE" in html
    assert "Sector" in html
    assert "pct2" in html
