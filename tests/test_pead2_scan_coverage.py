from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd

from stocks.core.config import PEAD2_CALC_VERSION
from stocks.strategies.pead2.service import (
    Pead2ScanCoverage,
    expand_pead_candidates_to_universe,
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


def _fresh_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aged_ts() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()


@contextmanager
def patch_pead_cache(cached: dict, *, fetched_at: dict[str, str] | None = None):
    """Patch PEAD cache loaders; default timestamps are recent (not aged)."""
    ts = {t: _fresh_ts() for t in cached}
    if fetched_at is not None:
        ts.update(fetched_at)
    with patch("stocks.strategies.pead2.service.load_pead2_cache", return_value=cached):
        with patch("stocks.strategies.pead2.service.load_pead2_fetched_at", return_value=ts):
            yield


def test_pead2_scan_coverage_counts_cached_stale_and_missing():
    universe = _universe("AAA", "BBB", "CCC")
    cached = {
        "AAA": {"ticker": "AAA", "calc_version": PEAD2_CALC_VERSION, "lags": {"0": {}}},
        "BBB": {"ticker": "BBB", "calc_version": PEAD2_CALC_VERSION - 1, "lags": {"0": {}}},
    }
    with patch_pead_cache(cached):
        coverage = pead2_scan_coverage(universe)
    assert coverage == Pead2ScanCoverage(
        universe_total=3,
        cached=1,
        stale=1,
        missing=1,
        scorable=1,
        aged=0,
    )
    assert coverage.pending_count("all") == 2
    assert coverage.pending_count("missing") == 1
    assert coverage.pending_count("stale") == 1
    assert coverage.pending_count("aged") == 0


def test_pead2_scan_coverage_counts_aged_cache():
    universe = _universe("AAA", "BBB")
    cached = {
        "AAA": {"ticker": "AAA", "calc_version": PEAD2_CALC_VERSION, "lags": {"0": {}}},
        "BBB": {"ticker": "BBB", "calc_version": PEAD2_CALC_VERSION, "lags": {"0": {}}},
    }
    with patch_pead_cache(cached, fetched_at={"AAA": _aged_ts(), "BBB": _fresh_ts()}):
        coverage = pead2_scan_coverage(universe)
    assert coverage.aged == 1
    assert coverage.pending_count("aged") == 1
    assert coverage.pending_count("all") == 1


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
    with patch_pead_cache(cached):
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

    with patch_pead_cache(cached):
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


def test_run_pead2_scan_pending_mode_aged_only():
    universe = _universe("AAA", "BBB")
    cached = {
        "AAA": {
            "ticker": "AAA",
            "market": "NSE",
            "calc_version": PEAD2_CALC_VERSION,
            "lags": {"0": {"result_date": "2025-05-15", "sales_yoy": 10.0, "np_yoy": 5.0, "eps_yoy": 5.0}},
            "1": {"result_date": "2025-02-15"},
        },
        "BBB": {
            "ticker": "BBB",
            "market": "NSE",
            "calc_version": PEAD2_CALC_VERSION,
            "lags": {"0": {"result_date": "2025-06-01", "sales_yoy": 8.0, "np_yoy": 4.0, "eps_yoy": 4.0}},
            "1": {"result_date": "2025-03-01"},
        },
    }

    def _fake_analyze(ticker, market, **kwargs):
        return cached[ticker]

    with patch_pead_cache(cached, fetched_at={"AAA": _aged_ts(), "BBB": _fresh_ts()}):
        with patch(
            "stocks.strategies.pead2.service.analyze_pead2_ticker",
            side_effect=_fake_analyze,
        ) as analyze:
            with patch("stocks.strategies.pead2.service.save_pead2_cache"):
                result = run_pead2_scan(universe, only_pending=True, pending_mode="aged")
    analyze.assert_called_once()
    assert analyze.call_args.args[0] == "AAA"
    assert result["pending_mode"] == "aged"
    assert result["fetched"] == 1


def test_run_pead2_batch_tombstones_failed_fetch_so_queue_drops():
    universe = _universe("AAA", "BBB")
    store: dict[str, dict] = {}

    def _fake_load(tickers, *, max_hours):
        return {t: store[t] for t in tickers if t in store}

    def _fake_fetched_at(tickers):
        return {t: _fresh_ts() for t in tickers if t in store}

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
        with patch("stocks.strategies.pead2.service.load_pead2_fetched_at", side_effect=_fake_fetched_at):
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


def test_pead2_scan_coverage_counts_scorable_and_no_data():
    universe = _universe("AAA", "BBB")
    cached = {
        "AAA": {"ticker": "AAA", "calc_version": PEAD2_CALC_VERSION, "lags": {"0": {}}},
        "BBB": {"ticker": "BBB", "calc_version": PEAD2_CALC_VERSION, "no_pead_data": True, "lags": {}},
    }
    with patch_pead_cache(cached):
        coverage = pead2_scan_coverage(universe)
    assert coverage.scorable == 1
    assert coverage.no_data == 1
    assert coverage.pending_count("no_data") == 1


def test_expand_pead_candidates_to_universe_includes_all_tickers():
    universe = _universe("AAA", "BBB", "CCC")
    candidates = pd.DataFrame(
        {
            "ticker": ["AAA"],
            "name": ["Alpha"],
            "market": ["NSE"],
            "sector": ["Industrials"],
            "pead_score": [42.5],
        }
    )
    cached = {
        "AAA": {"ticker": "AAA", "calc_version": PEAD2_CALC_VERSION, "lags": {"0": {}}},
        "BBB": {"ticker": "BBB", "calc_version": PEAD2_CALC_VERSION, "no_pead_data": True, "lags": {}},
    }
    with patch_pead_cache(cached):
        out = expand_pead_candidates_to_universe(universe, candidates)
    assert len(out) == 3
    assert out.loc[out["ticker"] == "AAA", "pead_score"].iloc[0] == 42.5
    assert pd.isna(out.loc[out["ticker"] == "BBB", "pead_score"].iloc[0])
    assert out.loc[out["ticker"] == "BBB", "pead_status"].iloc[0] == "No PEAD data"
    assert out.loc[out["ticker"] == "CCC", "pead_status"].iloc[0] == "Not scanned"


def test_expand_pead_candidates_to_universe_empty_candidates():
    universe = _universe("AAA", "BBB")
    with patch_pead_cache({}):
        out = expand_pead_candidates_to_universe(universe, pd.DataFrame())
    assert len(out) == 2
    assert "pead_score" in out.columns
    assert out["pead_score"].isna().all()
    assert (out["pead_status"] == "Not scanned").all()


def test_run_pead2_scan_pending_mode_no_data_only():
    universe = _universe("AAA", "BBB")
    cached = {
        "AAA": {"ticker": "AAA", "calc_version": PEAD2_CALC_VERSION, "lags": {"0": {}}},
        "BBB": {"ticker": "BBB", "calc_version": PEAD2_CALC_VERSION, "no_pead_data": True, "lags": {}},
    }

    def _fake_analyze(ticker, market, **kwargs):
        return {"ticker": ticker, "market": market, "calc_version": PEAD2_CALC_VERSION, "lags": {"0": {}}}

    with patch_pead_cache(cached):
        with patch(
            "stocks.strategies.pead2.service.analyze_pead2_ticker",
            side_effect=_fake_analyze,
        ) as analyze:
            with patch("stocks.strategies.pead2.service.save_pead2_cache"):
                result = run_pead2_scan(universe, only_pending=True, pending_mode="no_data")
    analyze.assert_called_once()
    assert analyze.call_args.args[0] == "BBB"
    assert result["pending_mode"] == "no_data"


def test_run_pead2_full_scan_does_not_refetch_fresh_cache():
    universe = _universe("AAA", "BBB")
    cached = {
        "AAA": {
            "ticker": "AAA",
            "market": "NSE",
            "calc_version": PEAD2_CALC_VERSION,
            "lags": {"0": {"result_date": "2025-05-15", "sales_yoy": 10.0, "np_yoy": 5.0, "eps_yoy": 5.0}},
            "1": {"result_date": "2025-02-15"},
        },
        "BBB": {
            "ticker": "BBB",
            "market": "NSE",
            "calc_version": PEAD2_CALC_VERSION,
            "lags": {"0": {"result_date": "2025-06-01", "sales_yoy": 8.0, "np_yoy": 4.0, "eps_yoy": 4.0}},
            "1": {"result_date": "2025-03-01"},
        },
    }
    with patch_pead_cache(cached):
        with patch("stocks.strategies.pead2.service.analyze_pead2_ticker") as analyze:
            result = run_pead2_scan(universe, only_pending=False)
    analyze.assert_not_called()
    assert result["fetched"] == 0
    assert result["pending"] == 0
    assert len(result["candidates"]) == 2


def test_run_pead2_full_scan_refetches_aged_cache():
    universe = _universe("AAA", "BBB")
    cached = {
        "AAA": {
            "ticker": "AAA",
            "market": "NSE",
            "calc_version": PEAD2_CALC_VERSION,
            "lags": {"0": {"result_date": "2025-05-15", "sales_yoy": 10.0, "np_yoy": 5.0, "eps_yoy": 5.0}},
            "1": {"result_date": "2025-02-15"},
        },
        "BBB": {
            "ticker": "BBB",
            "market": "NSE",
            "calc_version": PEAD2_CALC_VERSION,
            "lags": {"0": {"result_date": "2025-06-01", "sales_yoy": 8.0, "np_yoy": 4.0, "eps_yoy": 4.0}},
            "1": {"result_date": "2025-03-01"},
        },
    }

    def _fake_analyze(ticker, market, **kwargs):
        return cached[ticker]

    with patch_pead_cache(cached, fetched_at={"AAA": _aged_ts(), "BBB": _fresh_ts()}):
        with patch(
            "stocks.strategies.pead2.service.analyze_pead2_ticker",
            side_effect=_fake_analyze,
        ) as analyze:
            with patch("stocks.strategies.pead2.service.save_pead2_cache"):
                result = run_pead2_scan(universe, only_pending=False)
    analyze.assert_called_once()
    assert analyze.call_args.args[0] == "AAA"
    assert result["fetched"] == 1


def test_run_pead2_full_scan_retries_no_data_tombstone():
    universe = _universe("AAA")
    cached = {
        "AAA": {
            "ticker": "AAA",
            "market": "NSE",
            "calc_version": PEAD2_CALC_VERSION,
            "no_pead_data": True,
            "lags": {},
        },
    }

    def _fake_analyze(ticker, market, **kwargs):
        return {
            "ticker": ticker,
            "market": market,
            "calc_version": PEAD2_CALC_VERSION,
            "lags": {
                "0": {
                    "result_date": "2025-05-15",
                    "sales_yoy": 10.0,
                    "np_yoy": 5.0,
                    "eps_yoy": 5.0,
                },
                "1": {"result_date": "2025-02-15"},
            },
        }

    with patch_pead_cache(cached):
        with patch(
            "stocks.strategies.pead2.service.analyze_pead2_ticker",
            side_effect=_fake_analyze,
        ) as analyze:
            with patch("stocks.strategies.pead2.service.save_pead2_cache"):
                result = run_pead2_scan(universe, only_pending=False)
    analyze.assert_called_once_with("AAA", "NSE", min_mcap_cr=None)
    assert result["fetched"] == 1


def test_pead2_ebidt_series_falls_back_to_pretax_income():
    import pandas as pd

    from stocks.strategies.pead2.service import _pead2_ebidt_series

    income = pd.DataFrame(
        {
            pd.Timestamp("2024-03-31"): [100.0],
            pd.Timestamp("2024-06-30"): [110.0],
            pd.Timestamp("2024-09-30"): [120.0],
            pd.Timestamp("2024-12-31"): [130.0],
        },
        index=["Pretax Income"],
    )
    series = _pead2_ebidt_series(income)
    assert series is not None
    assert len(series) == 4


def test_pead2_passes_earnings_quality_allows_short_eps_history():
    import pandas as pd

    from stocks.strategies.pead2.service import _pead2_passes_earnings_quality

    idx = pd.date_range("2024-03-31", periods=3, freq="QE")
    net_profit = pd.Series([10.0, 11.0, 12.0], index=idx)
    eps = pd.Series([1.0, 1.1, 1.2], index=idx)
    assert _pead2_passes_earnings_quality(net_profit, eps) is True
