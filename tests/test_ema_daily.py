"""Daily above-all-EMAs strategy."""

from __future__ import annotations

import pandas as pd

from stocks.strategies.ema_daily.strategy import analyze_ema_daily


def test_analyze_ema_daily_passes_when_above_all():
    close = pd.Series([float(i) for i in range(1, 251)])
    hist = pd.DataFrame({"Close": close}, index=pd.date_range("2024-01-01", periods=250, freq="B"))
    row = analyze_ema_daily("TEST", "NSE", hist=hist)
    assert row is not None
    assert row["above_all_emas"] is True
    assert row["ema_20"] is not None
    assert row["ema_200"] is not None
    assert row["timeframe"] == "daily"


def test_analyze_ema_daily_rejects_when_below_ema200():
    close = pd.Series([float(i) for i in range(1, 251)])
    hist = pd.DataFrame({"Close": close}, index=pd.date_range("2024-01-01", periods=250, freq="B"))
    row = analyze_ema_daily("TEST", "NSE", hist=hist)
    assert row is not None

    hist_low = hist.copy()
    hist_low.iloc[-1, hist_low.columns.get_loc("Close")] = 50.0
    row_low = analyze_ema_daily("TEST", "NSE", hist=hist_low)
    assert row_low is None
