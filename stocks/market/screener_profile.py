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


def fetch_screener_profile(ticker: str, market: str | None = None) -> dict[str, str]:
    """Best-effort website + about text from a screener.in company page."""
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

    out: dict[str, str] = {}

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

    return out
