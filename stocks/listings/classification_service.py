"""Sector / industry / sub-sector from stock-analysis sqlite (NSE.db, BSE.db, SME.db)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from stocks.core.config import STOCK_ANALYSIS_SQLITE_DIR
from stocks.core.database import load_holdings_from_db, save_holdings_to_db
from stocks.core.text_utils import safe_str
from stocks.listings.sector_display import display_sector

_CLASS_COLS = ("sector", "industry", "subsector")


def _clean(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.lower() in ("", "nan", "none", "nat", "null"):
        return ""
    return text


def _merge_class(
    existing: tuple[str, str, str],
    incoming: tuple[str, str, str],
) -> tuple[str, str, str]:
    out = list(existing)
    for i, val in enumerate(incoming):
        if val and not out[i]:
            out[i] = val
    return tuple(out)


def _tuple_from_row(sector="", industry="", subsector="") -> tuple[str, str, str]:
    sector = _clean(sector)
    industry = _clean(industry)
    subsector = _clean(subsector)
    if not industry and subsector:
        industry = subsector
    if not subsector and industry:
        subsector = industry
    return sector, industry, subsector


def _read_classification_db(db_path: Path, *, has_bse_code: bool) -> pd.DataFrame:
    if not db_path.is_file():
        return pd.DataFrame()
    cols = ["nse_code", "sector", "industry", "subsector"]
    if has_bse_code:
        cols.insert(1, "bse_code")
    query = f"SELECT {', '.join(cols)} FROM stocks"
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql(query, conn)


def load_classification_maps(
    sqlite_dir: Path | None = None,
) -> dict[str, dict[str, tuple[str, str, str]]]:
    """
    Build lookups from stock-analysis sqlite DBs.
    Returns {"by_symbol": {TICKER: (sector, industry, subsector)}, "by_bse_code": {...}}.
    """
    base = Path(sqlite_dir or STOCK_ANALYSIS_SQLITE_DIR)
    maps: dict[str, dict[str, tuple[str, str, str]]] = {
        "by_symbol": {},
        "by_bse_code": {},
    }

    def _ingest_symbol(symbol: str, sector: str, industry: str, subsector: str) -> None:
        sym = _clean(symbol).upper()
        if not sym:
            return
        incoming = _tuple_from_row(sector, industry, subsector)
        maps["by_symbol"][sym] = _merge_class(
            maps["by_symbol"].get(sym, ("", "", "")), incoming
        )

    def _ingest_bse_code(code: str, sector: str, industry: str, subsector: str) -> None:
        bse = _clean(code)
        if bse.endswith(".0"):
            bse = bse[:-2]
        if not bse:
            return
        incoming = _tuple_from_row(sector, industry, subsector)
        maps["by_bse_code"][bse] = _merge_class(
            maps["by_bse_code"].get(bse, ("", "", "")), incoming
        )

    for name, has_bse in (("NSE.db", False), ("SME.db", False), ("BSE.db", True)):
        df = _read_classification_db(base / name, has_bse_code=has_bse)
        if df.empty:
            continue
        for _, row in df.iterrows():
            _ingest_symbol(
                row.get("nse_code"),
                row.get("sector"),
                row.get("industry"),
                row.get("subsector"),
            )
            if has_bse:
                _ingest_bse_code(
                    row.get("bse_code"),
                    row.get("sector"),
                    row.get("industry"),
                    row.get("subsector"),
                )

    return maps


def lookup_classification(
    ticker: str,
    *,
    maps: dict | None = None,
    market: str | None = None,
) -> tuple[str, str, str]:
    """Return (sector, industry, sub_sector) for a ticker symbol."""
    maps = maps or load_classification_maps()
    sym = safe_str(ticker).upper()
    if not sym:
        return "", "", ""

    hit = maps["by_symbol"].get(sym)
    if hit and any(hit):
        return hit

    # BSE listings sometimes use numeric codes as tickers in legacy datasets.
    if sym.isdigit():
        bse_hit = maps["by_bse_code"].get(sym)
        if bse_hit and any(bse_hit):
            return bse_hit

    if market and safe_str(market).upper() == "BSE":
        bse_hit = maps["by_bse_code"].get(sym)
        if bse_hit and any(bse_hit):
            return bse_hit

    return "", "", ""


def _pick_canonical_class(rows: pd.DataFrame) -> tuple[str, str, str]:
    sector = industry = subsector = ""
    for _, row in rows.iterrows():
        s = _clean(row.get("sector"))
        i = _clean(row.get("industry"))
        ss = _clean(row.get("sub_sector"))
        if not industry and i:
            industry = i
            subsector = ss or i
        if not subsector and ss:
            subsector = ss
            if not industry:
                industry = ss
        if not sector and s:
            sector = s
    return sector, industry, subsector


def propagate_classification_by_ticker(stocks: pd.DataFrame) -> pd.DataFrame:
    """One industry / sub-sector per unique ticker across NSE + BSE listings."""
    if stocks is None or stocks.empty or "ticker" not in stocks.columns:
        return stocks if stocks is not None else pd.DataFrame()

    out = stocks.copy()
    for col in ("sector", "industry", "sub_sector"):
        if col not in out.columns:
            out[col] = ""

    canonical: dict[str, tuple[str, str, str]] = {}
    for ticker, group in out.groupby(out["ticker"].astype(str).str.upper()):
        canonical[ticker] = _pick_canonical_class(group)

    sectors: list[str] = []
    industries: list[str] = []
    sub_sectors: list[str] = []
    for _, row in out.iterrows():
        sector, industry, subsector = canonical.get(
            safe_str(row.get("ticker")).upper(), ("", "", "")
        )
        sectors.append(sector or _clean(row.get("sector")))
        industries.append(industry)
        sub_sectors.append(subsector)

    out["sector"] = sectors
    out["industry"] = industries
    out["sub_sector"] = sub_sectors
    return out


def _fallback_industry_from_sector(
    sector: str,
    industry: str,
    subsector: str,
    *,
    raw_sector: str = "",
) -> tuple[str, str, str]:
    """Fill industry from sqlite sub-sector or raw HF sector — never duplicate display sector."""
    industry = _clean(industry)
    subsector = _clean(subsector)
    display = _clean(sector)
    if industry and industry != display:
        return industry, subsector or industry
    raw = _clean(raw_sector)
    if raw and raw != display:
        return raw, subsector or raw
    if subsector and subsector != display:
        return subsector, subsector
    return "", ""


def enrich_stocks_classification(
    stocks: pd.DataFrame,
    *,
    sqlite_dir: Path | None = None,
    overwrite_sector: bool = False,
) -> pd.DataFrame:
    """Merge sector / industry / sub_sector from local sqlite into a stocks frame."""
    if stocks is None or stocks.empty:
        return stocks if stocks is not None else pd.DataFrame()

    maps = load_classification_maps(sqlite_dir)
    out = stocks.copy()
    if "industry" not in out.columns:
        out["industry"] = ""
    if "sub_sector" not in out.columns:
        out["sub_sector"] = ""

    sectors: list[str] = []
    industries: list[str] = []
    sub_sectors: list[str] = []

    for _, row in out.iterrows():
        ticker = safe_str(row.get("ticker")).upper()
        market = safe_str(row.get("market")) or None
        existing_sector = _clean(row.get("sector"))
        raw_sector = _clean(row.get("source_sector")) or existing_sector
        sector, industry, subsector = lookup_classification(
            ticker, maps=maps, market=market
        )

        if sector and (overwrite_sector or not existing_sector):
            final_sector = sector
        else:
            final_sector = existing_sector or sector

        industry, subsector = _fallback_industry_from_sector(
            final_sector,
            industry,
            subsector,
            raw_sector=raw_sector,
        )

        industries.append(industry)
        sub_sectors.append(subsector)
        sectors.append(final_sector)

    out["sector"] = sectors
    out["industry"] = industries
    out["sub_sector"] = sub_sectors
    return propagate_classification_by_ticker(out)


def sync_holdings_classification(*, sqlite_dir: Path | None = None) -> int:
    """Update holdings sector / industry / sub_sector from classification sqlite."""
    holdings = load_holdings_from_db()
    if holdings.empty:
        return 0

    maps = load_classification_maps(sqlite_dir)
    updated = 0
    rows: list[dict] = []

    for _, row in holdings.iterrows():
        item = row.to_dict()
        ticker = safe_str(item.get("ticker")).upper()
        market = safe_str(item.get("market")) or None
        sector, industry, subsector = lookup_classification(
            ticker, maps=maps, market=market
        )
        existing_sector = _clean(item.get("sector"))
        final_sector = sector or existing_sector
        industry, subsector = _fallback_industry_from_sector(
            final_sector,
            industry,
            subsector,
            raw_sector=existing_sector,
        )
        mapped_sector = display_sector(
            sector=final_sector,
            industry=industry,
            sub_sector=subsector,
        )

        for field, value in (
            ("sector", mapped_sector or final_sector or sector),
            ("industry", industry),
            ("sub_sector", subsector),
        ):
            if not value:
                continue
            if _clean(item.get(field)) != value:
                item[field] = value
                updated += 1
            elif not _clean(item.get(field)):
                item[field] = value
                updated += 1

        rows.append(item)

    save_holdings_to_db(pd.DataFrame(rows))
    return updated


def classification_sources_ok(sqlite_dir: Path | None = None) -> tuple[bool, list[str]]:
    """True if at least one stock-analysis sqlite DB exists."""
    base = Path(sqlite_dir or STOCK_ANALYSIS_SQLITE_DIR)
    found = [name for name in ("NSE.db", "BSE.db", "SME.db") if (base / name).is_file()]
    return bool(found), found


def classification_coverage(stocks: pd.DataFrame) -> dict[str, int]:
    """Counts for Settings / diagnostics."""
    if stocks is None or stocks.empty:
        return {
            "tickers": 0,
            "industry": 0,
            "sub_sector": 0,
            "industry_from_sector": 0,
            "source_sector": 0,
        }
    tickers = stocks["ticker"].astype(str).str.upper().nunique()
    by_t = stocks.drop_duplicates("ticker")
    has_industry = by_t["industry"].fillna("").astype(str).str.strip() != ""
    industry = int(has_industry.sum())
    sub_sector = int((by_t["sub_sector"].fillna("").astype(str).str.strip() != "").sum())
    source_sector = 0
    if "source_sector" in by_t.columns:
        source_sector = int(
            (by_t["source_sector"].fillna("").astype(str).str.strip() != "").sum()
        )
    # Industry label copied from HF sector when sqlite had no finer taxonomy.
    sector_eq = (
        by_t["sector"].fillna("").astype(str).str.strip()
        == by_t["industry"].fillna("").astype(str).str.strip()
    )
    from_sector = int((has_industry & sector_eq).sum())
    return {
        "tickers": int(tickers),
        "industry": industry,
        "sub_sector": sub_sector,
        "source_sector": source_sector,
        "industry_from_sector": from_sector,
    }


def classification_status(
    stocks: pd.DataFrame,
    *,
    sqlite_dir: Path | None = None,
) -> dict[str, int | bool | list[str]]:
    """Coverage plus sqlite availability for diagnostics."""
    ok, found = classification_sources_ok(sqlite_dir)
    return {
        "sqlite_ok": ok,
        "sqlite_files": found,
        **classification_coverage(stocks),
    }
