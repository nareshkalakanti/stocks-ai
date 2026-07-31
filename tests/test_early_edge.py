"""Early Edge watchlist seed + Edge corp tag."""

from __future__ import annotations

import pandas as pd

from stocks.shared.corp_tags import clear_corp_tags_cache, corp_tags_dict_for_ticker
from stocks.shared.early_edge import (
    EARLY_EDGE_PLAYLIST_LABEL,
    enrich_watching_board,
    resolve_early_edge_queries,
    seed_early_edge,
)
from stocks.scans.scan_playlists import is_scan_playlist, scan_playlist_count


def test_enrich_watching_board_manual_bse_listing(monkeypatch):
    monkeypatch.setattr(
        "stocks.core.database.load_stocks_from_db",
        lambda: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "stocks.core.database.load_company_profiles_from_db",
        lambda _t: {},
    )
    monkeypatch.setattr(
        "stocks.core.database.load_market_cap_from_db",
        lambda _t, **kw: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "stocks.core.database.load_stock_prices_from_db",
        lambda _t, **kw: {},
    )
    monkeypatch.setattr(
        "stocks.market.price_service.fetch_current_prices",
        lambda _t, _m: {},
    )
    monkeypatch.setattr(
        "stocks.listings.classification_service.load_classification_maps",
        lambda: None,
    )

    df = pd.DataFrame([{"ticker": "TRUECOLORS", "name": "", "market": "", "sector": ""}])
    out = enrich_watching_board(df)
    row = out.iloc[0]
    assert row["market"] == "BSE"
    assert row["name"] == "True Colors Limited"
    assert "544531" in row["sc"]


def test_resolve_early_edge_core_names():
    df, unresolved = resolve_early_edge_queries(
        ["ENVIRO INFRA", "DAM CAPITAL", "Krsnaaa", "Gateway Distiparks"]
    )
    assert unresolved == []
    tickers = set(df["ticker"].astype(str).str.upper())
    assert {"EIEL", "DAMCAPITAL", "KRSNAA", "GATEWAY"} <= tickers


def test_seed_and_edge_tag(monkeypatch):
    # Use real DB seed (idempotent force).
    info = seed_early_edge(force=True)
    assert info["written"] >= 70
    assert not info["unresolved"]
    clear_corp_tags_cache()
    tags = corp_tags_dict_for_ticker("EIEL")
    assert tags.get("is_edge") is True
    assert is_scan_playlist(EARLY_EDGE_PLAYLIST_LABEL)
    assert scan_playlist_count(EARLY_EDGE_PLAYLIST_LABEL) == info["written"]
