"""Weekly RSI entry cross tests."""

from __future__ import annotations

import pandas as pd

from stocks.strategies.rsi_weekly.service import (
    RSI_ENTRY,
    RSI_ENTRY_MAX,
    SIGNAL_ENTRY,
    latest_rsi_entry_cross,
)


def test_latest_cross_detected_near_threshold():
    rsi = pd.Series([40.0, 50.0, 55.0, 60.8])
    state = latest_rsi_entry_cross(rsi, entry=RSI_ENTRY, entry_max=RSI_ENTRY_MAX)
    assert state is not None
    assert state["signal"] == SIGNAL_ENTRY
    assert state["rsi"] == 60.8
    assert state["prev_rsi"] == 55.0


def test_cross_rejected_when_current_too_high():
    rsi = pd.Series([40.0, 50.0, 55.0, 62.0])
    assert latest_rsi_entry_cross(rsi, entry=RSI_ENTRY, entry_max=RSI_ENTRY_MAX) is None


def test_cross_rejected_at_66():
    rsi = pd.Series([40.0, 50.0, 58.0, 66.0])
    assert latest_rsi_entry_cross(rsi, entry=RSI_ENTRY, entry_max=RSI_ENTRY_MAX) is None


def test_no_cross_when_already_above():
    rsi = pd.Series([40.0, 61.0, 70.0, 75.0])
    assert latest_rsi_entry_cross(rsi, entry=RSI_ENTRY, entry_max=RSI_ENTRY_MAX) is None


def test_no_cross_when_below():
    rsi = pd.Series([40.0, 50.0, 55.0, 58.0])
    assert latest_rsi_entry_cross(rsi, entry=RSI_ENTRY, entry_max=RSI_ENTRY_MAX) is None


def test_cross_after_dip_replaces_only_when_near_threshold():
    rsi = pd.Series([62.0, 70.0, 55.0, 60.5])
    state = latest_rsi_entry_cross(rsi, entry=RSI_ENTRY, entry_max=RSI_ENTRY_MAX)
    assert state is not None
    assert state["rsi"] == 60.5

    rsi_high = pd.Series([62.0, 70.0, 55.0, 63.0])
    assert latest_rsi_entry_cross(rsi_high, entry=RSI_ENTRY, entry_max=RSI_ENTRY_MAX) is None
