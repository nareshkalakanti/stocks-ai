"""PEAD score lookup for cross-strategy dashboards."""

import pandas as pd

from stocks.strategies.pead2.cache_lookup import (
    _pead_blob_scorable,
    attach_pead_scores,
    backfill_pead_cache_for_tickers,
    count_pead_backfill_pending,
)


def test_count_pead_backfill_includes_no_pead_data_tombstone(monkeypatch):
    cached = {
        "AAA": {"no_pead_data": True, "lags": {}},
        "BBB": {"lags": {"0": {"sales_yoy": 1.0}}},
    }

    def _fake_load(tickers, *, max_hours):
        return {k: cached[k] for k in tickers if k in cached}

    monkeypatch.setattr(
        "stocks.strategies.pead2.cache_lookup.load_pead2_cache",
        _fake_load,
    )

    assert count_pead_backfill_pending(["AAA", "BBB", "CCC"], max_hours=168) == 2


def test_backfill_retries_no_pead_data_tombstone(monkeypatch):
    store = {"OLD": {"no_pead_data": True, "lags": {}}}

    def _fake_load(tickers, *, max_hours):
        return {k: store[k] for k in tickers if k in store}

    def _fake_save(rows):
        for row in rows:
            store[row["ticker"].upper()] = row

    def _fake_analyze(ticker, market):
        if ticker == "OLD":
            return {
                "ticker": "OLD",
                "market": market,
                "calc_version": 18,
                "lags": {"0": {"sales_yoy": 10.0, "np_yoy": 5.0, "eps_yoy": 5.0}},
            }
        return None

    monkeypatch.setattr(
        "stocks.strategies.pead2.cache_lookup.load_pead2_cache",
        _fake_load,
    )
    monkeypatch.setattr(
        "stocks.strategies.pead2.cache_lookup.save_pead2_cache",
        _fake_save,
    )
    monkeypatch.setattr(
        "stocks.strategies.pead2.service.analyze_pead2_ticker",
        _fake_analyze,
    )
    monkeypatch.setattr(
        "stocks.strategies.pead2.cache_lookup.pead_missing_reason",
        lambda _t, _m: "No PEAD data",
    )

    n = backfill_pead_cache_for_tickers(["OLD"], ["BSE"], max_fetch=5, max_workers=1)
    assert n == 1
    assert _pead_blob_scorable(store["OLD"])


def test_attach_pead_scores_sets_note_when_missing(monkeypatch):
    monkeypatch.setattr(
        "stocks.strategies.pead2.cache_lookup.load_pead_scores_by_ticker",
        lambda _tickers, max_hours: {},
    )
    monkeypatch.setattr(
        "stocks.strategies.pead2.cache_lookup._pead_notes_from_cache",
        lambda _tickers, max_hours: {"AAA": "No quarterly earnings on Yahoo"},
    )

    out = attach_pead_scores(
        pd.DataFrame([{"ticker": "AAA"}]),
        max_hours=168,
    )
    assert pd.isna(out.loc[0, "pead_score"])
    assert out.loc[0, "pead_note"] == "No quarterly earnings on Yahoo"
