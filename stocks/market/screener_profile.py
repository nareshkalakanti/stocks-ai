"""Company profile fallback from screener.in when yfinance omits website/about."""

from __future__ import annotations

import re
import threading
import time
from html import unescape

import requests

from stocks.core.config import SCREENER_REQUEST_DELAY
from stocks.core.text_utils import safe_str, sanitize_website
from stocks.shared.links import screener_url

_USER_AGENT = (
    "Mozilla/5.0 (compatible; stocks-ai/1.0; +https://github.com/)"
)
_LOCK = threading.Lock()
_LAST_REQUEST_AT = 0.0


def _throttle() -> None:
    """Serialize and pace screener requests."""
    global _LAST_REQUEST_AT
    delay = max(0.0, float(SCREENER_REQUEST_DELAY))
    with _LOCK:
        now = time.monotonic()
        wait = delay - (now - _LAST_REQUEST_AT)
        if wait > 0:
            time.sleep(wait)
        _LAST_REQUEST_AT = time.monotonic()


def _strip_html(text: str) -> str:
    cleaned = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    cleaned = re.sub(r"<style[\s\S]*?</style>", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _normalize_website(url: str | None) -> str | None:
    return sanitize_website(url)


def fetch_screener_profile(ticker: str, market: str | None = None) -> dict:
    """Best-effort website, about, and market cap (₹ Cr) from screener.in."""
    url = screener_url(ticker, market)
    if not url or url.rstrip("/").endswith("screener.in"):
        return {}
    _throttle()
    try:
        resp = requests.get(
            url,
            timeout=15,
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

    # Screener peer bar: Broad Sector / Sector / Industry links.
    broad = re.search(
        r'title="Broad Sector">\s*([^<]+?)\s*</a>',
        html,
        flags=re.I,
    )
    sector_a = re.search(
        r'title="Sector">\s*([^<]+?)\s*</a>',
        html,
        flags=re.I,
    )
    industry_a = re.search(
        r'title="Industry">\s*([^<]+?)\s*</a>',
        html,
        flags=re.I,
    )
    sector = safe_str(broad.group(1) if broad else None) or safe_str(
        sector_a.group(1) if sector_a else None
    )
    industry = safe_str(industry_a.group(1) if industry_a else None) or safe_str(
        sector_a.group(1) if sector_a else None
    )
    if sector:
        out["company_sector"] = unescape(sector).strip()
    if industry:
        out["company_industry"] = unescape(industry).strip()

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


def _yahoo_market_cap_cr(ticker: str, market: str | None) -> float | None:
    import yfinance as yf

    from stocks.market.price_service import to_yfinance_symbol
    from stocks.market.yfinance_limits import call_fast

    ticker_key = safe_str(ticker).upper()
    if not ticker_key:
        return None
    symbol = to_yfinance_symbol(ticker_key, market)

    def _load() -> float | None:
        info = yf.Ticker(symbol).info or {}
        raw = info.get("marketCap")
        if raw is None:
            return None
        val = float(raw)
        if val <= 0:
            return None
        return round(val / 1e7, 1)

    try:
        return call_fast(_load)
    except Exception:
        return None


def fetch_market_cap_cr(ticker: str, market: str | None = None) -> float | None:
    """Market cap in ₹ Cr — screener.in, then Yahoo finance."""
    mcap = fetch_screener_market_cap_cr(ticker, market)
    if mcap is not None and mcap > 0:
        return mcap
    return _yahoo_market_cap_cr(ticker, market)
