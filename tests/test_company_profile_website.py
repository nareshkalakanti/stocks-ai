from stocks.core.text_utils import sanitize_website
from stocks.market.company_profile import merge_company_profile


def test_sanitize_website_rejects_google_search():
    raw = (
        "http://www.google.co.in/search?ie=UTF-8&amp;oe=UTF-8"
        "&sourceid=navclient&q=Cyber+Media"
    )
    assert sanitize_website(raw) is None


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
