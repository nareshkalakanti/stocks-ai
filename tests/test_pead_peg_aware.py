"""PEG-aware PEAD scoring (separate from PEAD 2)."""

from __future__ import annotations

import pandas as pd

from stocks.strategies.peg_aware.strategy import attach_peg_aware_fields, score_peg_aware


def test_attach_peg_and_napkin_readouts():
    df = pd.DataFrame(
        [
            {
                "ticker": "CHEAP",
                "eps_yoy": 40.0,
                "forward_pe": 20.0,
            }
        ]
    )
    out = attach_peg_aware_fields(df)
    assert out.iloc[0]["surprise_growth"] == 40.0
    assert out.iloc[0]["peg"] == 0.5  # 20 / max(40, 5)
    assert out.iloc[0]["peg_score"] is not None and out.iloc[0]["peg_score"] > 90
    assert out.iloc[0]["napkin_near_pe"] is not None
    assert out.iloc[0]["napkin_required_cagr"] is not None
    assert out.iloc[0]["napkin_gap"] is not None


def test_peg_aware_gate_keeps_cheap_growth_drops_expensive():
    df = pd.DataFrame(
        [
            {
                "ticker": "PASS",
                "eps_yoy": 30.0,
                "forward_pe": 18.0,
                "returns_pct": 12.0,
                "sales_yoy": 20.0,
                "np_yoy": 25.0,
            },
            {
                "ticker": "RICH",
                "eps_yoy": 10.0,
                "forward_pe": 40.0,
                "returns_pct": 20.0,
                "sales_yoy": 10.0,
                "np_yoy": 10.0,
            },
            {
                "ticker": "NEG",
                "eps_yoy": -5.0,
                "forward_pe": 8.0,
                "returns_pct": 5.0,
                "sales_yoy": -5.0,
                "np_yoy": -10.0,
            },
            {
                "ticker": "SENTINEL",
                "eps_yoy": 50.0,
                "forward_pe": 999.0,
                "returns_pct": 8.0,
                "sales_yoy": 50.0,
                "np_yoy": 40.0,
            },
        ]
    )
    scored = score_peg_aware(df)
    tickers = set(scored["ticker"].tolist())
    assert tickers == {"PASS"}
    assert "peg" in scored.columns
    assert "napkin_gap" in scored.columns


def test_peg_weight_prefers_lower_peg_at_similar_growth():
    df = pd.DataFrame(
        [
            {
                "ticker": "LOW_PEG",
                "eps_yoy": 25.0,
                "sales_yoy": 25.0,
                "np_yoy": 25.0,
                "forward_pe": 12.0,
                "returns_pct": 10.0,
            },
            {
                "ticker": "HIGH_PEG",
                "eps_yoy": 25.0,
                "sales_yoy": 25.0,
                "np_yoy": 25.0,
                "forward_pe": 40.0,
                "returns_pct": 10.0,
            },
        ]
    )
    scored = score_peg_aware(df)
    assert list(scored["ticker"]) == ["LOW_PEG", "HIGH_PEG"]
    assert scored.iloc[0]["pead_score"] > scored.iloc[1]["pead_score"]
