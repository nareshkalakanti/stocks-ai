"""PEAD cross-reference with Strategy TQ/BB SQLite cache."""

from __future__ import annotations

import pandas as pd

from stocks.strategies.pead2.strategy import attach_strategy_breakout_signals


def test_attach_strategy_breakout_signals(monkeypatch):
    def _fake_map(tickers):
        return {
            "RELIANCE": {
                "tq": {"score": 88.5, "crossover_type": "52W Only"},
                "bb": {"signal": "NEW_BREAKOUT", "timeframe": "weekly"},
            }
        }

    monkeypatch.setattr(
        "stocks.core.database.load_strategy_breakout_map",
        _fake_map,
    )

    df = pd.DataFrame(
        {
            "ticker": ["RELIANCE", "TCS"],
            "pead_score": [50.0, 30.0],
        }
    )
    out = attach_strategy_breakout_signals(df)
    rel = out[out["ticker"] == "RELIANCE"].iloc[0]
    assert bool(rel["has_tq"]) is True
    assert float(rel["tq_score"]) == 88.5
    assert rel["tq_crossover"] == "52W Only"
    assert bool(rel["has_bb"]) is True
    assert rel["bb_signal"] == "NEW_BREAKOUT"
    tcs = out[out["ticker"] == "TCS"].iloc[0]
    assert not bool(tcs["has_tq"])
    assert not bool(tcs["has_bb"])
