from stocks.market.screener_profile import (
    fetch_screener_current_price,
    fetch_screener_profile,
)


def test_fetch_screener_profile_gsmfoils():
    profile = fetch_screener_profile("GSMFOILS", "NSE")
    assert profile.get("website")
    assert "gsmfoils" in profile["website"].lower()
    assert profile.get("long_description")
    assert "GSM Foils" in profile["long_description"]


def test_fetch_screener_profile_parses_current_price(monkeypatch):
    html = """
    <ul id="top-ratios">
      <li><span class="name">Current Price</span><span class="number">162</span></li>
      <li><span class="name">Market Cap</span><span class="number">399</span> Cr.</li>
    </ul>
    """

    class _Resp:
        text = html

        def raise_for_status(self):
            return None

    monkeypatch.setattr(
        "stocks.market.screener_profile.screener_url",
        lambda _t, _m=None: "https://www.screener.in/company/544531/",
    )
    monkeypatch.setattr(
        "stocks.market.screener_profile.requests.get",
        lambda *args, **kwargs: _Resp(),
    )
    monkeypatch.setattr("stocks.market.screener_profile._throttle", lambda: None)

    profile = fetch_screener_profile("TRUECOLORS", "BSE")
    assert profile.get("current_price") == 162.0
    assert fetch_screener_current_price("TRUECOLORS", "BSE") == 162.0
