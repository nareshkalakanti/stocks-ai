"""Fund watchlists — Negen / Niveshaay (separate from personal Holdings)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from stocks.core.database import (
    load_all_superstar_holdings_df,
    load_fund_watchlist,
    replace_fund_watchlist,
)
from stocks.core.text_utils import safe_str

# list_key → display + SuperStars investor name(s) that seed the list
FUND_WATCHLIST_DEFS: dict[str, dict[str, Any]] = {
    "negen": {
        "label": "Negen",
        "investor_names": ["Negen Capital / Negen Undiscovered Value Fund"],
    },
    "niveshaay": {
        "label": "Niveshaay",
        "investor_names": ["Niveshaay"],
    },
}

NEGEN_PLAYLIST_LABEL = "Negen"
NIVESHAAY_PLAYLIST_LABEL = "Niveshaay"
FUND_WATCHLIST_PLAYLIST_LABELS = (NEGEN_PLAYLIST_LABEL, NIVESHAAY_PLAYLIST_LABEL)

_LABEL_TO_KEY = {
    NEGEN_PLAYLIST_LABEL: "negen",
    NIVESHAAY_PLAYLIST_LABEL: "niveshaay",
}


def fund_watchlist_keys() -> list[str]:
    return list(FUND_WATCHLIST_DEFS.keys())


def fund_watchlist_label(list_key: str) -> str:
    return safe_str((FUND_WATCHLIST_DEFS.get(list_key) or {}).get("label")) or list_key


def list_key_for_playlist(market: str) -> str | None:
    return _LABEL_TO_KEY.get(safe_str(market))


def is_fund_watchlist_playlist(market: str) -> bool:
    return safe_str(market) in FUND_WATCHLIST_PLAYLIST_LABELS


def load_fund_watchlist_df(list_key: str) -> pd.DataFrame:
    return load_fund_watchlist(list_key)


def fund_watchlist_tickers(list_key: str) -> set[str]:
    df = load_fund_watchlist_df(list_key)
    if df.empty:
        return set()
    return {safe_str(t).upper() for t in df["ticker"] if safe_str(t)}


def fund_watchlist_count(list_key: str) -> int:
    return len(fund_watchlist_tickers(list_key))


def sync_fund_watchlist_from_superstars(list_key: str) -> int:
    """
    Replace watchlist tickers from SuperStars ``superstar_holdings`` for linked investors.
    Returns number of tickers written.
    """
    meta = FUND_WATCHLIST_DEFS.get(list_key)
    if not meta:
        return 0
    names = [safe_str(n) for n in (meta.get("investor_names") or []) if safe_str(n)]
    if not names:
        return 0

    raw = load_all_superstar_holdings_df()
    if raw.empty or "investor" not in raw.columns:
        replace_fund_watchlist(list_key, pd.DataFrame())
        return 0

    inv = raw["investor"].astype(str)
    chunk = raw[inv.isin(names)].copy()
    if chunk.empty:
        replace_fund_watchlist(list_key, pd.DataFrame())
        return 0

    rows: list[dict] = []
    seen: set[str] = set()
    # Prefer higher holding value when same ticker appears under multiple fund entities.
    chunk = chunk.sort_values("holding_value_cr", ascending=False, na_position="last")
    for _, row in chunk.iterrows():
        ticker = safe_str(row.get("symbol")).upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        rows.append(
            {
                "ticker": ticker,
                "market": safe_str(row.get("exchange")).upper() or "NSE",
                "name": safe_str(row.get("company_name")),
                "holding_entity": safe_str(row.get("holding_entity")),
                "holding_value_cr": row.get("holding_value_cr"),
                "source_investor": safe_str(row.get("investor")),
            }
        )
    out = pd.DataFrame(rows)
    return replace_fund_watchlist(list_key, out)


def sync_all_fund_watchlists() -> dict[str, int]:
    return {key: sync_fund_watchlist_from_superstars(key) for key in FUND_WATCHLIST_DEFS}


def fund_watchlist_playlist_listings(
    stocks: pd.DataFrame,
    market: str,
    *,
    sector: str | list[str] = "All",
    search: str = "",
    industry: str | list[str] = "All",
    sub_sector: str | list[str] = "All",
) -> pd.DataFrame:
    list_key = list_key_for_playlist(market)
    if not list_key:
        return stocks.iloc[0:0].copy()
    watch = load_fund_watchlist_df(list_key)
    if watch.empty:
        return stocks.iloc[0:0].copy()

    tickers = fund_watchlist_tickers(list_key)
    matched = stocks[stocks["ticker"].astype(str).str.upper().isin(tickers)].copy()
    matched_tickers = set(matched["ticker"].astype(str).str.upper()) if not matched.empty else set()
    missing = tickers - matched_tickers
    if missing:
        lookup = watch.set_index(watch["ticker"].astype(str).str.upper())
        extra: list[dict] = []
        for ticker in sorted(missing):
            if ticker not in lookup.index:
                continue
            row = lookup.loc[ticker]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            extra.append(
                {
                    "ticker": ticker,
                    "market": safe_str(row.get("market")).upper() or "NSE",
                    "name": safe_str(row.get("name")) or "",
                    "sector": "",
                }
            )
        if extra:
            matched = pd.concat([matched, pd.DataFrame(extra)], ignore_index=True)

    matched = matched.drop_duplicates("ticker", keep="first")
    from stocks.listings.stocks_data import apply_classifier_filters, normalize_sectors

    sectors = normalize_sectors(sector)
    if sectors is not None and "sector" in matched.columns:
        matched = matched[matched["sector"].isin(sectors)]
    matched = apply_classifier_filters(matched, industry=industry, sub_sector=sub_sector)
    if search.strip():
        query = search.strip().lower()
        matched = matched[
            matched["ticker"].astype(str).str.lower().str.contains(query, na=False)
            | matched["name"].astype(str).str.lower().str.contains(query, na=False)
        ]
    return matched.reset_index(drop=True)


__all__ = [
    "FUND_WATCHLIST_DEFS",
    "FUND_WATCHLIST_PLAYLIST_LABELS",
    "NEGEN_PLAYLIST_LABEL",
    "NIVESHAAY_PLAYLIST_LABEL",
    "fund_watchlist_count",
    "fund_watchlist_keys",
    "fund_watchlist_label",
    "fund_watchlist_playlist_listings",
    "fund_watchlist_tickers",
    "is_fund_watchlist_playlist",
    "list_key_for_playlist",
    "load_fund_watchlist_df",
    "sync_all_fund_watchlists",
    "sync_fund_watchlist_from_superstars",
]
