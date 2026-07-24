"""NSE index constituents + Nifty playlist wiring."""

from __future__ import annotations

from stocks.market.nse_index_constituents import (
    NIFTY_INDEXES,
    ensure_index_constituents,
    index_tickers,
    load_index_constituents,
    replace_index_constituents,
)
from stocks.scans.nifty_index_playlist import (
    is_nifty_index_playlist,
    nifty_playlist_listings,
)
from stocks.scans.scan_playlists import (
    is_scan_playlist,
    scan_playlist_count,
    scan_playlist_listings,
)


def test_parse_and_store_index_constituents(tmp_path, monkeypatch):
    db_path = tmp_path / "stocks_ai_test.db"
    monkeypatch.setattr("stocks.core.database.DB_PATH", db_path)
    monkeypatch.setattr("stocks.core.config.DB_PATH", db_path)
    monkeypatch.setattr(
        "stocks.market.nse_index_constituents.fetch_index_constituents_from_nse",
        lambda index_id, session=None: [
            {
                "index_id": index_id,
                "ticker": "FAKELARGE",
                "name": "Fake Large Ltd.",
                "industry": "Financial Services",
                "isin": "INE000A01001",
                "series": "EQ",
                "fetched_at": "2026-07-23T00:00:00+00:00",
            },
            {
                "index_id": index_id,
                "ticker": "FAKESMALL",
                "name": "Fake Small Ltd.",
                "industry": "Consumer Services",
                "isin": "INE000A01003",
                "series": "EQ",
                "fetched_at": "2026-07-23T00:00:00+00:00",
            },
        ],
    )

    result = ensure_index_constituents("NIFTY_500", force=True)
    assert result["refreshed"] is True
    assert result["count"] == 2
    df = load_index_constituents("NIFTY_500")
    assert set(df["ticker"]) == {"FAKELARGE", "FAKESMALL"}
    assert "Financial Services" in set(df["industry"].astype(str))
    assert index_tickers("NIFTY_500", seed_if_empty=False) == {"FAKELARGE", "FAKESMALL"}

    # Fresh cache — no second fetch.
    result2 = ensure_index_constituents("NIFTY_500", force=False)
    assert result2["refreshed"] is False
    assert result2["count"] == 2


def test_nifty_playlist_listings_merge_sector(tmp_path, monkeypatch):
    db_path = tmp_path / "stocks_ai_playlist.db"
    monkeypatch.setattr("stocks.core.database.DB_PATH", db_path)
    monkeypatch.setattr("stocks.core.config.DB_PATH", db_path)

    replace_index_constituents(
        "NIFTY_SMALLCAP_250",
        [
            {
                "index_id": "NIFTY_SMALLCAP_250",
                "ticker": "ONLYNSE",
                "name": "Only In Index Ltd.",
                "industry": "Power",
                "isin": "INE999A01001",
                "series": "EQ",
                "fetched_at": "2026-07-23T00:00:00+00:00",
            }
        ],
    )

    import pandas as pd

    stocks = pd.DataFrame(
        [
            {
                "ticker": "RELIANCE",
                "name": "Reliance",
                "market": "NSE",
                "sector": "Energy",
                "industry": "Oil",
                "sub_sector": "Oil",
            }
        ]
    )
    out = nifty_playlist_listings(stocks, "Nifty Smallcap 250")
    assert list(out["ticker"]) == ["ONLYNSE"]
    assert out.iloc[0]["sector"] == "Power"
    assert is_nifty_index_playlist("Nifty Smallcap 250")
    assert is_scan_playlist("Nifty 500")
    assert "Nifty Midcap 150" in {m["label"] for m in NIFTY_INDEXES.values()}
    assert scan_playlist_count("Nifty Smallcap 250") == 1


def test_scan_playlist_listings_routes_nifty(tmp_path, monkeypatch):
    db_path = tmp_path / "stocks_ai_route.db"
    monkeypatch.setattr("stocks.core.database.DB_PATH", db_path)
    monkeypatch.setattr("stocks.core.config.DB_PATH", db_path)
    replace_index_constituents(
        "NIFTY_50",
        [
            {
                "index_id": "NIFTY_50",
                "ticker": "TCS",
                "name": "TCS",
                "industry": "IT",
                "isin": "INE467B01029",
                "series": "EQ",
                "fetched_at": "2026-07-23T00:00:00+00:00",
            }
        ],
    )
    import pandas as pd

    stocks = pd.DataFrame(
        [{"ticker": "TCS", "name": "TCS", "market": "NSE", "sector": "IT"}]
    )
    out = scan_playlist_listings(stocks, "Nifty 50")
    assert list(out["ticker"]) == ["TCS"]
