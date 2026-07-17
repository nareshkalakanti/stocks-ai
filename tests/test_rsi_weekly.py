"""Weekly RSI entry cross tests."""

from __future__ import annotations

import pandas as pd

from stocks.strategies.rsi_weekly.service import SIGNAL_ENTRY, latest_rsi_entry_cross


def test_latest_cross_detected():
    rsi = pd.Series([40.0, 50.0, 55.0, 62.0])
    state = latest_rsi_entry_cross(rsi, entry=60.0)
    assert state is not None
    assert state["signal"] == SIGNAL_ENTRY
    assert state["rsi"] == 62.0
    assert state["prev_rsi"] == 55.0


def test_no_cross_when_already_above():
    rsi = pd.Series([40.0, 61.0, 70.0, 75.0])
    assert latest_rsi_entry_cross(rsi, entry=60.0) is None


def test_no_cross_when_below():
    rsi = pd.Series([40.0, 50.0, 55.0, 58.0])
    assert latest_rsi_entry_cross(rsi, entry=60.0) is None


def test_cross_after_dip_replaces():
    # Prior stay above 60 does not count; only latest bar cross matters
    rsi = pd.Series([62.0, 70.0, 55.0, 63.0])
    state = latest_rsi_entry_cross(rsi, entry=60.0)
    assert state is not None
    assert state["rsi"] == 63.0
