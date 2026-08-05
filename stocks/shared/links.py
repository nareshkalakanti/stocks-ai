"""Screener / TradingView link helpers for NSE and BSE symbols."""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote

import pandas as pd

from stocks.core.text_utils import safe_str

TV_CHART_BASE = "https://www.tradingview.com/chart/"
_NSE_MARKETS = frozenset({"NSE", "NSE SME", "NATIONAL STOCK EXCHANGE"})


def _clean_bse_code(bse_code: str | None) -> str:
    bse = safe_str(bse_code)
    if bse.endswith(".0"):
        bse = bse[:-2]
    return bse


@lru_cache(maxsize=1)
def nse_listed_symbols() -> frozenset[str]:
    from stocks.listings.stocks_data import load_india_stocks

    stocks = load_india_stocks()
    if stocks.empty or "market" not in stocks.columns:
        return frozenset()
    mk = stocks["market"].astype(str).str.upper()
    nse = stocks.loc[mk.isin(_NSE_MARKETS), "ticker"]
    return frozenset(safe_str(t).upper() for t in nse if safe_str(t))


@lru_cache(maxsize=1)
def bse_code_by_ticker() -> dict[str, str]:
    """Map BSE text ticker → numeric scrip code (for screener.in / Yahoo)."""
    from stocks.core.database import load_bse_code_map_from_db

    try:
        return load_bse_code_map_from_db()
    except Exception:
        return {}


@lru_cache(maxsize=1)
def bse_ticker_by_code() -> dict[str, str]:
    """Map BSE numeric scrip code → text ticker (for TradingView BSE:SYMBOL)."""
    return {code: ticker for ticker, code in bse_code_by_ticker().items()}


def _prefer_bse(ticker: str, market: str | None) -> bool:
    sym = safe_str(ticker).upper()
    market_key = safe_str(market).upper()
    if market_key in {"BSE", "BOMBAY STOCK EXCHANGE"}:
        return True
    if market_key in _NSE_MARKETS:
        return False
    if sym.isdigit():
        return True
    if sym and sym not in nse_listed_symbols():
        return True
    return False


@lru_cache(maxsize=1)
def ticker_market_lookup() -> dict[str, str]:
    from stocks.listings.stocks_data import load_india_stocks

    stocks = load_india_stocks()
    if stocks.empty or "market" not in stocks.columns:
        return {}
    out: dict[str, str] = {}
    for ticker, market in zip(stocks["ticker"], stocks["market"], strict=False):
        sym = safe_str(ticker).upper()
        mk = safe_str(market).upper()
        if sym and mk and sym not in out:
            out[sym] = mk
    return out


def resolve_listing_market(ticker: str, market: str | None) -> str | None:
    """Prefer explicit market; fall back to India listings when missing."""
    mk = safe_str(market).upper()
    if mk in _NSE_MARKETS or mk in {"BSE", "BOMBAY STOCK EXCHANGE"}:
        return mk
    sym = safe_str(ticker).upper()
    if sym:
        found = ticker_market_lookup().get(sym)
        if found:
            return found
    return mk or None


def research_links(
    ticker: str,
    market: str | None = None,
    *,
    bse_code: str | None = None,
) -> tuple[str, str]:
    """Fresh screener + TradingView URLs from ticker and resolved listing market."""
    resolved = resolve_listing_market(ticker, market)
    return (
        screener_url(ticker, resolved, bse_code=bse_code),
        tradingview_url(ticker, resolved, bse_code=bse_code),
    )


def tradingview_chart_symbol(
    ticker: str,
    market: str | None = None,
    *,
    bse_code: str | None = None,
    prefer_bse: bool = False,
) -> str:
    """
    TradingView chart symbol (e.g. NSE:RELIANCE, BSE:RAP).

    BSE-only names must use BSE: — NSE: links 404 on TradingView.
    Numeric BSE codes resolve to text tickers when possible.
    """
    sym = safe_str(ticker).upper()
    bse = _clean_bse_code(bse_code) or bse_code_by_ticker().get(sym, "")

    use_bse = prefer_bse or _prefer_bse(sym, market)
    if use_bse:
        if sym and not sym.isdigit():
            return f"BSE:{sym}"
        ticker_text = bse_ticker_by_code().get(bse) or bse_ticker_by_code().get(sym)
        if ticker_text:
            return f"BSE:{ticker_text}"
        if bse:
            return f"BSE:{bse}"
        if sym:
            return f"BSE:{sym}"
        return ""

    return f"NSE:{sym}" if sym else ""


def tradingview_url(
    ticker: str,
    market: str | None = None,
    *,
    bse_code: str | None = None,
    prefer_bse: bool = False,
) -> str:
    sym = tradingview_chart_symbol(
        ticker,
        market,
        bse_code=bse_code,
        prefer_bse=prefer_bse,
    )
    if not sym:
        return TV_CHART_BASE
    return f"{TV_CHART_BASE}?symbol={quote(sym, safe=':')}"


def screener_url(
    ticker: str,
    market: str | None = None,
    *,
    bse_code: str | None = None,
) -> str:
    """Screener.in company page — numeric BSE code when the ticker is BSE-only."""
    sym = safe_str(ticker).upper()
    bse = _clean_bse_code(bse_code) or bse_code_by_ticker().get(sym, "")
    slug = bse if _prefer_bse(sym, market) and bse.isdigit() else sym
    if not slug:
        return "https://www.screener.in/"
    if slug.isdigit():
        return f"https://www.screener.in/company/{slug}/"
    return f"https://www.screener.in/company/{slug}/"


def screener_people_url(people_id: str, slug: str = "") -> str:
    """Screener.in shareholder / fund people page."""
    pid = safe_str(people_id)
    if not pid:
        return "https://www.screener.in/"
    slug_part = safe_str(slug).strip("/")
    if slug_part:
        return f"https://www.screener.in/people/{pid}/{slug_part}/"
    return f"https://www.screener.in/people/{pid}/"


def _listing_markets(df: pd.DataFrame) -> list[str | None]:
    if "market" in df.columns:
        return df["market"].tolist()
    if "market_x" in df.columns:
        return df["market_x"].tolist()
    if "market_y" in df.columns:
        return df["market_y"].tolist()
    return [None] * len(df)


def _listing_bse_codes(df: pd.DataFrame) -> list[str | None]:
    if "bse_code" in df.columns:
        return df["bse_code"].tolist()
    lookup = bse_code_by_ticker()
    return [lookup.get(safe_str(t).upper()) for t in df["ticker"]]


def attach_research_links(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "ticker" not in df.columns:
        return df

    result = df.copy()
    markets = _listing_markets(result)
    bse_codes = _listing_bse_codes(result)

    result["tv_link"] = [
        tradingview_url(ticker, resolve_listing_market(ticker, market), bse_code=bse_code)
        for ticker, market, bse_code in zip(result["ticker"], markets, bse_codes, strict=False)
    ]
    result["screener_link"] = [
        screener_url(ticker, resolve_listing_market(ticker, market), bse_code=bse_code)
        for ticker, market, bse_code in zip(result["ticker"], markets, bse_codes, strict=False)
    ]
    return result
