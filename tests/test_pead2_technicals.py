"""Tests for PEAD price snapshot / EMA logic."""

from __future__ import annotations

from datetime import date

import pandas as pd

from stocks.strategies.pead2.technicals import (
    _build_ema_averages,
    build_expected_prices,
    build_price_snapshot,
    indian_fy_labels,
)


def test_above_all_emas_when_price_above_each():
    close = pd.Series(range(100, 300), dtype=float)
    emas, all_above = _build_ema_averages(close, 500.0)
    assert len(emas) == 4
    assert all_above is True
    assert all(row["above"] for row in emas)


def test_not_above_all_emas_when_price_below_one():
    close = pd.Series(range(100, 300), dtype=float)
    emas, all_above = _build_ema_averages(close, 150.0)
    assert all_above is False
    assert any(not row["above"] for row in emas)


def test_build_price_snapshot_includes_ema_fields():
    hist = pd.DataFrame(
        {"Close": [float(i) for i in range(1, 251)]},
        index=pd.date_range("2024-01-01", periods=250, freq="B"),
    )
    snap = build_price_snapshot(
        {"regularMarketPrice": 300.0, "marketCap": 1e10},
        hist,
        None,
        price=300.0,
    )
    assert snap is not None
    assert len(snap["ema_averages"]) == 4
    assert snap["above_all_emas"] is True


def test_indian_fy_labels_july_2026():
    labels = indian_fy_labels(4, as_of=date(2026, 7, 13))
    assert labels == ["FY26", "FY27", "FY28", "FY29"]


def test_build_expected_prices_from_comfortable_buy():
    rows = build_expected_prices(
        235.0,
        cagr=46.9,
        eps_yoy=76.0,
        comfortable_buy=210.0,
    )
    assert rows is not None
    assert rows[0] == {"fy": "FY26", "price": 210}
    assert rows[1]["price"] == 370


def test_build_expected_prices_from_price_growth():
    rows = build_expected_prices(134.0, eps_yoy=56.6, cagr=14.75)
    assert rows is not None
    assert rows[0]["price"] == 210
