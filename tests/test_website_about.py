"""Tests for corporate website About Us scraper (offline fixtures)."""

from __future__ import annotations

from stocks.market.website_about import (
    discover_about_urls,
    extract_end_markets,
    extract_page_text,
    extract_products_text,
    extract_theme_tags,
    normalize_website_url,
    pick_ir_url,
    scrape_website_about,
    validate_about_text,
)

_HOME_HTML = """
<html><head><title>Acme Metals</title></head>
<body>
  <nav><a href="/">Home</a><a href="/about-us">About Us</a><a href="/contact">Contact</a></nav>
  <main>
    <p>Welcome to Acme. Cookie settings and privacy policy links live in the footer.</p>
  </main>
  <footer>All rights reserved.</footer>
</body></html>
"""

_ABOUT_HTML = """
<html><body>
<header>Menu</header>
<main class="about">
  <h1>About Us</h1>
  <p>Acme Metals Limited manufactures and supplies copper and aluminium products for
  industrial customers across India. The company operates processing facilities and
  develops specialty alloys for electrical and automotive segments.</p>
  <p>Our business engages with distributors and provides engineered solutions for
  OEMs. We specialize in high-conductivity copper rods and aluminium extrusions.</p>
</main>
<footer>Privacy Policy</footer>
</body></html>
"""

_COOKIE_HTML = """
<html><body>
<p>Please enable cookies and accept our privacy policy to continue. Sign in required.</p>
</body></html>
"""


def test_normalize_website_url():
    assert normalize_website_url("www.example.com") == "https://www.example.com/"
    assert normalize_website_url("https://example.com/about") == "https://example.com/about"
    assert normalize_website_url("http://www.google.co.in/search?q=foo") is None


def test_validate_about_accepts_business_prose():
    text = extract_page_text(_ABOUT_HTML)
    v = validate_about_text(text)
    assert v.ok, v.reasons
    assert v.business_hits >= 3
    assert "manufactures" in text.lower() or "supplies" in text.lower()


def test_validate_about_rejects_cookie_gate():
    v = validate_about_text(
        "Please enable cookies and accept our privacy policy to continue. Sign in required."
    )
    assert not v.ok
    assert "boilerplate_or_gate" in v.reasons


def test_discover_about_urls_ranks_about_link():
    urls = discover_about_urls("https://acme.example/", _HOME_HTML)
    assert urls
    assert any("about" in u.lower() for u, _ in urls)


def test_scrape_website_about_uses_about_page(monkeypatch):
    pages = {
        "https://acme.example/": _HOME_HTML,
        "https://acme.example/about-us": _ABOUT_HTML,
    }

    def _fake_fetch(url: str):
        html = pages.get(url) or pages.get(url.rstrip("/"))
        if not html:
            return None, "missing"
        return html, None

    monkeypatch.setattr("stocks.market.website_about._fetch_html", _fake_fetch)
    monkeypatch.setattr("stocks.market.website_about._throttle", lambda: None)

    result = scrape_website_about("https://acme.example/")
    assert result.ok, result.error
    assert "about" in result.source_url
    assert "copper" in result.text.lower() or "aluminium" in result.text.lower()
    assert result.validation and result.validation.ok


def test_scrape_website_about_fails_cookie_only(monkeypatch):
    monkeypatch.setattr(
        "stocks.market.website_about._fetch_html",
        lambda url: (_COOKIE_HTML, None),
    )
    monkeypatch.setattr("stocks.market.website_about._throttle", lambda: None)
    result = scrape_website_about("https://blocked.example/")
    assert not result.ok
    assert result.text == ""


def test_theme_and_end_markets_from_copy():
    text = (
        "We manufacture copper rods and aluminium extrusions for automotive OEMs "
        "and defence aerospace programmes. CDMO and API formulation capacity."
    )
    tags = extract_theme_tags(text)
    assert "copper" in tags
    assert "aluminium" in tags
    assert "cdmo" in tags or "api" in tags
    markets = extract_end_markets(text)
    assert "Automotive" in markets
    assert "Aerospace & Defence" in markets or "Defence" in markets or "Aerospace" in markets


def test_products_and_ir_discovery():
    home = """
    <html><body>
      <a href="/products">Products</a>
      <a href="/investors">Investor Relations</a>
      <a href="/about-us">About Us</a>
    </body></html>
    """
    products_html = """
    <html><body><main>
      <h2>Copper rods</h2><p>We produce high-conductivity copper rods for electrical markets.</p>
      <h2>Aluminium extrusions</h2><li>Automotive and construction extrusions</li>
    </main></body></html>
    """
    assert pick_ir_url("https://acme.example/", home).endswith("/investors")
    prod = extract_products_text(products_html)
    assert "copper" in prod.lower()
    assert discover_about_urls("https://acme.example/", home)
