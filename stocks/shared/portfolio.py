"""Holdings stored in SQLite + live prices from yfinance."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from stocks.core.config import HOLDINGS_PEAD_CACHE_HOURS
from stocks.core.database import (
    holdings_count,
    load_holdings_from_db,
    replace_holdings_in_db,
    save_holdings_to_db,
)
from stocks.core.text_utils import resolve_company_name, safe_str
from stocks.listings.stock_overrides import ticker_meta_override
from stocks.listings.stocks_data import load_india_stocks
from stocks.market.momentum import attach_holdings_momentum
from stocks.market.price_service import attach_prices
from stocks.shared.links import attach_research_links

# Default portfolio (seeded once when holdings table is empty).
_DEFAULT_HOLDINGS: list[dict] = [
    {"ticker": "BPL", "sector": "Technology", "sub_sector": "Home Electronics & Appliances", "snapshot_price": 54.44},
    {"ticker": "DGCONTENT", "sector": "Communication Services", "sub_sector": "Online Services", "snapshot_price": 26.91},
    {"ticker": "GPTINFRA", "sector": "Industrials", "sub_sector": "Construction & Engineering", "snapshot_price": 121.39},
    {"ticker": "HMT", "sector": "Industrials", "sub_sector": "Industrial Machinery", "snapshot_price": 64.74},
    {"ticker": "LOKESHMACH", "sector": "Industrials", "sub_sector": "Industrial Machinery", "snapshot_price": 270.25},
    {"ticker": "MIRCELECTR", "sector": "Consumer Cyclical", "sub_sector": "Home Electronics & Appliances", "snapshot_price": 38.20},
    {"ticker": "BHAGYANGR", "sector": "Basic Materials", "sub_sector": "Electrical Components & Equipments", "snapshot_price": 388.05},
    {"ticker": "PFS", "sector": "Financial Services", "sub_sector": "Specialized Finance", "snapshot_price": 31.05},
    {"ticker": "FOODSIN", "sector": "Consumer Defensive", "sub_sector": "FMCG - Foods", "snapshot_price": 56.39},
    {"ticker": "XPROINDIA", "sector": "Basic Materials", "sub_sector": "Plastic Products", "snapshot_price": 1344.80},
    {"ticker": "PNBGILTS", "sector": "Financial Services", "sub_sector": "Investment Banking & Brokerage", "snapshot_price": 92.05},
    {"ticker": "TVSELECT", "sector": "Technology", "sub_sector": "Technology Hardware", "snapshot_price": 482.35},
    {"ticker": "TCPLPACK", "sector": "Consumer Cyclical", "sub_sector": "Packaging", "snapshot_price": 3029.40},
    {"ticker": "PPL", "sector": "Industrials", "sub_sector": "Building Products - Pipes", "snapshot_price": 259.63},
    {"ticker": "STERTOOLS", "sector": "Industrials", "sub_sector": "Industrial Machinery", "snapshot_price": 245.52},
    {"ticker": "KAMDHENU", "sector": "Basic Materials", "sub_sector": "Iron & Steel", "snapshot_price": 28.83},
    {"ticker": "SUKHJITS", "sector": "Basic Materials", "sub_sector": "Agro Products", "snapshot_price": 172.24},
    {"ticker": "INDBANK", "sector": "Financial Services", "sub_sector": "Investment Banking & Brokerage", "snapshot_price": 33.82},
    {"ticker": "WINDLAS", "sector": "Healthcare", "sub_sector": "Pharmaceuticals", "snapshot_price": 816.00},
    {"ticker": "ALPHAGEO", "sector": "Energy", "sub_sector": "Oil & Gas - Equipment & Services", "snapshot_price": 208.31},
    {"ticker": "RAMRAT", "sector": "Industrials", "sub_sector": "Electrical Components & Equipments", "snapshot_price": 407.15},
    {"ticker": "MAHEPC", "sector": "Industrials", "sub_sector": "Agricultural & Farm Machinery", "snapshot_price": 116.50},
    {"ticker": "FOSECOIND", "sector": "Basic Materials", "sub_sector": "Specialty Chemicals", "snapshot_price": 5258.50},
    {"ticker": "NELCO", "sector": "Technology", "sub_sector": "Communication & Networking", "snapshot_price": 940.35},
    {"ticker": "MANAKCOAT", "sector": "Industrials", "sub_sector": "Metals - Diversified", "snapshot_price": 116.10},
    {"ticker": "GOLDIAM", "sector": "Consumer Cyclical", "sub_sector": "Precious Metals, Jewellery & Watches", "snapshot_price": 474.60},
    {"ticker": "RPGLIFE", "sector": "Healthcare", "sub_sector": "Pharmaceuticals", "snapshot_price": 2277.40},
    {"ticker": "SEAMECLTD", "sector": "Industrials", "sub_sector": "Oil & Gas - Equipment & Services", "snapshot_price": 1366.80},
    {"ticker": "ROTO", "sector": "Industrials", "sub_sector": "Industrial Machinery", "snapshot_price": 64.39},
    {"ticker": "KOTHARIPET", "sector": "Basic Materials", "sub_sector": "Commodity Chemicals", "snapshot_price": 122.67},
    {"ticker": "ZODIAC", "name": "Zodiac Energy Limited", "sector": "Energy", "sub_sector": "Renewable Energy Equipment & Services", "snapshot_price": 280.70},
    {"ticker": "INDRAMEDCO", "sector": "Healthcare", "sub_sector": "Hospitals & Diagnostic Centres", "snapshot_price": 382.95},
    {"ticker": "APTECHT", "sector": "Consumer Defensive", "sub_sector": "Education Services", "snapshot_price": 110.95},
    {"ticker": "LAGNAM", "sector": "Consumer Cyclical", "sub_sector": "Textiles", "snapshot_price": 82.48},
    {"ticker": "CUPID", "sector": "Consumer Defensive", "sub_sector": "FMCG - Personal Products", "snapshot_price": 176.92},
    {"ticker": "THEINVEST", "sector": "Financial Services", "sub_sector": "Investment Banking & Brokerage", "snapshot_price": 98.57},
    {"ticker": "TEXINFRA", "sector": "Real Estate", "sub_sector": "Real Estate", "snapshot_price": 102.39},
    {"ticker": "MAANALU", "sector": "Basic Materials", "sub_sector": "Metals - Aluminium", "snapshot_price": 127.14},
    {"ticker": "EKC", "sector": "Industrials", "sub_sector": "Gas Distribution", "snapshot_price": 113.55},
    {"ticker": "SATIA", "sector": "Basic Materials", "sub_sector": "Paper Products", "snapshot_price": 55.50},
    {"ticker": "JAYBARMARU", "sector": "Consumer Cyclical", "sub_sector": "Auto Parts", "snapshot_price": 169.55},
    {"ticker": "TBZ", "sector": "Consumer Cyclical", "sub_sector": "Precious Metals, Jewellery & Watches", "snapshot_price": 188.88},
    {"ticker": "AHLEAST", "sector": "Consumer Cyclical", "sub_sector": "Hotels, Resorts & Cruise Lines", "snapshot_price": 155.82},
    {"ticker": "SANGHVIMOV", "sector": "Industrials", "sub_sector": "Business Support Services", "snapshot_price": 414.75},
    {"ticker": "APCOTEXIND", "sector": "Basic Materials", "sub_sector": "Specialty Chemicals", "snapshot_price": 546.65},
    {"ticker": "ADFFOODS", "sector": "Consumer Defensive", "sub_sector": "Packaged Foods & Meats", "snapshot_price": 306.85},
    {"ticker": "EVERESTIND", "sector": "Industrials", "sub_sector": "Building Products - Prefab Structures", "snapshot_price": 378.40},
    {"ticker": "CARYSIL", "sector": "Consumer Cyclical", "sub_sector": "Home Furnishing", "snapshot_price": 1199.30},
    {"ticker": "CDSL", "sector": "Financial Services", "sub_sector": "Stock Exchanges & Ratings", "snapshot_price": 1370.30},
    {"ticker": "AFFLE", "sector": "Communication Services", "sub_sector": "Advertising", "snapshot_price": 1463.70},
    {"ticker": "HNDFDS", "sector": "Industrials", "sub_sector": "FMCG - Foods", "snapshot_price": 545.40},
    {"ticker": "PRIVISCL", "sector": "Basic Materials", "sub_sector": "Specialty Chemicals", "snapshot_price": 3493.90},
    {"ticker": "AAVAS", "sector": "Financial Services", "sub_sector": "Home Financing", "snapshot_price": 1471.90},
    {"ticker": "ARTEMISMED", "name": "Artemis Medicare Services Limited", "sector": "Healthcare", "sub_sector": "Hospitals & Diagnostic Centres", "snapshot_price": 258.65},
    {"ticker": "COSMOFIRST", "sector": "Consumer Cyclical", "sub_sector": "Packaging", "snapshot_price": 780.75},
    {"ticker": "BLS", "sector": "Industrials", "sub_sector": "Outsourced services", "snapshot_price": 267.45},
    {"ticker": "CLEDUCATE", "sector": "Consumer Defensive", "sub_sector": "Education Services", "snapshot_price": 50.51},
    {"ticker": "HIRECT", "sector": "Industrials", "sub_sector": "Electrical Components & Equipments", "snapshot_price": 1152.40},
    {"ticker": "PRIMESECU", "sector": "Financial Services", "sub_sector": "Investment Banking & Brokerage", "snapshot_price": 299.90},
    {"ticker": "HERCULES", "sector": "Industrials", "sub_sector": "Industrial Machinery", "snapshot_price": 159.00},
    {"ticker": "IRISDOREME", "sector": "Consumer Cyclical", "sub_sector": "Retail - Apparel", "snapshot_price": 39.91},
    {"ticker": "RML", "sector": "Consumer Cyclical", "sub_sector": "Auto Parts", "snapshot_price": 1121.15},
    {"ticker": "SMSPHARMA", "sector": "Healthcare", "sub_sector": "Pharmaceuticals", "snapshot_price": 378.60},
    {"ticker": "CLSEL", "sector": "Consumer Defensive", "sub_sector": "Packaged Foods & Meats", "snapshot_price": 295.35},
    {"ticker": "TEAMGTY", "sector": "Financial Services", "sub_sector": "Asset Management", "snapshot_price": 230.70},
    {"ticker": "GPTHEALTH", "sector": "Healthcare", "sub_sector": "Hospitals & Diagnostic Centres", "snapshot_price": 147.82},
    {"ticker": "TRF", "sector": "Industrials", "sub_sector": "Industrial Machinery", "snapshot_price": 233.80},
    {"ticker": "SURAJEST", "name": "Suraj Estate Developers Limited", "sector": "Real Estate", "industry": "Real Estate", "sub_sector": "Real Estate", "snapshot_price": 196.10},
    {"ticker": "HALEOSLABS", "sector": "Healthcare", "sub_sector": "Pharmaceuticals", "snapshot_price": 1410.20},
    {"ticker": "EPACK", "sector": "Consumer Cyclical", "sub_sector": "Home Electronics & Appliances", "snapshot_price": 230.39},
    {"ticker": "EPACKPEB", "name": "Epack Prefab Technologies Limited", "sector": "Industrials", "industry": "Building Products - Prefab Structures", "sub_sector": "Building Products - Prefab Structures", "snapshot_price": 268.98},
    {"ticker": "DYCL", "name": "Dynamic Cables Ltd.", "sector": "Producer manufacturing", "sub_sector": "Electrical Components & Equipments", "snapshot_price": None},
    {"ticker": "20MICRONS", "name": "20 Microns Limited", "sector": "Process industries", "sub_sector": "Specialty Chemicals", "snapshot_price": None},
    {
        "ticker": "KAMOPAINTS",
        "name": "Kamdhenu Ventures (Komo Paints)",
        "sector": "Basic Materials",
        "sub_sector": "Paints",
        "snapshot_price": 5.32,
    },
    {
        "ticker": "ATAM",
        "name": "Atam Valves Ltd.",
        "sector": "Engineering & Capital Goods",
        "sub_sector": "Industrial Machinery",
        "snapshot_price": None,
    },
]


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


def _market_lookup() -> dict[str, dict[str, str]]:
    return _stock_meta_lookup()


def _build_seed_frame() -> pd.DataFrame:
    lookup = _market_lookup()
    rows: list[dict] = []
    for item in _DEFAULT_HOLDINGS:
        ticker = safe_str(item["ticker"]).upper()
        meta = lookup.get(ticker, {})
        override = ticker_meta_override(ticker)
        rows.append(
            {
                "ticker": ticker,
                "market": meta.get("market") or "NSE",
                "name": resolve_company_name(
                    override.get("name"),
                    item.get("name"),
                    meta.get("name"),
                    ticker=ticker,
                )
                or None,
                "sector": item["sector"] or override.get("sector") or meta.get("sector"),
                "industry": item.get("industry")
                or override.get("industry")
                or meta.get("industry"),
                "sub_sector": item["sub_sector"]
                or override.get("sub_sector")
                or meta.get("sub_sector"),
                "qty": None,
                "avg_price": None,
                "snapshot_price": item["snapshot_price"],
            }
        )
    return pd.DataFrame(rows)


def seed_default_holdings(*, force: bool = False) -> int:
    """Insert default portfolio when DB is empty (or replace all when force=True)."""
    if not force and holdings_count() > 0:
        return holdings_count()
    frame = _build_seed_frame()
    if force:
        replace_holdings_in_db(frame)
    else:
        save_holdings_to_db(frame)
    return len(frame)


def load_holdings(*, seed_if_empty: bool = True) -> pd.DataFrame:
    if seed_if_empty and holdings_count() == 0:
        seed_default_holdings()
    return load_holdings_from_db()


def save_holdings(df: pd.DataFrame) -> None:
    save_holdings_to_db(df)


def add_holdings(entries: list[dict]) -> int:
    """Upsert additional holdings (ticker, sector, sub_sector, snapshot_price)."""
    if not entries:
        return 0
    lookup = _market_lookup()
    rows: list[dict] = []
    for item in entries:
        ticker = safe_str(item["ticker"]).upper()
        if not ticker:
            continue
        meta = lookup.get(ticker, {})
        override = ticker_meta_override(ticker)
        rows.append(
            {
                "ticker": ticker,
                "market": meta.get("market") or safe_str(item.get("market")).upper() or "NSE",
                "name": resolve_company_name(
                    override.get("name"),
                    item.get("name"),
                    meta.get("name"),
                    ticker=ticker,
                )
                or None,
                "sector": item.get("sector") or override.get("sector"),
                "industry": item.get("industry")
                or override.get("industry")
                or meta.get("industry"),
                "sub_sector": item.get("sub_sector") or override.get("sub_sector"),
                "qty": item.get("qty"),
                "avg_price": item.get("avg_price"),
                "snapshot_price": item.get("snapshot_price"),
            }
        )
    save_holdings_to_db(pd.DataFrame(rows))
    return len(rows)


def _fill_holdings_classification(holdings: pd.DataFrame) -> pd.DataFrame:
    if holdings.empty:
        return holdings
    lookup = _stock_meta_lookup()
    out = holdings.copy()
    for col in ("name", "sector", "industry", "sub_sector"):
        if col not in out.columns:
            out[col] = ""
    for idx, row in out.iterrows():
        ticker = safe_str(row.get("ticker")).upper()
        meta = lookup.get(ticker, {})
        override = ticker_meta_override(ticker)
        name = resolve_company_name(
            override.get("name"),
            row.get("name"),
            meta.get("name"),
            ticker=ticker,
        )
        if name and name.upper() != ticker:
            out.at[idx, "name"] = name
        for col in ("sector", "industry", "sub_sector"):
            if not safe_str(out.at[idx, col]):
                val = override.get(col) or meta.get(col)
                if val:
                    out.at[idx, col] = val
    return out


def backfill_holdings_names(*, persist: bool = True) -> int:
    """Fill blank / ticker-only names from stock_overrides (no listings download)."""
    df = load_holdings_from_db()
    if df.empty:
        return 0
    out = df.copy()
    if "name" not in out.columns:
        out["name"] = ""
    changed = 0
    for idx, row in out.iterrows():
        ticker = safe_str(row.get("ticker")).upper()
        if not ticker:
            continue
        override = ticker_meta_override(ticker)
        if not override:
            continue
        new_name = safe_str(override.get("name"))
        old_name = safe_str(row.get("name"))
        if new_name and (not old_name or old_name.upper() == ticker):
            out.at[idx, "name"] = new_name
            changed += 1
        for col in ("sector", "industry", "sub_sector"):
            if col not in out.columns:
                out[col] = ""
            if not safe_str(out.at[idx, col]) and override.get(col):
                out.at[idx, col] = override[col]
                changed += 1
    if changed and persist:
        save_holdings_to_db(out)
    return changed


def load_holdings(*, seed_if_empty: bool = True) -> pd.DataFrame:
    if seed_if_empty and holdings_count() == 0:
        seed_default_holdings()
    backfill_holdings_names(persist=True)
    return load_holdings_from_db()


def enrich_holdings(
    holdings: pd.DataFrame,
    *,
    use_cache: bool = True,  # noqa: ARG001 — kept for callers
    with_momentum: bool = False,
    with_pead_expand: bool = False,
    pead_progress_callback: Callable[[int, int], None] | None = None,
) -> pd.DataFrame:
    if holdings.empty:
        return holdings

    out = _fill_holdings_classification(holdings.copy())
    if with_momentum:
        out = attach_holdings_momentum(out)
    else:
        out = attach_prices(out)

    # PEAD-style rows use `price`; momentum path also sets current_price.
    if "price" not in out.columns or out["price"].isna().all():
        if "current_price" in out.columns:
            out["price"] = out["current_price"]

    qty = pd.to_numeric(out.get("qty"), errors="coerce")
    price = pd.to_numeric(out.get("current_price"), errors="coerce")
    if price.isna().all():
        price = pd.to_numeric(out.get("price"), errors="coerce")
    avg = pd.to_numeric(out.get("avg_price"), errors="coerce")
    snap = pd.to_numeric(out.get("snapshot_price"), errors="coerce")

    out["value"] = (qty * price).where(qty.notna() & price.notna()).round(2)
    out["pnl_pct"] = ((price - avg) / avg * 100).where(
        avg.notna() & (avg > 0) & price.notna()
    ).round(2)
    out["chg_from_snapshot_pct"] = ((price - snap) / snap * 100).where(
        snap.notna() & (snap > 0) & price.notna()
    ).round(2)

    out = attach_research_links(out)

    if with_pead_expand:
        out = refresh_holdings_pead_metrics(out, progress_callback=pead_progress_callback)

    return out


def refresh_holdings_pead_metrics(
    priced: pd.DataFrame,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
) -> pd.DataFrame:
    """Re-attach PEAD score, PE, and expand-panel fields after a PEAD backfill."""
    if priced is None or priced.empty:
        return priced if priced is not None else pd.DataFrame()

    from stocks.strategies.pead2.cache_lookup import (
        attach_pead_scores,
        load_pead_pe_by_ticker,
    )
    from stocks.strategies.pead2.expand_data import attach_pead_expand

    out = attach_pead_expand(
        priced,
        progress_callback=progress_callback,
        cache_hours=HOLDINGS_PEAD_CACHE_HOURS,
    )
    out = attach_pead_scores(out, max_hours=HOLDINGS_PEAD_CACHE_HOURS)

    for col in ("pe_ratio", "forward_pe"):
        if col not in out.columns:
            out[col] = pd.NA
    pe_map = load_pead_pe_by_ticker(
        out["ticker"].astype(str).str.upper().tolist(),
        max_hours=HOLDINGS_PEAD_CACHE_HOURS,
    )
    for idx, row in out.iterrows():
        ticker = safe_str(row.get("ticker")).upper()
        entry = pe_map.get(ticker) or {}
        if pd.isna(row.get("pe_ratio")) and entry.get("pe_ratio") is not None:
            out.at[idx, "pe_ratio"] = entry["pe_ratio"]
        if pd.isna(row.get("forward_pe")) and entry.get("forward_pe") is not None:
            out.at[idx, "forward_pe"] = entry["forward_pe"]
    return out


def run_holdings_pead_backfill(
    holdings: pd.DataFrame,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
) -> int:
    """Fetch PEAD2 cache for holdings tickers missing scorable data. Returns fetch count."""
    if holdings is None or holdings.empty:
        return 0

    from stocks.core.config import PEAD2_MAX_WORKERS
    from stocks.strategies.pead2.cache_lookup import backfill_pead_cache_for_tickers

    tickers = holdings["ticker"].astype(str).str.upper().tolist()
    markets = (
        holdings["market"].astype(str).tolist()
        if "market" in holdings.columns
        else None
    )
    return backfill_pead_cache_for_tickers(
        tickers,
        markets,
        max_fetch=len(tickers),
        max_workers=PEAD2_MAX_WORKERS,
        progress_callback=progress_callback,
    )
