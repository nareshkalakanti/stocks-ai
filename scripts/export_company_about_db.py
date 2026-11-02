#!/usr/bin/env python3
"""Export NSE + NSE SME About Us / profile rows into a standalone SQLite DB.

Source: data/stocks_ai.db (stocks + company_profile_cache)
Output: data/company_about.db  (default)

Usage:
  python scripts/export_company_about_db.py
  python scripts/export_company_about_db.py --out data/company_about.db
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from stocks.core.config import DATA_DIR, DB_PATH

DEFAULT_OUT = DATA_DIR / "company_about.db"

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS company_about (
    ticker TEXT PRIMARY KEY,
    name TEXT,
    market TEXT NOT NULL,
    website TEXT,
    about TEXT,
    yf_about TEXT,
    scraped_about TEXT,
    company_sector TEXT,
    company_industry TEXT,
    headquarters TEXT,
    employees INTEGER,
    products TEXT,
    end_markets TEXT,
    ir_url TEXT,
    theme_tags TEXT,
    website_status TEXT,
    source TEXT,
    fetched_at TEXT,
    has_website INTEGER NOT NULL DEFAULT 0,
    has_yf_about INTEGER NOT NULL DEFAULT 0,
    has_scraped_about INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_company_about_market ON company_about(market);
CREATE INDEX IF NOT EXISTS idx_company_about_website ON company_about(has_website);
CREATE INDEX IF NOT EXISTS idx_company_about_scraped ON company_about(has_scraped_about);
"""


def _has_text(val: str | None, *, min_len: int = 20) -> int:
    if val is None:
        return 0
    s = str(val).strip()
    return 1 if len(s) >= min_len else 0


def export_company_about_db(
    *,
    source_db: Path = DB_PATH,
    out_path: Path = DEFAULT_OUT,
    markets: tuple[str, ...] = ("NSE", "NSE SME"),
) -> dict:
    """Build a clean About Us SQLite from listings + company_profile_cache."""
    if not source_db.exists():
        raise FileNotFoundError(f"Source DB missing: {source_db}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    src = sqlite3.connect(str(source_db))
    src.row_factory = sqlite3.Row
    dst = sqlite3.connect(str(out_path))
    try:
        dst.executescript(SCHEMA_SQL)

        placeholders = ",".join("?" * len(markets))
        listings = src.execute(
            f"""
            SELECT UPPER(TRIM(ticker)) AS ticker,
                   name,
                   market
            FROM stocks
            WHERE UPPER(TRIM(market)) IN ({placeholders})
            ORDER BY market, ticker
            """,
            tuple(m.upper() for m in markets),
        ).fetchall()

        profiles = {
            str(r["ticker"]).strip().upper(): r
            for r in src.execute(
                """
                SELECT UPPER(TRIM(ticker)) AS ticker,
                       market, website, long_description,
                       company_sector, company_industry, headquarters, employees,
                       source, fetched_at, products, end_markets, ir_url,
                       theme_tags, website_status, yf_about, scraped_about
                FROM company_profile_cache
                """
            ).fetchall()
        }

        rows: list[tuple] = []
        for listing in listings:
            ticker = str(listing["ticker"]).strip().upper()
            if not ticker:
                continue
            p = profiles.get(ticker)
            website = (p["website"] if p else None) or None
            yf_about = (p["yf_about"] if p else None) or None
            scraped = (p["scraped_about"] if p else None) or None
            long_desc = (p["long_description"] if p else None) or None
            about = (scraped or yf_about or long_desc or None)
            if isinstance(website, str):
                website = website.strip() or None
            if isinstance(yf_about, str):
                yf_about = yf_about.strip() or None
            if isinstance(scraped, str):
                scraped = scraped.strip() or None
            if isinstance(about, str):
                about = about.strip() or None

            market = str(listing["market"] or (p["market"] if p else "") or "").strip()
            rows.append(
                (
                    ticker,
                    listing["name"],
                    market,
                    website,
                    about,
                    yf_about,
                    scraped,
                    p["company_sector"] if p else None,
                    p["company_industry"] if p else None,
                    p["headquarters"] if p else None,
                    p["employees"] if p else None,
                    p["products"] if p else None,
                    p["end_markets"] if p else None,
                    p["ir_url"] if p else None,
                    p["theme_tags"] if p else None,
                    p["website_status"] if p else None,
                    p["source"] if p else None,
                    p["fetched_at"] if p else None,
                    1 if website else 0,
                    _has_text(yf_about),
                    _has_text(scraped),
                )
            )

        dst.executemany(
            """
            INSERT INTO company_about (
                ticker, name, market, website, about, yf_about, scraped_about,
                company_sector, company_industry, headquarters, employees,
                products, end_markets, ir_url, theme_tags, website_status,
                source, fetched_at, has_website, has_yf_about, has_scraped_about
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        meta = {
            "created_at": now,
            "source_db": str(source_db),
            "markets": ",".join(markets),
            "row_count": str(len(rows)),
        }
        dst.executemany(
            "INSERT INTO meta(key, value) VALUES (?, ?)",
            list(meta.items()),
        )
        dst.commit()

        # Stats
        stats = {
            "out_path": str(out_path),
            "rows": len(rows),
        }
        for market in markets:
            cur = dst.execute(
                """
                SELECT COUNT(*) AS n,
                       SUM(has_website) AS websites,
                       SUM(has_yf_about) AS yf_about,
                       SUM(has_scraped_about) AS scraped_about,
                       SUM(CASE WHEN about IS NOT NULL AND LENGTH(TRIM(about)) >= 20
                                THEN 1 ELSE 0 END) AS with_about
                FROM company_about
                WHERE UPPER(market) = ?
                """,
                (market.upper(),),
            ).fetchone()
            stats[market] = {
                "n": cur[0],
                "websites": cur[1] or 0,
                "yf_about": cur[2] or 0,
                "scraped_about": cur[3] or 0,
                "with_about": cur[4] or 0,
            }
        return stats
    finally:
        src.close()
        dst.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output SQLite path (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DB_PATH,
        help=f"Source stocks_ai.db (default: {DB_PATH})",
    )
    args = parser.parse_args()
    stats = export_company_about_db(source_db=args.source, out_path=args.out)
    print(f"Wrote {stats['out_path']}")
    print(f"Total rows: {stats['rows']}")
    for market in ("NSE", "NSE SME"):
        s = stats.get(market) or {}
        print(
            f"  {market}: {s.get('n', 0)} · website {s.get('websites', 0)} · "
            f"yf_about {s.get('yf_about', 0)} · scraped {s.get('scraped_about', 0)} · "
            f"about {s.get('with_about', 0)}"
        )


if __name__ == "__main__":
    main()
