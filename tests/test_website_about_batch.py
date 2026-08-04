"""Batch About scrape helpers (offline)."""

from __future__ import annotations

import pandas as pd

from stocks.market.website_about_batch import about_gap_tickers, batch_stats


def test_about_gap_tickers_missing_only(monkeypatch):
    listings = pd.DataFrame(
        [
            {"ticker": "AAA", "name": "Aaa", "market": "NSE", "sector": "X"},
            {"ticker": "BBB", "name": "Bbb", "market": "NSE SME", "sector": "Y"},
            {"ticker": "CCC", "name": "Ccc", "market": "NSE", "sector": "Z"},
        ]
    )
    monkeypatch.setattr(
        "stocks.market.website_about_batch.load_company_profiles_from_db",
        lambda tickers: {
            "AAA": {"long_description": "Has about", "website": "https://a.com", "source": "yfinance"},
            "BBB": {"long_description": "", "website": "", "source": ""},
            "CCC": {
                "long_description": "From site",
                "website": "https://c.com",
                "source": "website_about",
            },
        },
    )
    gaps = about_gap_tickers(listings, missing_about_only=True, refresh_existing=False)
    assert set(gaps["ticker"]) == {"BBB"}


def test_about_gap_tickers_missing_website(monkeypatch):
    listings = pd.DataFrame(
        [
            {"ticker": "AAA", "name": "Aaa", "market": "NSE", "sector": "X"},
            {"ticker": "BBB", "name": "Bbb", "market": "NSE", "sector": "Y"},
        ]
    )
    monkeypatch.setattr(
        "stocks.market.website_about_batch.load_company_profiles_from_db",
        lambda tickers: {
            "AAA": {"long_description": "Has about", "website": "https://a.com", "source": "yfinance"},
            "BBB": {"long_description": "About only", "website": "", "source": "yfinance"},
        },
    )
    gaps = about_gap_tickers(listings, missing_website_only=True, refresh_existing=False)
    assert set(gaps["ticker"]) == {"BBB"}


def test_about_gap_skips_not_found(monkeypatch):
    listings = pd.DataFrame(
        [
            {"ticker": "AAA", "name": "Aaa", "market": "NSE", "sector": "X"},
            {"ticker": "BBB", "name": "Bbb", "market": "NSE", "sector": "Y"},
            {"ticker": "CCC", "name": "Ccc", "market": "NSE", "sector": "Z"},
        ]
    )
    monkeypatch.setattr(
        "stocks.market.website_about_batch.load_company_profiles_from_db",
        lambda tickers: {
            "AAA": {
                "long_description": "",
                "website": "",
                "source": "no_website",
                "website_status": "not_found",
            },
            "BBB": {"long_description": "", "website": "", "source": "", "website_status": ""},
            "CCC": {
                "long_description": "",
                "website": "https://c.com",
                "source": "web_search",
                "website_status": "ok",
            },
        },
    )
    monkeypatch.setattr(
        "stocks.market.website_about_batch.official_nse_symbols",
        lambda: {"AAA", "BBB", "CCC"},
    )
    gaps = about_gap_tickers(listings, missing_website_only=True, refresh_existing=False)
    assert set(gaps["ticker"]) == {"BBB"}

    force = about_gap_tickers(listings, missing_website_only=True, refresh_existing=True)
    assert set(force["ticker"]) == {"AAA", "BBB", "CCC"}

    from stocks.market.website_about_batch import website_not_found_rows

    missed = website_not_found_rows(listings)
    assert set(missed["ticker"]) == {"AAA"}
    assert bool(missed.iloc[0]["listed"]) is True


def test_batch_stats():
    stats = batch_stats(
        [
            {"ok": True, "skipped": False, "reason": "saved"},
            {"ok": True, "skipped": True, "reason": "already_have_website_about"},
            {"ok": False, "skipped": False, "reason": "no_website"},
            {
                "ok": False,
                "skipped": False,
                "reason": "no_proper_website",
                "website_status": "not_found",
            },
        ]
    )
    assert stats["saved"] == 1
    assert stats["skipped"] == 1
    assert stats["failed"] == 2
    assert stats["not_found"] == 1
    assert stats["total"] == 4
