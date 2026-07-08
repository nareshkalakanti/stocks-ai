"""Regression tests for PE / Fwd PE backfill on scan frames."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stocks.strategies.intrinsic_value.cache import ensure_pe_ratios


def test_ensure_pe_ratios_all_none_lookup_does_not_crash(monkeypatch):
    """IV cache rows with null PE must not raise LossySetitemError on float64 columns."""

    def _fake_iv(_tickers, *, max_hours):
        return pd.DataFrame(
            {
                "ticker": ["AAA", "BBB"],
                "pe_ratio": [None, None],
                "forward_pe": [None, None],
            }
        )

    monkeypatch.setattr(
        "stocks.strategies.intrinsic_value.cache.load_cached_iv_rows",
        _fake_iv,
    )

    frame = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB", "CCC"],
            "pe_ratio": np.nan,
            "forward_pe": np.nan,
        }
    )
    out = ensure_pe_ratios(frame, max_hours=24)
    assert len(out) == 3
    assert out["forward_pe"].isna().all()


def test_ensure_pe_ratios_fills_partial_values(monkeypatch):
    def _fake_iv(_tickers, *, max_hours):
        return pd.DataFrame(
            {
                "ticker": ["AAA"],
                "pe_ratio": [12.5],
                "forward_pe": [10.0],
            }
        )

    monkeypatch.setattr(
        "stocks.strategies.intrinsic_value.cache.load_cached_iv_rows",
        _fake_iv,
    )

    frame = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB"],
            "pe_ratio": [np.nan, np.nan],
            "forward_pe": [np.nan, np.nan],
        }
    )
    out = ensure_pe_ratios(frame, max_hours=24)
    assert out.loc[out["ticker"] == "AAA", "pe_ratio"].iloc[0] == 12.5
    assert out.loc[out["ticker"] == "AAA", "forward_pe"].iloc[0] == 10.0
    assert pd.isna(out.loc[out["ticker"] == "BBB", "pe_ratio"].iloc[0])
