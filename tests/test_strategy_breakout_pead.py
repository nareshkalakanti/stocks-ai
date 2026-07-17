"""PEAD cross-reference with Strategy TQ/BB SQLite cache."""

from __future__ import annotations

import pandas as pd

from stocks.strategies.pead2.strategy import (
    apply_breakout_map,
    attach_strategy_breakout_signals,
)


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


def test_apply_breakout_map_does_not_overwrite_existing():
    df = pd.DataFrame(
        {
            "ticker": ["AAA"],
            "has_tq": [True],
            "tq_crossover": ["13W Only"],
            "tq_score": [70.0],
            "has_bb": [False],
            "bb_signal": [""],
        }
    )
    bmap = {
        "AAA": {
            "tq": {"score": 99.0, "crossover_type": "52W Only", "timeframe": "weekly"},
            "bb": {"signal": "NEW_BREAKOUT", "timeframe": "weekly"},
        }
    }
    out = apply_breakout_map(df, bmap, overwrite=False)
    assert out.iloc[0]["tq_crossover"] == "13W Only"
    assert float(out.iloc[0]["tq_score"]) == 70.0
    assert bool(out.iloc[0]["has_bb"]) is True
    assert out.iloc[0]["bb_signal"] == "NEW_BREAKOUT"


def test_attach_weekly_breakouts_to_pead(monkeypatch):
    from stocks.strategies.pead2 import service as pead_service

    def _fake_bb(universe, **kwargs):
        return pd.DataFrame(
            [{"ticker": "AAA", "signal": "NEW_BREAKOUT", "timeframe": "weekly", "price": 10, "upper_band": 9}]
        )

    def _fake_tq(universe, **kwargs):
        return pd.DataFrame(
            [
                {
                    "ticker": "AAA",
                    "score": 81.0,
                    "crossover_type": "52W Only",
                    "timeframe": "weekly",
                    "signal": "TQ_SIGNAL",
                }
            ]
        )

    monkeypatch.setattr("stocks.strategies.tq_bb.service.run_bb_strategy", _fake_bb)
    monkeypatch.setattr("stocks.strategies.tq_bb.service.run_tq_strategy", _fake_tq)
    monkeypatch.setattr(
        "stocks.core.database.clear_strategy_breakouts_for_tickers",
        lambda tickers, timeframe="weekly": None,
    )
    monkeypatch.setattr(
        "stocks.core.database.upsert_strategy_bb_signals",
        lambda df, timeframe="weekly": len(df),
    )
    monkeypatch.setattr(
        "stocks.core.database.upsert_strategy_tq_signals",
        lambda df, timeframe="weekly": len(df),
    )

    df = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB"],
            "name": ["A", "B"],
            "market": ["NSE", "NSE"],
            "pead_score": [55.0, 40.0],
        }
    )
    out = pead_service.attach_weekly_breakouts_to_pead(df, persist=True)
    aaa = out[out["ticker"] == "AAA"].iloc[0]
    assert bool(aaa["has_tq"]) is True
    assert bool(aaa["has_bb"]) is True
    assert aaa["bb_signal"] == "NEW_BREAKOUT"
    assert float(aaa["tq_score"]) == 81.0
    bbb = out[out["ticker"] == "BBB"].iloc[0]
    assert not bool(bbb["has_tq"])
    assert not bool(bbb["has_bb"])
