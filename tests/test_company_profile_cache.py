from unittest.mock import patch

from stocks.core.database import get_connection, init_db, load_company_profiles_from_db, save_company_profiles
from stocks.market.company_profile import merge_company_profile


def _cleanup(ticker: str) -> None:
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM company_profile_cache WHERE ticker = ?", (ticker,))


def test_merge_company_profile_uses_db_without_rescrape():
    ticker = "ZZTESTPROFILE97"
    _cleanup(ticker)
    save_company_profiles(
        [
            {
                "ticker": ticker,
                "market": "NSE",
                "website": "https://example-cached.test",
                "long_description": "Cached about text.",
                "company_sector": "Industrials",
                "company_industry": "Packaging",
                "source": "screener",
            }
        ]
    )
    with patch("stocks.market.company_profile.fetch_screener_profile") as fetch:
        with patch("stocks.market.company_profile._fetch_yfinance_profile") as yf:
            out = merge_company_profile({}, ticker, "NSE")
    fetch.assert_not_called()
    yf.assert_not_called()
    assert out["website"] == "https://example-cached.test"
    assert out["long_description"] == "Cached about text."
    _cleanup(ticker)


def test_merge_company_profile_scrapes_once_then_stores_in_db():
    ticker = "ZZTESTPROFILE99"
    _cleanup(ticker)
    with patch(
        "stocks.market.company_profile.fetch_screener_profile",
        return_value={
            "website": "https://example.com",
            "long_description": "Fresh about.",
            "company_sector": "Industrials",
            "company_industry": "Packaging",
        },
    ) as fetch:
        with patch("stocks.market.company_profile._fetch_yfinance_profile", return_value=None):
            first = merge_company_profile({}, ticker, "NSE")
            second = merge_company_profile({}, ticker, "NSE")
    assert fetch.call_count == 1
    assert first["website"] == "https://example.com"
    assert second["long_description"] == "Fresh about."
    stored = load_company_profiles_from_db([ticker])
    assert stored[ticker]["website"] == "https://example.com"
    _cleanup(ticker)


def test_merge_company_profile_saves_complete_yfinance_profile():
    ticker = "ZZTESTPROFILE98"
    _cleanup(ticker)
    yf_profile = {
        "website": "https://yf.example.com",
        "long_description": "Yahoo about text.",
        "company_sector": "Industrials",
        "company_industry": "Engineering",
        "headquarters": "Mumbai, India",
    }
    with patch("stocks.market.company_profile.fetch_screener_profile") as fetch:
        with patch("stocks.market.company_profile._fetch_yfinance_profile") as yf:
            out = merge_company_profile(yf_profile, ticker, "NSE")
    fetch.assert_not_called()
    yf.assert_not_called()
    assert out["website"] == "https://yf.example.com"
    stored = load_company_profiles_from_db([ticker])
    assert stored[ticker]["long_description"] == "Yahoo about text."
    assert stored[ticker]["company_sector"] == "Industrials"
    assert stored[ticker]["source"] == "yfinance"
    _cleanup(ticker)
