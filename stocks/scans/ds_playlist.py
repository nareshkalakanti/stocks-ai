"""D&S — unified demerger + spin-off scan playlist."""

from __future__ import annotations

import pandas as pd

from stocks.core.text_utils import safe_str

DS_PLAYLIST_LABEL = "D&S"


def _load_stocks() -> pd.DataFrame:
    from stocks.shared.demerger_stocks import load_demerger_stocks

    return load_demerger_stocks()


def is_ds_playlist(market: str) -> bool:
    return safe_str(market) == DS_PLAYLIST_LABEL


def ds_playlist_tickers() -> set[str]:
    stocks = _load_stocks()
    if stocks.empty:
        return set()
    return {safe_str(t).upper() for t in stocks["ticker"] if safe_str(t)}


def ds_playlist_count() -> int:
    return len(ds_playlist_tickers())


def ds_playlist_listings(
    stocks: pd.DataFrame,
    *,
    sector: str | list[str] = "All",
    search: str = "",
    industry: str | list[str] = "All",
    sub_sector: str | list[str] = "All",
) -> pd.DataFrame:
    """All parent + spin-off tickers from the saved D&S watchlist."""
    watchlist = _load_stocks()
    if watchlist.empty:
        return stocks.iloc[0:0].copy()

    tickers = ds_playlist_tickers()
    if not tickers:
        return stocks.iloc[0:0].copy()

    matched = stocks[stocks["ticker"].astype(str).str.upper().isin(tickers)].copy()
    matched_tickers = set(matched["ticker"].astype(str).str.upper())
    missing = tickers - matched_tickers
    if missing:
        lookup = watchlist.set_index(watchlist["ticker"].astype(str).str.upper())
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
                    "sector": safe_str(row.get("sector")) or "",
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
