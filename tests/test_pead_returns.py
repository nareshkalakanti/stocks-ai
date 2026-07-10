"""Unit tests for PEAD return formulas (offline, deterministic)."""

from __future__ import annotations

import pandas as pd

from stocks.strategies.pead2.strategy import (
    compute_daily_ret_ff,
    compute_daily_ret_pct,
    compute_forward_pe,
    compute_return_since_result,
    compute_returns_pct,
    trading_days_after_result,
)


def _hist(closes: list[tuple[str, float]]) -> pd.DataFrame:
    idx = pd.to_datetime([d for d, _ in closes])
    return pd.DataFrame({"Close": [c for _, c in closes]}, index=idx)


def test_compute_returns_pct_open_ended_drift():
    hist = _hist(
        [
            ("2026-04-01", 100.0),
            ("2026-05-01", 105.0),
            ("2026-05-15", 110.0),
            ("2026-06-01", 120.0),
        ]
    )
    ret = compute_returns_pct(hist, pd.Timestamp("2026-05-01"))
    assert ret == 9.09  # first close after 2026-05-01 is 110 → 120/110 - 1


def test_compute_return_since_result_matches_stock_analysis_window():
    hist = _hist(
        [
            ("2026-05-07", 100.0),
            ("2026-05-08", 101.0),
            ("2026-05-12", 105.0),
            ("2026-06-01", 149.4),
        ]
    )
    ret = compute_return_since_result(
        hist,
        pd.Timestamp("2026-05-12"),
        current_price=149.4,
    )
    assert ret == 49.4


def test_trading_days_after_result_counts_closes_after_date():
    hist = _hist(
        [
            ("2026-05-01", 100.0),
            ("2026-05-02", 101.0),
            ("2026-05-03", 102.0),
        ]
    )
    assert trading_days_after_result(hist, pd.Timestamp("2026-05-01")) == 2


def test_compute_forward_pe_negative_eps_returns_sentinel():
    eps = pd.Series([-1.0], index=[pd.Timestamp("2026-03-31")])
    assert compute_forward_pe(100.0, eps) == 999.0


def test_compute_daily_ret_ff_caps_spike():
    hist = _hist(
        [
            ("2026-05-19", 100.0),
            ("2026-05-20", 125.0),
            ("2026-05-21", 120.0),
        ]
    )
    daily = compute_daily_ret_ff(hist, pd.Timestamp("2026-05-19"), cap=19.99)
    assert daily == 19.99


def test_compute_daily_ret_pct_is_returns_over_trading_days():
    hist = _hist(
        [
            ("2026-05-01", 100.0),
            ("2026-05-02", 110.0),
            ("2026-05-03", 120.0),
        ]
    )
    daily = compute_daily_ret_pct(20.0, hist, pd.Timestamp("2026-05-01"))
    assert daily == 10.0
