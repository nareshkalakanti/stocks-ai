from unittest.mock import patch

from stocks.core.database import get_connection, init_db, load_company_profiles_from_db, save_company_profiles
from stocks.market.company_profile import merge_company_profile


def test_merge_company_profile_uses_db_without_rescrape():
    save_company_profiles(
        [
            {
                "ticker": "GSMFOILS",
                "market": "NSE",
                "website": "https://gsmfoils.com",
                "long_description": "Cached about text.",
                "source": "screener",
            }
        ]
    )
    with patch("stocks.market.company_profile.fetch_screener_profile") as fetch:
        out = merge_company_profile({}, "GSMFOILS", "NSE")
    fetch.assert_not_called()
    assert out["website"] == "https://gsmfoils.com"
    assert out["long_description"] == "Cached about text."


def test_merge_company_profile_scrapes_once_then_stores_in_db():
    ticker = "ZZTESTPROFILE99"
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM company_profile_cache WHERE ticker = ?", (ticker,))
    with patch(
        "stocks.market.company_profile.fetch_screener_profile",
        return_value={
            "website": "https://example.com",
            "long_description": "Fresh about.",
        },
    ) as fetch:
        first = merge_company_profile({}, ticker, "NSE")
        second = merge_company_profile({}, ticker, "NSE")
    assert fetch.call_count == 1
    assert first["website"] == "https://example.com"
    assert second["long_description"] == "Fresh about."
    stored = load_company_profiles_from_db([ticker])
    assert stored[ticker]["website"] == "https://example.com"


def test_merge_company_profile_saves_complete_yfinance_profile():
    ticker = "ZZTESTPROFILE98"
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM company_profile_cache WHERE ticker = ?", (ticker,))
    yf_profile = {
        "website": "https://yf.example.com",
        "long_description": "Yahoo about text.",
        "company_sector": "Industrials",
        "company_industry": "Engineering",
        "headquarters": "Mumbai, India",
    }
    with patch("stocks.market.company_profile.fetch_screener_profile") as fetch:
        out = merge_company_profile(yf_profile, ticker, "NSE")
    fetch.assert_not_called()
    assert out["website"] == "https://yf.example.com"
    stored = load_company_profiles_from_db([ticker])
    assert stored[ticker]["long_description"] == "Yahoo about text."
    assert stored[ticker]["company_sector"] == "Industrials"
    assert stored[ticker]["source"] == "yfinance"
