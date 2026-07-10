from stocks.market.screener_profile import fetch_screener_profile


def test_fetch_screener_profile_gsmfoils():
    profile = fetch_screener_profile("GSMFOILS", "NSE")
    assert profile.get("website")
    assert "gsmfoils" in profile["website"].lower()
    assert profile.get("long_description")
    assert "GSM Foils" in profile["long_description"]
