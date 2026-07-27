"""Weekly base breakout detector tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stocks.strategies.base_breakout.detect import detect_weekly_base_breakout
from stocks.strategies.base_breakout.html import build_base_breakout_html


def _ohlc_from_closes(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2023-01-01", periods=len(closes), freq="W")
    close = np.asarray(closes, dtype=float)
    high = close * 1.01
    low = close * 0.99
    open_ = close.copy()
    vol = np.linspace(1_000_000, 1_300_000, len(closes))
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol},
        index=idx,
    )


def test_detect_weekly_base_breakout_near_pivot():
    early = np.concatenate([
        np.linspace(82, 98, 8),
        np.linspace(98, 84, 8),
        np.linspace(84, 97, 8),
        np.linspace(97, 86, 8),
        np.linspace(86, 98, 8),
    ])
    tight = np.array([95.0, 96.2, 95.4, 96.5, 95.8, 97.0, 96.4, 97.4, 96.8, 98.1, 97.6, 98.8])
    closes = np.concatenate([early, tight]).tolist()
    hit = detect_weekly_base_breakout(_ohlc_from_closes(closes))
    assert hit is not None
    assert hit["pattern_code"] == "BASE_BREAKOUT"
    assert hit["base_weeks"] >= 30
    assert hit["pattern_chart"]["closes"]
    assert any(z["kind"] == "base" for z in hit["pattern_chart"]["zones"])


def test_build_base_breakout_html_includes_title():
    df = pd.DataFrame(
        [
            {
                "ticker": "DEMO",
                "name": "Demo Ltd",
                "market": "NSE",
                "signal": "NEAR_BREAKOUT",
                "score": 74.0,
                "price": 98.5,
                "detail": "36w base",
                "date": "2026-07-01",
                "pattern_chart": {
                    "title": "Weekly Base Breakout",
                    "closes": [{"i": 0, "v": 90}, {"i": 1, "v": 95}, {"i": 2, "v": 99}],
                    "zones": [{"kind": "base", "i0": 0, "i1": 2}],
                },
            }
        ]
    )
    html = build_base_breakout_html(df, standalone=False)
    assert "Weekly Base Breakout" in html
    assert "DEMO" in html
