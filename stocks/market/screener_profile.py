"""Company profile fallback from screener.in when yfinance omits website/about."""

from __future__ import annotations

import re
from html import unescape

import requests

from stocks.core.text_utils import safe_str
from stocks.shared.links import screener_url

_USER_AGENT = (
    "Mozilla/5.0 (compatible; stocks-ai/1.0; +https://github.com/)"
)


def _strip_html(text: str) -> str:
    cleaned = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    cleaned = re.sub(r"<style[\s\S]*?</style>", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _normalize_website(url: str | None) -> str | None:
    site = safe_str(url).strip()
    if not site:
        return None
    if site.startswith(("http://", "https://")):
        return site
    return f"https://{site}"


def fetch_screener_profile(ticker: str, market: str | None = None) -> dict:
    """Best-effort website, about, and market cap (₹ Cr) from screener.in."""
    url = screener_url(ticker, market)
    if not url or url.rstrip("/").endswith("screener.in"):
        return {}
    try:
        resp = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": _USER_AGENT},
        )
        resp.raise_for_status()
        html = resp.text
    except Exception:
        return {}

    out: dict = {}

    web_match = re.search(
        r'class="company-links[^"]*"[\s\S]*?<a\s+href="(https?://[^"]+)"',
        html,
        flags=re.I,
    )
    if web_match:
        website = _normalize_website(web_match.group(1))
        if website and "screener.in" not in website:
            out["website"] = website

    about_match = re.search(
        r'<div class="sub show-more-box about"[^>]*>([\s\S]*?)</div>',
        html,
        flags=re.I,
    )
    if about_match:
        about = _strip_html(about_match.group(1))
        about = re.sub(r"\s*\[\d+\]\s*$", "", about).strip()
        if about:
            out["long_description"] = about

    # e.g. Market Cap … ₹ <span class="number">392</span> Cr.
    mcap_match = re.search(
        r"Market\s*Cap[\s\S]{0,240}?₹\s*<span class=\"number\">\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*</span>\s*Cr",
        html,
        flags=re.I,
    )
    if not mcap_match:
        mcap_match = re.search(
            r"Market\s*Cap[\s\S]{0,120}?₹\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*Cr",
            html,
            flags=re.I,
        )
    if mcap_match:
        try:
            out["market_cap_cr"] = round(float(mcap_match.group(1).replace(",", "")), 1)
        except ValueError:
            pass

    return out


def fetch_screener_market_cap_cr(ticker: str, market: str | None = None) -> float | None:
    """Market cap in ₹ Cr from screener.in, or None."""
    raw = fetch_screener_profile(ticker, market).get("market_cap_cr")
    try:
        if raw is None:
            return None
        val = float(raw)
    except (TypeError, ValueError):
        return None
    return val if val > 0 else None
