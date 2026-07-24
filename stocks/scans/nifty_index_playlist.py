"""Nifty index playlists — scan universes from NSE constituent lists."""

from __future__ import annotations

import pandas as pd

from stocks.core.text_utils import safe_str
from stocks.market.nse_index_constituents import (
    LABEL_TO_INDEX_ID,
    NIFTY_INDEXES,
    ensure_index_constituents,
    index_tickers,
    load_index_constituents,
)

NIFTY_PLAYLIST_LABELS = tuple(meta["label"] for meta in NIFTY_INDEXES.values())


def is_nifty_index_playlist(market: str) -> bool:
    return safe_str(market) in LABEL_TO_INDEX_ID


def nifty_index_id_for_label(market: str) -> str | None:
    return LABEL_TO_INDEX_ID.get(safe_str(market))


def nifty_playlist_tickers(market: str, *, seed_if_empty: bool = True) -> set[str]:
    index_id = nifty_index_id_for_label(market)
    if not index_id:
        return set()
    return index_tickers(index_id, seed_if_empty=seed_if_empty)


def nifty_playlist_count(market: str, *, seed_if_empty: bool = True) -> int:
    return len(nifty_playlist_tickers(market, seed_if_empty=seed_if_empty))


def nifty_playlist_listings(
    stocks: pd.DataFrame,
    market: str,
    *,
    sector: str | list[str] = "All",
    search: str = "",
    industry: str | list[str] = "All",
    sub_sector: str | list[str] = "All",
) -> pd.DataFrame:
    """Listings for a Nifty index, merged with India dataset sector/sub-sector."""
    index_id = nifty_index_id_for_label(market)
    if not index_id:
        return stocks.iloc[0:0].copy()

    constituents = load_index_constituents(index_id)
    if constituents.empty:
        ensure_index_constituents(index_id, force=False)
        constituents = load_index_constituents(index_id)
    if constituents.empty:
        return stocks.iloc[0:0].copy()

    tickers = {safe_str(t).upper() for t in constituents["ticker"].tolist() if safe_str(t)}
    matched = stocks[stocks["ticker"].astype(str).str.upper().isin(tickers)].copy()
    matched_tickers = set(matched["ticker"].astype(str).str.upper())
    missing = tickers - matched_tickers

    if missing:
        lookup = constituents.set_index(constituents["ticker"].astype(str).str.upper())
        extra_rows: list[dict] = []
        for ticker in sorted(missing):
            row = lookup.loc[ticker] if ticker in lookup.index else None
            if row is None:
                continue
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            nse_industry = safe_str(row.get("industry"))
            extra_rows.append(
                {
                    "ticker": ticker,
                    "market": "NSE",
                    "name": safe_str(row.get("name")) or ticker,
                    # NSE "Industry" is the best available sector signal in the CSV.
                    "sector": nse_industry,
                    "industry": nse_industry,
                    "sub_sector": "",
                }
            )
        if extra_rows:
            matched = pd.concat([matched, pd.DataFrame(extra_rows)], ignore_index=True)

    # Fill blank sector from NSE industry when stocks row has no classification.
    if not matched.empty and "sector" in matched.columns:
        ind_map = {
            safe_str(r["ticker"]).upper(): safe_str(r.get("industry"))
            for _, r in constituents.iterrows()
        }
        def _fill_sector(row: pd.Series) -> str:
            current = safe_str(row.get("sector"))
            if current:
                return current
            return ind_map.get(safe_str(row.get("ticker")).upper(), "") or current

        matched["sector"] = matched.apply(_fill_sector, axis=1)

    matched = matched.drop_duplicates("ticker", keep="first")
    from stocks.listings.stocks_data import apply_classifier_filters, normalize_sectors

    sectors = normalize_sectors(sector)
    if sectors is not None and "sector" in matched.columns:
        matched = matched[matched["sector"].isin(sectors)]
    matched = apply_classifier_filters(matched, industry=industry, sub_sector=sub_sector)
    if search.strip():
        query = search.strip().lower()
        matched = matched[
            matched["ticker"].str.lower().str.contains(query, na=False)
            | matched["name"].str.lower().str.contains(query, na=False)
        ]
    return matched.reset_index(drop=True)
