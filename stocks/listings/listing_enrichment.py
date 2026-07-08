"""Resolve missing NSE listings via aliases and yfinance."""

from __future__ import annotations

import pandas as pd
import yfinance as yf

from stocks.core.database import load_stocks_from_db, save_stocks_to_db
from stocks.market.price_service import to_yfinance_symbol
from stocks.core.text_utils import safe_str
from stocks.market.yfinance_limits import call_fast

# TradingView / legacy symbols → dataset tickers.
TICKER_ALIASES: dict[str, str] = {
    "TUBEINVEST": "TIINDIA",
    "SHRAMASSET": "SRAMSET",
    "FASTANI": "AASTAFIN",
    "SHEL": "STEL",
    "TMPM": "TATAMOTORS",
    "MMFIN": "M&MFIN",
    "RUCHIINFRA": "RUCHINFRA",
    "DUNCANSZN": "DUNCANENG",
    "JUBLAGRI": "JUBLCPL",
    "KHAITAN": "KHAITANLTD",
    "MAHSEAMLESS": "MAHSEAMLES",
    "JINDALPHOTO": "JINDALPHOT",
    "FORBESGOK": "FORBESCO",
    "UNIVERSUS": "UNIVPHOTO",
    "RAMCOSYST": "RAMCOSYS",
    "ASI": "AGI",
    "KAMAHLD": "KAMAHOLD",
    "RPGLVENT": "RPSGVENT",
    "SWAJENG": "SWARAJENG",
    "KPENERGY": "KPEL",
    "KPENERGYLTD": "KPEL",
    "KPENERG": "KPEL",
    "KPIT": "KPITTECH",
}

# Manual rows when yfinance has no quote (BSE-only / illiquid).
_MANUAL_LISTINGS: dict[str, dict[str, str]] = {
    "SILPO": {
        "name": "SILPO Limited",
        "sector": "",
        "market": "NSE",
    },
    "ASAHIIND": {
        "name": "Asahi Industries Limited",
        "sector": "",
        "market": "BSE",
    },
    "EPACKPEB": {
        "name": "Epack Prefab Technologies Limited",
        "sector": "Industrials",
        "market": "NSE",
    },
    "IBULLSLTD": {
        "name": "Indiabulls Limited",
        "sector": "",
        "market": "BSE",
    },
}

# Back-compat alias
_MANUAL_NSE = _MANUAL_LISTINGS


def resolve_ticker_alias(ticker: str) -> str:
    key = safe_str(ticker).upper()
    return TICKER_ALIASES.get(key, key)


def _listing_row(ticker: str, name: str, *, sector: str = "", market: str = "NSE") -> dict[str, str]:
    return {
        "ticker": safe_str(ticker).upper(),
        "name": safe_str(name),
        "market": market,
        "sector": safe_str(sector),
    }


def fetch_listing_from_yfinance(ticker: str, *, market: str = "NSE") -> dict[str, str] | None:
    """Return a stocks-universe row when yfinance has a live quote."""
    symbol = to_yfinance_symbol(ticker, market)
    try:
        yt = yf.Ticker(symbol)
        info = call_fast(lambda: yt.info or {}) or {}
        name = safe_str(info.get("longName") or info.get("shortName"))
        hist = call_fast(lambda: yt.history(period="5d"))
        if (hist is None or hist.empty) and not name:
            return None
        sector = safe_str(info.get("sector"))
        return _listing_row(ticker, name or ticker, sector=sector, market=market)
    except Exception:
        return None


def _resolve_rows(tickers: list[str]) -> tuple[list[dict[str, str]], list[str]]:
    rows: list[dict[str, str]] = []
    missing: list[str] = []
    seen: set[str] = set()
    for raw in tickers:
        ticker = resolve_ticker_alias(raw)
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        if ticker in _MANUAL_LISTINGS:
            manual = _MANUAL_LISTINGS[ticker]
            rows.append(
                _listing_row(
                    ticker,
                    manual["name"],
                    sector=manual.get("sector", ""),
                    market=manual.get("market", "NSE"),
                )
            )
            continue
        row = fetch_listing_from_yfinance(ticker)
        if not row:
            row = fetch_listing_from_yfinance(ticker, market="BSE")
        if row:
            rows.append(row)
        else:
            missing.append(ticker)
    return rows, missing


def ensure_tickers_in_universe(
    stocks: pd.DataFrame,
    tickers: list[str],
    *,
    persist: bool = True,
) -> tuple[pd.DataFrame, list[str]]:
    """Add missing tickers to the universe using aliases, manual rows, and yfinance."""
    if stocks.empty:
        stocks = pd.DataFrame(columns=["ticker", "name", "market", "sector"])

    existing = set(stocks["ticker"].astype(str).str.upper())
    want = [resolve_ticker_alias(t) for t in tickers if safe_str(t)]
    need = [t for t in dict.fromkeys(want) if t not in existing]
    if not need:
        return stocks, []

    rows, still_missing = _resolve_rows(need)
    if not rows:
        return stocks, still_missing

    out = pd.concat([stocks, pd.DataFrame(rows)], ignore_index=True)
    out = out.drop_duplicates(subset=["ticker"], keep="first")
    if persist:
        save_stocks_to_db(out)
    return out, still_missing


def enrich_stocks_cache(tickers: list[str]) -> pd.DataFrame:
    """Load cached stocks, ensure tickers exist, return updated frame."""
    cached = load_stocks_from_db()
    if cached.empty:
        from stocks.listings.stocks_data import load_india_stocks

        cached = load_india_stocks()
    updated, _ = ensure_tickers_in_universe(cached, tickers)
    return updated
