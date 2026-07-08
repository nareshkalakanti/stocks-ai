"""Tests for price momentum calculation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stocks.market.momentum import momentum_from_close, rank_by_momentum


def test_momentum_from_close_formula():
    n = 420
    close = pd.Series(np.linspace(100, 200, n))
    out = momentum_from_close(close)
    assert out["current_price"] == round(float(close.iloc[-1]), 2)
    assert out["price_1y"] == round(float(close.iloc[-395]), 2)
    assert out["price_1m"] == round(float(close.iloc[-30]), 2)
    expected = round((out["price_1m"] / out["price_1y"] - 1) * 100, 2)
    assert abs(out["momentum_pct"] - expected) < 0.02


def test_rank_by_momentum_descending():
    df = pd.DataFrame(
        {
            "ticker": ["A", "B", "C"],
            "momentum_pct": [10.0, 50.0, -5.0],
        }
    )
    ranked = rank_by_momentum(df)
    assert ranked.iloc[0]["ticker"] == "B"
    assert ranked.iloc[0]["momentum_rank"] == 1
    assert ranked.iloc[1]["ticker"] == "A"
    assert ranked.iloc[2]["ticker"] == "C"
