from unittest.mock import patch

import pandas as pd

from stocks.core.config import PEAD2_CALC_VERSION
from stocks.strategies.pead2.service import (
    Pead2ScanCoverage,
    pead2_scan_coverage,
    run_pead2_scan,
)


def _universe(*tickers: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": list(tickers),
            "market": ["NSE"] * len(tickers),
            "name": list(tickers),
            "sector": ["Industrials"] * len(tickers),
        }
    )


def test_pead2_scan_coverage_counts_cached_stale_and_missing():
    universe = _universe("AAA", "BBB", "CCC")
    cached = {
        "AAA": {"ticker": "AAA", "calc_version": PEAD2_CALC_VERSION, "lags": {"0": {}}},
        "BBB": {"ticker": "BBB", "calc_version": PEAD2_CALC_VERSION - 1, "lags": {"0": {}}},
    }
    with patch("stocks.strategies.pead2.service.load_pead2_cache", return_value=cached):
        coverage = pead2_scan_coverage(universe)
    assert coverage == Pead2ScanCoverage(
        universe_total=3,
        cached=1,
        stale=1,
        missing=1,
    )
    assert coverage.pending_count("all") == 2
    assert coverage.pending_count("missing") == 1
    assert coverage.pending_count("stale") == 1


def test_run_pead2_scan_only_pending_skips_yahoo_when_complete():
    universe = _universe("AAA")
    cached = {
        "AAA": {
            "ticker": "AAA",
            "market": "NSE",
            "calc_version": PEAD2_CALC_VERSION,
            "lags": {
                "0": {
                    "result_date": "2025-05-15",
                    "quarter_end": "2025-03-31",
                    "returns_pct": 1.0,
                    "sales_yoy": 10.0,
                    "np_yoy": 5.0,
                    "eps_yoy": 5.0,
                },
                "1": {
                    "result_date": "2025-02-15",
                    "quarter_end": "2024-12-31",
                    "returns_pct": 0.5,
                },
            },
        }
    }
    with patch("stocks.strategies.pead2.service.load_pead2_cache", return_value=cached):
        with patch("stocks.strategies.pead2.service.analyze_pead2_ticker") as analyze:
            result = run_pead2_scan(universe, only_pending=True)
    analyze.assert_not_called()
    assert result["pending"] == 0
    assert result["fetched"] == 0
    assert not result["candidates"].empty


def test_run_pead2_scan_pending_mode_stale_only():
    universe = _universe("AAA", "BBB", "CCC")
    cached = {
        "AAA": {"ticker": "AAA", "calc_version": PEAD2_CALC_VERSION, "lags": {"0": {}}},
        "BBB": {"ticker": "BBB", "calc_version": PEAD2_CALC_VERSION - 1, "lags": {"0": {}}},
    }

    def _fake_analyze(ticker, market, **kwargs):
        return {"ticker": ticker, "market": market, "calc_version": PEAD2_CALC_VERSION, "lags": {"0": {}}}

    with patch("stocks.strategies.pead2.service.load_pead2_cache", return_value=cached):
        with patch(
            "stocks.strategies.pead2.service.analyze_pead2_ticker",
            side_effect=_fake_analyze,
        ) as analyze:
            with patch("stocks.strategies.pead2.service.save_pead2_cache"):
                result = run_pead2_scan(universe, only_pending=True, pending_mode="stale")
    analyze.assert_called_once()
    assert analyze.call_args.args[0] == "BBB"
    assert result["saved"] == 1
    assert result["pending_mode"] == "stale"


def test_run_pead2_batch_tombstones_failed_fetch_so_queue_drops():
    universe = _universe("AAA", "BBB")
    store: dict[str, dict] = {}

    def _fake_load(tickers, *, max_hours):
        return {t: store[t] for t in tickers if t in store}

    def _fake_save(rows):
        for row in rows:
            store[str(row["ticker"]).upper()] = row

    def _fake_analyze(ticker, market, **kwargs):
        if ticker == "AAA":
            return {
                "ticker": ticker,
                "market": market,
                "calc_version": PEAD2_CALC_VERSION,
                "lags": {"0": {"result_date": "2025-05-15"}},
            }
        return None

    with patch("stocks.strategies.pead2.service.load_pead2_cache", side_effect=_fake_load):
        with patch("stocks.strategies.pead2.service.save_pead2_cache", side_effect=_fake_save):
            with patch(
                "stocks.strategies.pead2.service.analyze_pead2_ticker",
                side_effect=_fake_analyze,
            ):
                result = run_pead2_scan(universe, only_pending=True, pending_mode="missing")

    assert result["saved"] == 1
    assert result["tombstoned"] == 1
    assert result["cleared"] == 2
    assert result["coverage"].missing == 0
    assert store["BBB"]["no_pead_data"] is True
