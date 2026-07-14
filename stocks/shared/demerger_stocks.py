"""Unified demerger stock list — parents + spin-offs in one SQLite watchlist."""

from __future__ import annotations

import pandas as pd

from stocks.core.database import (
    demerger_stocks_count,
    load_demerger_stocks_from_db,
    replace_demerger_stocks_in_db,
)
from stocks.core.text_utils import safe_str
from stocks.listings.stocks_data import load_india_stocks
from stocks.shared.corp_tags import clear_corp_tags_cache
from stocks.shared.portfolio import enrich_holdings


def _stock_meta_lookup() -> dict[str, dict[str, str]]:
    try:
        stocks = load_india_stocks()
    except Exception:
        return {}
    if stocks.empty:
        return {}
    lookup: dict[str, dict[str, str]] = {}
    for _, row in stocks.drop_duplicates("ticker").iterrows():
        ticker = safe_str(row.get("ticker")).upper()
        if not ticker:
            continue
        lookup[ticker] = {
            "market": safe_str(row.get("market")).upper() or "NSE",
            "name": safe_str(row.get("name")),
            "sector": safe_str(row.get("sector")),
            "industry": safe_str(row.get("industry")),
            "sub_sector": safe_str(row.get("sub_sector")),
        }
    return lookup


def _fmt_ex_date(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _rows_from_demerger_df(df: pd.DataFrame) -> list[dict]:
    """Build one row per parent or spin-off ticker from the demerger feed."""
    if df is None or df.empty:
        return []
    lookup = _stock_meta_lookup()
    by_ticker: dict[str, dict] = {}

    def _upsert(entry: dict) -> None:
        ticker = safe_str(entry.get("ticker")).upper()
        if not ticker:
            return
        meta = lookup.get(ticker, {})
        ex_date = _fmt_ex_date(entry.get("ex_date"))
        merged = {
            "ticker": ticker,
            "role": entry.get("role"),
            "peer_ticker": safe_str(entry.get("peer_ticker")).upper() or None,
            "peer_company": entry.get("peer_company"),
            "ex_date": ex_date,
            "market": meta.get("market") or safe_str(entry.get("market")).upper() or "NSE",
            "name": meta.get("name") or entry.get("name"),
            "sector": entry.get("sector") or meta.get("sector"),
            "industry": entry.get("industry") or meta.get("industry"),
            "sub_sector": entry.get("sub_sector") or meta.get("sub_sector"),
            "snapshot_price": entry.get("snapshot_price"),
        }
        existing = by_ticker.get(ticker)
        if existing is None:
            by_ticker[ticker] = merged
            return
        old_ex = existing.get("ex_date")
        if ex_date and (not old_ex or ex_date > old_ex):
            by_ticker[ticker] = merged

    for _, row in df.iterrows():
        role = safe_str(row.get("row_role"))
        ticker = safe_str(row.get("ticker")).upper()
        if not ticker:
            continue

        if role == "Parent":
            demerged = safe_str(row.get("demerged_ticker")).upper()
            _upsert(
                {
                    "ticker": ticker,
                    "role": "Parent",
                    "peer_ticker": demerged or None,
                    "peer_company": row.get("demerged_company"),
                    "ex_date": row.get("ex_date"),
                    "name": row.get("company"),
                }
            )
            if demerged:
                _upsert(
                    {
                        "ticker": demerged,
                        "role": "Spin-off",
                        "peer_ticker": ticker,
                        "peer_company": row.get("company"),
                        "ex_date": row.get("ex_date"),
                        "name": row.get("demerged_company"),
                    }
                )
            continue

        if role == "Spin-off":
            parent = safe_str(row.get("parent_ticker")).upper()
            _upsert(
                {
                    "ticker": ticker,
                    "role": "Spin-off",
                    "peer_ticker": parent or None,
                    "peer_company": row.get("parent_company"),
                    "ex_date": row.get("ex_date"),
                    "name": row.get("company"),
                }
            )
            if parent:
                _upsert(
                    {
                        "ticker": parent,
                        "role": "Parent",
                        "peer_ticker": ticker,
                        "peer_company": row.get("company"),
                        "ex_date": row.get("ex_date"),
                        "name": row.get("parent_company"),
                    }
                )

    return list(by_ticker.values())


def persist_demerger_stocks_from_feed(df: pd.DataFrame) -> int:
    """Replace the D&S watchlist from a demerger feed dataframe."""
    rows = _rows_from_demerger_df(df)
    if not rows:
        return 0
    replace_demerger_stocks_in_db(pd.DataFrame(rows))
    clear_corp_tags_cache()
    from stocks.core.database import sync_corp_tags_from_demerger_stocks

    sync_corp_tags_from_demerger_stocks()
    return len(rows)


def load_demerger_stocks() -> pd.DataFrame:
    return load_demerger_stocks_from_db()


def enrich_demerger_stocks(
    stocks: pd.DataFrame,
    *,
    use_cache: bool = True,  # noqa: ARG001
    with_momentum: bool = True,
) -> pd.DataFrame:
    if stocks.empty:
        return stocks
    work = stocks.copy()
    if "qty" not in work.columns:
        work["qty"] = None
    if "avg_price" not in work.columns:
        work["avg_price"] = None
    return enrich_holdings(work, use_cache=use_cache, with_momentum=with_momentum)
