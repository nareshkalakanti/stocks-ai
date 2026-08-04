from stocks.core.text_utils import sanitize_website
from stocks.market.company_profile import merge_company_profile


def test_sanitize_website_rejects_google_search():
    raw = (
        "http://www.google.co.in/search?ie=UTF-8&amp;oe=UTF-8"
        "&sourceid=navclient&q=Cyber+Media"
    )
    assert sanitize_website(raw) is None


def test_sanitize_website_rejects_finance_portals():
    assert sanitize_website("https://finance.yahoo.com/quote/TCS.NS") is None
    assert sanitize_website("https://www.moneycontrol.com/india/stockpricequote/tcs") is None
    assert sanitize_website("https://www.hindalco.com/") == "https://www.hindalco.com/"


def test_sanitize_website_x_com_does_not_block_cleanmax():
    assert sanitize_website("https://x.com/someone") is None
    assert sanitize_website("https://www.cleanmax.com/") == "https://www.cleanmax.com/"


def test_sanitize_website_allows_exchange_homepage_only():
    assert sanitize_website("https://www.bseindia.com/") == "https://www.bseindia.com/"
    assert sanitize_website("https://www.bseindia.com/stock-share-price/x") is None


def test_merge_company_profile_drops_junk_website_from_db(monkeypatch):
    monkeypatch.setattr(
        "stocks.market.company_profile.load_company_profiles_from_db",
        lambda _tickers: {
            "CMRSL": {
                "website": (
                    "http://www.google.co.in/search?ie=UTF-8&amp;oe=UTF-8"
                    "&q=Cyber+Media+Research"
                ),
                "long_description": "Market research consultancy",
            }
        },
    )
    monkeypatch.setattr(
        "stocks.market.company_profile.fetch_screener_profile",
        lambda *_a, **_k: {},
    )

    out = merge_company_profile({}, "CMRSL", "NSE SME")
    assert out.get("website") is None
    assert out.get("long_description") == "Market research consultancy"
