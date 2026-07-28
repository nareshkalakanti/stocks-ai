#!/usr/bin/env python3
"""
Rebuild sector classification sqlite (NSE.db / SME.db) from stock-analysis CSVs,
patch known mislabels into NSE/BSE/SME DBs, then re-merge into stocks-ai.

Usage (from repo root):
  python scripts/refresh_sector_classification.py
  python scripts/refresh_sector_classification.py --refresh-csv

Env:
  STOCK_ANALYSIS_SQLITE_DIR  — default …/stock-analysis/sqlite
  STOCK_ANALYSIS_DATA_DIR    — default <sqlite_dir>/../data
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

import pandas as pd

# Allow `python scripts/…` from repo root without installing the package.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from stocks.core.config import STOCK_ANALYSIS_SQLITE_DIR
from stocks.core.text_utils import safe_str
from stocks.listings.classification_service import classification_coverage
from stocks.listings.stock_overrides import classification_overrides
from stocks.listings.stocks_data import rebuild_india_stocks_classification


def _data_dir() -> Path:
    env = os.getenv("STOCK_ANALYSIS_DATA_DIR", "").strip()
    if env:
        return Path(env)
    return Path(STOCK_ANALYSIS_SQLITE_DIR).resolve().parent / "data"


def _clean_mcap(raw) -> float:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)) or raw == "":
        return 0.0
    try:
        return float(str(raw).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _build_nse_style_db(csv_path: Path, db_path: Path, *, label: str) -> int:
    """Rebuild NSE.db / SME.db from SYMBOL + SUBSECTOR CSV (industry = subsector)."""
    if not csv_path.is_file():
        raise FileNotFoundError(f"{label} CSV not found: {csv_path}")

    df = pd.read_csv(csv_path, on_bad_lines="skip", engine="python")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            nse_code TEXT,
            sector TEXT,
            industry TEXT,
            subsector TEXT,
            market_cap REAL
        )
        """
    )
    for col in ("company_name", "nse_code", "sector", "industry", "subsector", "market_cap"):
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{col} ON stocks({col})")

    inserted = 0
    for _, row in df.iterrows():
        name = ""
        if "NAME OF COMPANY" in df.columns and pd.notna(row.get("NAME OF COMPANY")):
            name = str(row["NAME OF COMPANY"]).strip()
        elif "Company Name" in df.columns and pd.notna(row.get("Company Name")):
            name = str(row["Company Name"]).strip()
        if not name or name.startswith("0"):
            continue

        symbol = ""
        if "SYMBOL" in df.columns and pd.notna(row.get("SYMBOL")):
            symbol = str(row["SYMBOL"]).strip().upper()
        elif "NSE Code" in df.columns and pd.notna(row.get("NSE Code")):
            symbol = str(row["NSE Code"]).strip().upper()
        if not symbol:
            continue

        sub = ""
        if "SUBSECTOR" in df.columns and pd.notna(row.get("SUBSECTOR")):
            sub = str(row["SUBSECTOR"]).strip()
        elif "Subsector" in df.columns and pd.notna(row.get("Subsector")):
            sub = str(row["Subsector"]).strip()

        sector = ""
        industry = sub  # NSE/SME CSV fine tag lives in SUBSECTOR
        if "Sector" in df.columns and pd.notna(row.get("Sector")):
            sector = str(row["Sector"]).strip()
        if "Industry" in df.columns and pd.notna(row.get("Industry")):
            industry = str(row["Industry"]).strip() or industry

        mcap = 0.0
        if "MARKET CAP" in df.columns:
            mcap = _clean_mcap(row.get("MARKET CAP"))
        elif "Market Cap (Cr)" in df.columns:
            mcap = _clean_mcap(row.get("Market Cap (Cr)"))

        cur.execute(
            """
            INSERT INTO stocks (company_name, nse_code, sector, industry, subsector, market_cap)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, symbol, sector, industry, sub or industry, mcap),
        )
        inserted += 1

    conn.commit()
    conn.close()
    print(f"  {label}: wrote {inserted:,} rows → {db_path}")
    return inserted


def _fill_empty_industry_from_subsector(db_path: Path) -> int:
    if not db_path.is_file():
        return 0
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cols = {r[1] for r in cur.execute("PRAGMA table_info(stocks)")}
    if "industry" not in cols or "subsector" not in cols:
        conn.close()
        return 0
    cur.execute(
        """
        UPDATE stocks
        SET industry = subsector
        WHERE (industry IS NULL OR trim(industry) = '')
          AND subsector IS NOT NULL AND trim(subsector) <> ''
        """
    )
    n = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0
    conn.commit()
    conn.close()
    return int(n)


def _apply_overrides_to_db(db_path: Path, *, db_kind: str) -> int:
    """
    Patch classification overrides into a sqlite DB.

    db_kind: NSE | SME | BSE — used to honor optional market filters on overrides.
    """
    if not db_path.is_file():
        return 0
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cols = {r[1] for r in cur.execute("PRAGMA table_info(stocks)")}
    if "nse_code" not in cols:
        conn.close()
        return 0

    updated = 0
    for rule in classification_overrides():
        ticker = safe_str(rule.get("ticker")).upper()
        if not ticker:
            continue
        market = safe_str(rule.get("market")).upper()
        if market == "NSE" and db_kind == "BSE":
            continue
        if market == "BSE" and db_kind in {"NSE", "SME"}:
            continue
        if market == "NSE SME" and db_kind != "SME":
            continue

        industry = safe_str(rule.get("industry") or rule.get("sub_sector"))
        sub = safe_str(rule.get("sub_sector") or rule.get("industry"))
        sector = safe_str(rule.get("sector"))
        name_contains = safe_str(rule.get("name_contains"))

        where = "UPPER(TRIM(nse_code)) = ?"
        params: list = [ticker]
        if name_contains:
            where += " AND company_name LIKE ?"
            params.append(f"%{name_contains}%")

        sets = []
        values: list = []
        if industry and "industry" in cols:
            sets.append("industry = ?")
            values.append(industry)
        if sub and "subsector" in cols:
            sets.append("subsector = ?")
            values.append(sub)
        if sector and "sector" in cols:
            sets.append("sector = ?")
            values.append(sector)
        if not sets:
            continue

        sql = f"UPDATE stocks SET {', '.join(sets)} WHERE {where}"
        cur.execute(sql, (*values, *params))
        if cur.rowcount and cur.rowcount > 0:
            updated += int(cur.rowcount)

    conn.commit()
    conn.close()
    return updated


def refresh(
    *,
    rebuild_sqlite: bool = True,
    refresh_listings_csv: bool = False,
) -> Path:
    sqlite_dir = Path(STOCK_ANALYSIS_SQLITE_DIR)
    data_dir = _data_dir()
    print(f"sqlite dir: {sqlite_dir}")
    print(f"data dir:   {data_dir}")

    if rebuild_sqlite:
        print("\n1) Rebuild NSE.db / SME.db from CSVs")
        _build_nse_style_db(data_dir / "NSE.csv", sqlite_dir / "NSE.db", label="NSE")
        _build_nse_style_db(data_dir / "SME_NSE.csv", sqlite_dir / "SME.db", label="SME")

        bse_path = sqlite_dir / "BSE.db"
        filled = _fill_empty_industry_from_subsector(bse_path)
        if filled:
            print(f"  BSE: filled industry from subsector on {filled:,} rows")

        print("\n2) Apply classification overrides into sqlite")
        for name, kind in (("NSE.db", "NSE"), ("SME.db", "SME"), ("BSE.db", "BSE")):
            n = _apply_overrides_to_db(sqlite_dir / name, db_kind=kind)
            print(f"  {name}: patched {n} row(s)")

    print("\n3) Re-merge into stocks-ai universe")
    df = rebuild_india_stocks_classification(refresh_csv=refresh_listings_csv)
    cov = classification_coverage(df)
    print(f"  rows={len(df):,} tickers={df['ticker'].nunique():,}")
    print(f"  coverage={cov}")
    return sqlite_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-sqlite-rebuild",
        action="store_true",
        help="Only re-merge stocks-ai (do not rewrite NSE.db/SME.db)",
    )
    parser.add_argument(
        "--refresh-csv",
        action="store_true",
        help="Also re-fetch NSE equity listing CSVs into stocks-ai",
    )
    args = parser.parse_args(argv)
    refresh(
        rebuild_sqlite=not args.skip_sqlite_rebuild,
        refresh_listings_csv=args.refresh_csv,
    )
    print("\ndone")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
