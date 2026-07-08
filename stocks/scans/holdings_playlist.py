"""Holdings — scan universe from SQLite portfolio."""

from __future__ import annotations

import pandas as pd

from stocks.core.text_utils import safe_str

HOLDINGS_PLAYLIST_LABEL = "Holdings"


def _load_holdings(*, seed_if_empty: bool = True) -> pd.DataFrame:
    from stocks.shared.portfolio import load_holdings

    return load_holdings(seed_if_empty=seed_if_empty)


def is_holdings_playlist(market: str) -> bool:
    return safe_str(market) == HOLDINGS_PLAYLIST_LABEL


def holdings_playlist_tickers(*, seed_if_empty: bool = True) -> set[str]:
    holdings = _load_holdings(seed_if_empty=seed_if_empty)
    if holdings.empty:
        return set()
    return {safe_str(t).upper() for t in holdings["ticker"] if safe_str(t)}


def holdings_playlist_count(*, seed_if_empty: bool = True) -> int:
    return len(holdings_playlist_tickers(seed_if_empty=seed_if_empty))


def holdings_industry_labels(*, seed_if_empty: bool = True) -> list[str]:
    """Distinct industry labels from the Holdings portfolio."""
    from stocks.shared.portfolio import (
        _fill_holdings_classification,
        load_holdings,
    )

    holdings = _fill_holdings_classification(load_holdings(seed_if_empty=seed_if_empty))
    if holdings.empty or "industry" not in holdings.columns:
        return []
    labels: set[str] = set()
    for val in holdings["industry"].dropna():
        text = safe_str(val).strip()
        if text and text.upper() not in {"N/A", "NA", ""}:
            labels.add(text)
    return sorted(labels)


def filter_stocks_by_holdings_industries(stocks: pd.DataFrame) -> pd.DataFrame:
    """Keep listings whose industry matches a Holdings portfolio industry."""
    if stocks.empty:
        return stocks
    labels = holdings_industry_labels()
    if not labels:
        return stocks.iloc[0:0].copy()
    if "industry" not in stocks.columns:
        return stocks.iloc[0:0].copy()
    return stocks[stocks["industry"].isin(labels)].copy()


def holdings_playlist_listings(
    stocks: pd.DataFrame,
    *,
    sector: str | list[str] = "All",
    search: str = "",
    industry: str | list[str] = "All",
    sub_sector: str | list[str] = "All",
) -> pd.DataFrame:
    """Listings for SQLite Holdings, merged with India dataset metadata."""
    holdings = _load_holdings(seed_if_empty=True)
    if holdings.empty:
        return stocks.iloc[0:0].copy()

    tickers = holdings_playlist_tickers(seed_if_empty=False)
    if not tickers:
        return stocks.iloc[0:0].copy()

    matched = stocks[stocks["ticker"].astype(str).str.upper().isin(tickers)].copy()
    matched_tickers = set(matched["ticker"].astype(str).str.upper())
    missing = tickers - matched_tickers
    if missing:
        lookup = holdings.set_index(holdings["ticker"].astype(str).str.upper())
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
