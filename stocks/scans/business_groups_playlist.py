"""Business Groups — scan universe from saved corporate groups."""

from __future__ import annotations

import pandas as pd

from stocks.core.database import load_all_business_group_members
from stocks.core.text_utils import safe_str

BUSINESS_GROUPS_PLAYLIST_LABEL = "Business Groups"


def _load_members() -> pd.DataFrame:
    return load_all_business_group_members()


def is_business_groups_playlist(market: str) -> bool:
    return safe_str(market) == BUSINESS_GROUPS_PLAYLIST_LABEL


def business_groups_playlist_tickers() -> set[str]:
    members = _load_members()
    if members.empty:
        return set()
    return {safe_str(t).upper() for t in members["ticker"] if safe_str(t)}


def business_groups_playlist_count() -> int:
    return len(business_groups_playlist_tickers())


def business_groups_playlist_listings(
    stocks: pd.DataFrame,
    *,
    sector: str | list[str] = "All",
    search: str = "",
    industry: str | list[str] = "All",
    sub_sector: str | list[str] = "All",
) -> pd.DataFrame:
    """Listings for saved business groups, merged with India dataset metadata."""
    members = _load_members()
    if members.empty:
        return stocks.iloc[0:0].copy()

    tickers = business_groups_playlist_tickers()
    if not tickers:
        return stocks.iloc[0:0].copy()

    matched = stocks[stocks["ticker"].astype(str).str.upper().isin(tickers)].copy()
    matched_tickers = set(matched["ticker"].astype(str).str.upper())
    missing = tickers - matched_tickers
    if missing:
        lookup = members.set_index(members["ticker"].astype(str).str.upper())
        extra_rows: list[dict] = []
        for ticker in sorted(missing):
            row = lookup.loc[ticker] if ticker in lookup.index else None
            if row is None:
                continue
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            extra_rows.append(
                {
                    "ticker": ticker,
                    "market": safe_str(row.get("market")).upper() or "NSE",
                    "name": safe_str(row.get("name")) or "",
                    "sector": "",
                }
            )
        if extra_rows:
            matched = pd.concat([matched, pd.DataFrame(extra_rows)], ignore_index=True)

    matched = matched.drop_duplicates("ticker", keep="first")
    from stocks.listings.stocks_data import apply_classifier_filters, normalize_sectors

    sectors = normalize_sectors(sector)
    if sectors is not None:
        matched = matched[matched["sector"].isin(sectors)]
    matched = apply_classifier_filters(matched, industry=industry, sub_sector=sub_sector)
    if search.strip():
        query = search.strip().lower()
        matched = matched[
            matched["ticker"].str.lower().str.contains(query, na=False)
            | matched["name"].str.lower().str.contains(query, na=False)
        ]
    return matched.reset_index(drop=True)
