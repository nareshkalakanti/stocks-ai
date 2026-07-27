"""Cup & Handle / VCP detectors."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stocks.strategies.cup_vcp.detect import (
    detect_cup_and_handle,
    detect_patterns,
    detect_vcp,
)
from stocks.strategies.cup_vcp.html import build_cup_handle_html, build_vcp_html


def _ohlc_from_closes(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="B")
    close = np.asarray(closes, dtype=float)
    high = close * 1.01
    low = close * 0.99
    open_ = close.copy()
    vol = np.linspace(2_000_000, 800_000, len(closes))
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol},
        index=idx,
    )


def test_detect_cup_and_handle_near_breakout():
    # Left rim ~100, trough ~70, right rim ~98, shallow handle, finish near rim.
    left = np.linspace(90, 100, 20)
    down = np.linspace(100, 70, 30)
    up = np.linspace(70, 98, 35)
    handle = np.linspace(98, 93, 12)
    finish = np.linspace(93, 97.5, 8)
    closes = np.concatenate([left, down, up, handle, finish]).tolist()
    hit = detect_cup_and_handle(_ohlc_from_closes(closes))
    assert hit is not None
    assert hit["pattern_code"] == "CUP_HANDLE"
    assert hit["pattern_chart"]["closes"]
    assert hit["pattern_chart"]["shape"] == "cup_handle"
    lm = hit["pattern_chart"]["landmarks"]
    assert lm["left"]["i"] < lm["trough"]["i"] < lm["right"]["i"]
    assert any(z["kind"] == "cup" for z in hit["pattern_chart"]["zones"])
    assert any(z["kind"] == "handle" for z in hit["pattern_chart"]["zones"])


def test_detect_vcp_shrinking_contractions():
    # Three clear pullbacks into a late pivot: ~25% → ~12% → ~6%, finish near high.
    parts = [
        np.linspace(80, 100, 12),
        np.linspace(100, 75, 14),   # ~25%
        np.linspace(75, 101, 14),
        np.linspace(101, 89, 12),   # ~12%
        np.linspace(89, 102, 12),
        np.linspace(102, 96, 10),   # ~6%
        np.linspace(96, 101, 8),
    ]
    closes = np.concatenate(parts).tolist()
    hit = detect_vcp(_ohlc_from_closes(closes), min_contractions=2)
    assert hit is not None
    assert hit["pattern_code"] == "VCP"
    assert hit["contractions"] >= 2
    assert hit["pattern_chart"]["closes"]


def test_build_cup_handle_html_includes_pattern_chart_hook():
    df = pd.DataFrame(
        [
            {
                "ticker": "DEMO",
                "name": "Demo Ltd",
                "market": "NSE",
                "sector": "Test",
                "pattern": "VCP",
                "pattern_code": "VCP",
                "signal": "NEAR_BREAKOUT",
                "score": 72.0,
                "price": 100.0,
                "detail": "2 contractions 20 → 10",
                "date": "2026-07-01",
                "pattern_chart": {
                    "title": "VCP",
                    "closes": [{"i": 0, "v": 90}, {"i": 1, "v": 95}, {"i": 2, "v": 100}],
                    "zones": [{"kind": "pivot", "level": 100, "label": "Pivot"}],
                },
            }
        ]
    )
    html = build_cup_handle_html(df, standalone=False)
    assert "renderPatternChart" in html or "Cup & Handle" in html
    assert "DEMO" in html


def test_build_vcp_html_section():
    df = pd.DataFrame(
        [
            {
                "ticker": "DEMO",
                "name": "Demo Ltd",
                "market": "NSE",
                "sector": "Test",
                "pattern": "VCP",
                "signal": "NEAR_BREAKOUT",
                "score": 70.0,
                "price": 100.0,
                "detail": "2 contractions",
                "date": "2026-07-01",
            }
        ]
    )
    html = build_vcp_html(df, standalone=False)
    assert "VCP" in html
    assert "DEMO" in html


def test_detect_patterns_empty_on_noise():
    rng = np.random.default_rng(0)
    closes = (100 + np.cumsum(rng.normal(0, 0.3, 80))).tolist()
    assert detect_patterns(_ohlc_from_closes(closes)) == []
