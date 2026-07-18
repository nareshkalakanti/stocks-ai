"""Headwind / Tailwind (H&T) scan helpers and ranking."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from stocks.market.fundamentals_service import apply_cap_tier_filter, apply_market_cap_filter
from stocks.pages.headwind_tailwind import _resolve_mcap_floor, _scan_universe
from stocks.scans.scan_universe import cap_tier_min_mcap_cr
from stocks.strategies.intrinsic_value.service import (
    _finalize_intrinsic_value_scan,
    assemble_headwind_from_iv_cache,
    shrink_universe_by_mcap,
)
from stocks.strategies.intrinsic_value.strategy import rank_intrinsic_value, sector_headwind_tailwind


def _sample_stocks(*tickers: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": list(tickers),
            "market": ["NSE"] * len(tickers),
            "name": list(tickers),
            "sector": ["IT & Technology"] * len(tickers),
            "industry": ["Software"] * len(tickers),
        }
    )


def _sample_iv_rows() -> list[dict]:
    return [
        {
            "ticker": "AAA",
            "market": "NSE",
            "name": "Alpha Ltd",
            "price": 100.0,
            "market_cap_cr": 50.0,
            "sales_growth_3y": 25.0,
            "roce_3y": 30.0,
            "pb": 1.5,
            "pe_ratio": 18.0,
            "forward_pe": 16.0,
            "industry": "Software",
            "sector": "IT & Technology",
        },
        {
            "ticker": "BBB",
            "market": "NSE",
            "name": "Beta Ltd",
            "price": 200.0,
            "market_cap_cr": 80.0,
            "sales_growth_3y": 15.0,
            "roce_3y": 20.0,
            "pb": 2.0,
            "pe_ratio": 22.0,
            "forward_pe": 20.0,
            "industry": "Software",
            "sector": "IT & Technology",
        },
    ]


def test_resolve_mcap_floor_all_caps_has_no_floor():
    assert _resolve_mcap_floor("all") == 0.0
    assert _resolve_mcap_floor("") == 0.0
    assert cap_tier_min_mcap_cr("all") is None


def test_resolve_mcap_floor_named_tier_uses_tier_minimum():
    assert _resolve_mcap_floor("large") == 20000.0
    assert _resolve_mcap_floor("micro") == 100.0


def test_scan_universe_all_caps_keeps_full_list_without_db_mcap():
    stocks = _sample_stocks("AAA", "BBB", "CCC")
    universe, stats = _scan_universe(stocks, "All", min_cr=0.0)
    assert len(universe) == 3
    assert stats["eligible"] == 3
    assert stats["missing"] == 0


def test_scan_universe_with_floor_uses_db_mcap_filter():
    stocks = _sample_stocks("AAA", "BBB")
    cached = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB"],
            "market_cap_cr": [500.0, 50.0],
        }
    )
    with patch(
        "stocks.strategies.intrinsic_value.service.load_market_cap_from_db",
        return_value=cached,
    ):
        universe, stats = _scan_universe(stocks, "All", min_cr=200.0)
    assert list(universe["ticker"]) == ["AAA"]
    assert stats["eligible"] == 1
    assert stats["below_floor"] == 1


def test_apply_market_cap_filter_zero_floor_keeps_sub_floor_names():
    df = pd.DataFrame(
        {
            "ticker": ["NANO", "MID"],
            "market_cap_cr": [25.0, 800.0],
        }
    )
    kept, excluded = apply_market_cap_filter(df, min_cr=0.0)
    assert len(kept) == 2
    assert excluded == 0


def test_shrink_universe_by_mcap_zero_floor_keeps_unknown_caps(monkeypatch):
    universe = _sample_stocks("AAA", "BBB")
    monkeypatch.setattr(
        "stocks.strategies.intrinsic_value.service.load_market_cap_from_db",
        lambda _tickers: pd.DataFrame(columns=["ticker", "market_cap_cr"]),
    )
    shrunk, excluded = shrink_universe_by_mcap(universe, min_cr=0.0)
    assert len(shrunk) == 2
    assert excluded == 0


def test_rank_intrinsic_value_matches_screenshot_columns():
    ranked = rank_intrinsic_value(pd.DataFrame(_sample_iv_rows()))
    assert list(ranked.columns[:8]) == [
        "rank",
        "ticker",
        "market",
        "name",
        "price",
        "market_cap_cr",
        "sales_growth_3y",
        "roce_3y",
    ]
    assert "total_score" in ranked.columns
    assert ranked.iloc[0]["rank"] == 1
    assert ranked["total_score"].notna().all()


def test_finalize_scan_builds_sector_board_with_min_one_company():
    result = _finalize_intrinsic_value_scan(
        _sample_iv_rows(),
        scanned_total=2,
        min_sector_companies=1,
    )
    assert result["with_data"] == 2
    assert not result["sectors"].empty
    assert result["sectors"].iloc[0]["sector"] == "IT & Technology"
    assert result["industry_col"] == "sector"


def test_sector_headwind_tailwind_single_company_group():
    ranked = rank_intrinsic_value(pd.DataFrame(_sample_iv_rows()))
    board = sector_headwind_tailwind(ranked, industry_col="industry", min_companies=1)
    assert len(board) == 1
    assert board.iloc[0]["companies"] == 2


def test_assemble_headwind_from_iv_cache_respects_zero_floor():
    universe = _sample_stocks("AAA", "BBB")
    cached = pd.DataFrame(_sample_iv_rows())

    with patch(
        "stocks.strategies.intrinsic_value.service.load_cached_iv_rows",
        return_value=cached,
    ):
        built = assemble_headwind_from_iv_cache(
            universe,
            min_mcap_cr=0.0,
            min_sector_companies=1,
        )

    assert built is not None
    assert built["with_data"] == 2
    assert not built["ranked"].empty


def test_assemble_headwind_from_iv_cache_excludes_below_floor_when_set():
    rows = _sample_iv_rows()
    rows[0]["market_cap_cr"] = 50.0
    rows[1]["market_cap_cr"] = 150.0
    universe = _sample_stocks("AAA", "BBB")
    cached = pd.DataFrame(rows)

    with patch(
        "stocks.strategies.intrinsic_value.service.load_cached_iv_rows",
        return_value=cached,
    ):
        built = assemble_headwind_from_iv_cache(
            universe,
            min_mcap_cr=100.0,
            min_sector_companies=1,
        )

    assert built is not None
    assert list(built["ranked"]["ticker"]) == ["BBB"]


def _cement_iv_rows() -> list[dict]:
    """Fixture shaped like the cement industry ranking screenshot."""
    industry = "Cement & Cement Products"
    sector = "Real Estate & Construction"
    rows = [
        ("ACC", "ACC Ltd", 14.04, 25.52, 1.92),
        ("KCP", "KCP Ltd", 12.0, 22.0, 2.1),
        ("BARAKCEM", "Barak Valley Cements", 10.5, 20.0, 2.0),
        ("STARCEMENT", "Star Cement", 9.0, 18.0, 2.3),
        ("BIRLACORPN", "Birla Corporation", 8.0, 17.0, 2.5),
        ("JKCEMENT", "JK Cement", 0.31, 12.66, 4.29),
    ]
    out: list[dict] = []
    for ticker, name, growth, roce, pb in rows:
        out.append(
            {
                "ticker": ticker,
                "market": "NSE",
                "name": name,
                "price": 100.0,
                "market_cap_cr": 5000.0,
                "sales_growth_3y": growth,
                "roce_3y": roce,
                "pb": pb,
                "pe_ratio": 18.0,
                "forward_pe": 16.0,
                "industry": industry,
                "sector": sector,
            }
        )
    return out


def test_cement_industry_ranking_matches_screenshot_order():
    ranked = rank_intrinsic_value(pd.DataFrame(_cement_iv_rows()))
    assert len(ranked) == 6
    assert ranked.iloc[0]["ticker"] == "ACC"
    assert ranked.iloc[0]["rank"] == 1
    assert ranked.iloc[0]["total_score"] < ranked.iloc[-1]["total_score"]
    assert list(ranked["ticker"].tail(1)) == ["JKCEMENT"]


def test_cement_industry_builds_single_sector_board():
    rows = _cement_iv_rows()
    result = _finalize_intrinsic_value_scan(
        rows,
        scanned_total=len(rows),
        min_sector_companies=1,
    )
    assert result["with_data"] == 6
    assert result["industry_col"] == "sector"
    assert len(result["sectors"]) == 1
    assert result["sectors"].iloc[0]["sector"] == "Real Estate & Construction"
    assert int(result["sectors"].iloc[0]["companies"]) == 6


def test_cement_industry_filter_keeps_cement_listings_only():
    from stocks.scans.stock_filters import apply_stock_filters, StockFilters

    stocks = pd.DataFrame(
        {
            "ticker": ["ACC", "JKCEMENT", "TCS"],
            "market": ["NSE", "NSE", "NSE"],
            "name": ["ACC Ltd", "JK Cement", "TCS"],
            "sector": ["Real Estate & Construction"] * 3,
            "industry": [
                "Cement & Cement Products",
                "Cement & Cement Products",
                "Software",
            ],
        }
    )
    filters = StockFilters(
        market="All",
        sectors=[],
        industries=["Cement & Cement Products"],
        search="",
    )
    filtered = apply_stock_filters(stocks, filters)
    assert list(filtered["ticker"]) == ["ACC", "JKCEMENT"]


def test_industry_filter_matches_display_sector_peers_without_tags():
    from stocks.scans.stock_filters import StockFilters, apply_stock_filters

    stocks = pd.DataFrame(
        {
            "ticker": ["ACC", "JKCEMENT", "TCS"],
            "market": ["NSE", "NSE", "NSE"],
            "name": ["ACC Ltd", "JK Cement", "TCS"],
            "sector": [
                "Real Estate & Construction",
                "Real Estate & Construction",
                "IT & Technology",
            ],
            "industry": ["", "", ""],
            "sub_sector": ["", "", ""],
        }
    )
    filters = StockFilters(
        market="All",
        sectors=[],
        industries=["Cement & Cement Products"],
        search="",
    )
    filtered = apply_stock_filters(stocks, filters)
    assert list(filtered["ticker"]) == ["ACC", "JKCEMENT"]


def test_my_industries_matches_sub_sector_peers():
    from stocks.scans.holdings_playlist import filter_stocks_by_holdings_industries

    stocks = pd.DataFrame(
        {
            "ticker": ["EPACKPEB", "PEER", "OTHER"],
            "market": ["NSE", "NSE", "NSE"],
            "name": ["Epack Prefab", "Peer Prefab", "Other Co"],
            "sector": ["Industrials", "Industrials", "Technology"],
            "industry": ["", "", "Software"],
            "sub_sector": [
                "Building Products - Prefab Structures",
                "Building Products - Prefab Structures",
                "Software",
            ],
        }
    )
    fine_labels = {"Building Products - Prefab Structures", "Finance"}
    with patch(
        "stocks.scans.holdings_playlist.holdings_industry_match_spec",
        return_value=(fine_labels, set()),
    ):
        with patch(
            "stocks.listings.classification_service.enrich_stocks_classification",
            side_effect=lambda df, **_: df,
        ):
            out = filter_stocks_by_holdings_industries(stocks)
    assert list(out["ticker"]) == ["EPACKPEB", "PEER"]


def test_my_industries_matches_display_sector_peers():
    from stocks.scans.holdings_playlist import filter_stocks_by_holdings_industries

    stocks = pd.DataFrame(
        {
            "ticker": ["HDFCBANK", "ICICIBANK", "INFY"],
            "market": ["NSE", "NSE", "NSE"],
            "name": ["HDFC Bank", "ICICI Bank", "Infosys"],
            "sector": ["Banking & Finance", "Banking & Finance", "IT & Technology"],
            "industry": ["", "", ""],
            "sub_sector": ["", "", ""],
        }
    )
    with patch(
        "stocks.scans.holdings_playlist.holdings_industry_match_spec",
        return_value=(set(), {"Banking & Finance"}),
    ):
        with patch(
            "stocks.listings.classification_service.enrich_stocks_classification",
            side_effect=lambda df, **_: df,
        ):
            out = filter_stocks_by_holdings_industries(stocks)
    assert list(out["ticker"]) == ["HDFCBANK", "ICICIBANK"]


def test_resolve_scan_group_col_falls_back_when_industry_tags_sparse():
    from stocks.strategies.intrinsic_value.service import resolve_scan_group_col

    rows = []
    for i, ticker in enumerate(["H1", "H2", "H3", "H4"]):
        rows.append(
            {
                "ticker": ticker,
                "industry": "Finance",
                "sector": "Banking & Finance",
                "sales_growth_3y": 1.0,
                "roce_3y": 1.0,
                "pb": 1.0,
                "total_score": 100.0,
            }
        )
    for ticker in ["P1", "P2", "P3", "P4", "P5", "P6"]:
        rows.append(
            {
                "ticker": ticker,
                "industry": "",
                "sector": "Banking & Finance",
                "sales_growth_3y": 2.0,
                "roce_3y": 2.0,
                "pb": 1.5,
                "total_score": 90.0,
            }
        )
    ranked = pd.DataFrame(rows)
    assert resolve_scan_group_col(ranked) == "sector"
    assert resolve_scan_group_col(ranked, force_display_sector=True) == "sector"


def test_finalize_scan_groups_by_sector_when_industry_sparse():
    rows = []
    for ticker in ["H1", "H2", "H3", "H4"]:
        rows.append(
            {
                "ticker": ticker,
                "market": "NSE",
                "name": ticker,
                "price": 100.0,
                "market_cap_cr": 500.0,
                "sales_growth_3y": 10.0,
                "roce_3y": 10.0,
                "pb": 1.0,
                "pe_ratio": 12.0,
                "forward_pe": 11.0,
                "industry": "Finance",
                "sector": "Banking & Finance",
            }
        )
    for ticker in ["P1", "P2", "P3", "P4", "P5", "P6"]:
        rows.append(
            {
                "ticker": ticker,
                "market": "NSE",
                "name": ticker,
                "price": 100.0,
                "market_cap_cr": 600.0,
                "sales_growth_3y": 12.0,
                "roce_3y": 11.0,
                "pb": 1.2,
                "pe_ratio": 14.0,
                "forward_pe": 13.0,
                "industry": "",
                "sector": "Banking & Finance",
            }
        )
    result = _finalize_intrinsic_value_scan(
        rows,
        scanned_total=len(rows),
        min_sector_companies=1,
    )
    assert result["industry_col"] == "sector"
    assert len(result["sectors"]) == 1
    assert result["sectors"].iloc[0]["sector"] == "Banking & Finance"
    assert int(result["sectors"].iloc[0]["companies"]) == 10


def test_stocks_by_sector_falls_back_to_sector_column():
    from stocks.strategies.intrinsic_value.html import _stocks_by_sector

    sectors = pd.DataFrame(
        [{"sector": "Real Estate & Construction", "companies": 1, "score": -0.2}]
    )
    ranked = pd.DataFrame(
        [
            {
                "ticker": "ACC",
                "sector": "Real Estate & Construction",
                "industry": "",
                "sub_sector": "",
                "sales_growth_3y": 1.0,
                "roce_3y": 1.0,
                "pb": 1.0,
                "total_score": 100.0,
            }
        ]
    )
    stocks = _stocks_by_sector(sectors, ranked, "industry")
    assert len(stocks["Real Estate & Construction"]) == 1
    assert stocks["Real Estate & Construction"][0]["ticker"] == "ACC"


def test_apply_cap_tier_filter_micro_excludes_large_names():
    df = pd.DataFrame(
        {
            "ticker": ["MICRO", "BIG"],
            "market_cap_cr": [150.0, 5000.0],
        }
    )
    kept, excluded = apply_cap_tier_filter(df, "micro")
    assert list(kept["ticker"]) == ["MICRO"]
    assert excluded == 1
