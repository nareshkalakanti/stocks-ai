"""Separate SQLite DB for NSE board / director data (quality over quantity)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from stocks.core.config import DATA_DIR, GOVERNANCE_DB_PATH


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_governance_connection():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(GOVERNANCE_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r[1]) for r in rows}


def _migrate_to_person_id(conn: sqlite3.Connection) -> None:
    """Upgrade early DIN-only schema → person_id (DIN or name key)."""
    cols = _table_columns(conn, "directors")
    if not cols or "person_id" in cols:
        return
    conn.executescript(
        """
        PRAGMA foreign_keys = OFF;
        ALTER TABLE directors RENAME TO directors_legacy;
        ALTER TABLE board_seats RENAME TO board_seats_legacy;

        CREATE TABLE directors (
            person_id TEXT PRIMARY KEY,
            din TEXT UNIQUE,
            name TEXT NOT NULL,
            name_key TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_gov_directors_name_key
            ON directors(name_key);
        CREATE INDEX IF NOT EXISTS idx_gov_directors_din
            ON directors(din);

        CREATE TABLE board_seats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL REFERENCES companies(ticker) ON DELETE CASCADE,
            person_id TEXT NOT NULL REFERENCES directors(person_id) ON DELETE CASCADE,
            designation TEXT NOT NULL,
            category TEXT,
            source TEXT NOT NULL,
            as_of TEXT,
            fetched_at TEXT NOT NULL,
            UNIQUE (ticker, person_id)
        );
        CREATE INDEX IF NOT EXISTS idx_gov_seats_person ON board_seats(person_id);
        CREATE INDEX IF NOT EXISTS idx_gov_seats_ticker ON board_seats(ticker);

        INSERT INTO directors (person_id, din, name, name_key, updated_at)
        SELECT din, din, name, name_key, updated_at FROM directors_legacy;

        INSERT INTO board_seats (
            ticker, person_id, designation, category, source, as_of, fetched_at
        )
        SELECT ticker, din, designation, category, source, as_of, fetched_at
        FROM board_seats_legacy;

        DROP TABLE board_seats_legacy;
        DROP TABLE directors_legacy;
        PRAGMA foreign_keys = ON;
        """
    )


def _board_seats_create_sql() -> str:
    return """
        CREATE TABLE board_seats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL REFERENCES companies(ticker) ON DELETE CASCADE,
            person_id TEXT NOT NULL REFERENCES directors(person_id) ON DELETE CASCADE,
            designation TEXT NOT NULL,
            category TEXT,
            source TEXT NOT NULL,
            as_of TEXT,
            fetched_at TEXT NOT NULL,
            UNIQUE (ticker, person_id)
        );
        CREATE INDEX IF NOT EXISTS idx_gov_seats_person ON board_seats(person_id);
        CREATE INDEX IF NOT EXISTS idx_gov_seats_ticker ON board_seats(ticker);
    """


def _rebuild_board_seats(conn: sqlite3.Connection) -> None:
    """Recreate board_seats so FKs point at companies (not a rename leftover)."""
    conn.executescript(
        """
        PRAGMA foreign_keys = OFF;
        ALTER TABLE board_seats RENAME TO board_seats_fk_fix;
        """
    )
    conn.executescript(_board_seats_create_sql())
    conn.executescript(
        """
        INSERT INTO board_seats (
            ticker, person_id, designation, category, source, as_of, fetched_at
        )
        SELECT ticker, person_id, designation, category, source, as_of, fetched_at
        FROM board_seats_fk_fix;
        DROP TABLE board_seats_fk_fix;
        PRAGMA foreign_keys = ON;
        """
    )


def _repair_board_seats_fk(conn: sqlite3.Connection) -> None:
    """Fix FKs left pointing at companies_market_mig after an earlier market migrate."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='board_seats'"
    ).fetchone()
    sql = str(row[0] or "") if row else ""
    if "companies_market_mig" not in sql:
        return
    _rebuild_board_seats(conn)


def _migrate_market_check(conn: sqlite3.Connection) -> None:
    """Allow NSE + BSE (older DBs had CHECK market = 'NSE' only).

    Renaming ``companies`` updates FK targets on ``board_seats``, so we rebuild
    seats afterward to point at the new ``companies`` table.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='companies'"
    ).fetchone()
    sql = str(row[0] or "") if row else ""
    if not sql or "IN ('NSE', 'BSE')" in sql or "NSE SME" in sql:
        return
    if "CHECK (market = 'NSE')" not in sql and 'CHECK (market = "NSE")' not in sql:
        return
    conn.executescript(
        """
        PRAGMA foreign_keys = OFF;
        ALTER TABLE companies RENAME TO companies_market_mig;
        CREATE TABLE companies (
            ticker TEXT PRIMARY KEY,
            market TEXT NOT NULL DEFAULT 'NSE'
                CHECK (market IN ('NSE', 'NSE SME', 'BSE')),
            name TEXT NOT NULL,
            cin TEXT,
            isin TEXT,
            notes TEXT,
            sector TEXT,
            industry TEXT,
            sub_sector TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_gov_companies_cin
            ON companies(cin)
            WHERE cin IS NOT NULL AND TRIM(cin) != '';
        INSERT INTO companies (
            ticker, market, name, cin, isin, notes, updated_at
        )
        SELECT ticker,
               CASE WHEN UPPER(COALESCE(market, 'NSE')) = 'BSE' THEN 'BSE' ELSE 'NSE' END,
               name, cin, isin, notes, updated_at
        FROM companies_market_mig;
        DROP TABLE companies_market_mig;
        PRAGMA foreign_keys = ON;
        """
    )
    if _table_columns(conn, "board_seats"):
        _rebuild_board_seats(conn)


def _migrate_sme_market_check(conn: sqlite3.Connection) -> None:
    """Allow ``NSE SME`` alongside NSE (and legacy BSE) in companies.market CHECK."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='companies'"
    ).fetchone()
    sql = str(row[0] or "") if row else ""
    if not sql or "NSE SME" in sql:
        return
    if "IN ('NSE', 'BSE')" not in sql and 'IN ("NSE", "BSE")' not in sql:
        return

    cols = _table_columns(conn, "companies")
    extra = [c for c in ("sector", "industry", "sub_sector") if c in cols]
    extra_cols = (", " + ", ".join(extra)) if extra else ""
    extra_select = (", " + ", ".join(extra)) if extra else ""

    conn.executescript(
        f"""
        PRAGMA foreign_keys = OFF;
        ALTER TABLE companies RENAME TO companies_sme_mig;
        CREATE TABLE companies (
            ticker TEXT PRIMARY KEY,
            market TEXT NOT NULL DEFAULT 'NSE'
                CHECK (market IN ('NSE', 'NSE SME', 'BSE')),
            name TEXT NOT NULL,
            cin TEXT,
            isin TEXT,
            notes TEXT,
            sector TEXT,
            industry TEXT,
            sub_sector TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_gov_companies_cin
            ON companies(cin)
            WHERE cin IS NOT NULL AND TRIM(cin) != '';
        INSERT INTO companies (
            ticker, market, name, cin, isin, notes{extra_cols}, updated_at
        )
        SELECT ticker, market, name, cin, isin, notes{extra_select}, updated_at
        FROM companies_sme_mig;
        DROP TABLE companies_sme_mig;
        PRAGMA foreign_keys = ON;
        """
    )
    if _table_columns(conn, "board_seats"):
        _rebuild_board_seats(conn)


def _ensure_company_classification_columns(conn: sqlite3.Connection) -> None:
    cols = _table_columns(conn, "companies")
    if not cols:
        return
    for col in ("sector", "industry", "sub_sector"):
        if col not in cols:
            conn.execute(f"ALTER TABLE companies ADD COLUMN {col} TEXT")


def _purge_bse_data(conn: sqlite3.Connection) -> dict[str, int]:
    """Remove BSE companies (cascade seats), orphan directors, and their scan_log rows."""
    bse_tickers = [
        str(r[0]).upper()
        for r in conn.execute(
            "SELECT ticker FROM companies WHERE UPPER(market) = 'BSE'"
        ).fetchall()
        if r[0]
    ]
    seats_before = conn.execute("SELECT COUNT(*) FROM board_seats").fetchone()[0]
    companies_deleted = 0
    if bse_tickers:
        conn.execute("DELETE FROM companies WHERE UPPER(market) = 'BSE'")
        companies_deleted = len(bse_tickers)
        placeholders = ",".join("?" * len(bse_tickers))
        conn.execute(
            f"DELETE FROM scan_log WHERE ticker IN ({placeholders})",
            bse_tickers,
        )
    seats_after = conn.execute("SELECT COUNT(*) FROM board_seats").fetchone()[0]
    orphan = conn.execute(
        """
        DELETE FROM directors
        WHERE person_id NOT IN (SELECT DISTINCT person_id FROM board_seats)
        """
    )
    return {
        "companies_deleted": companies_deleted,
        "seats_deleted": max(0, int(seats_before) - int(seats_after)),
        "directors_deleted": int(orphan.rowcount or 0),
    }


def init_governance_db() -> None:
    """
    Schema:

    - companies — NSE tickers with stored boards (BSE purged)
    - directors — people keyed by ``person_id`` (DIN when known, else ``n:<name_key>``)
    - board_seats — one row per (ticker, person_id)
    """
    with get_governance_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS companies (
                ticker TEXT PRIMARY KEY,
                market TEXT NOT NULL DEFAULT 'NSE'
                    CHECK (market IN ('NSE', 'NSE SME', 'BSE')),
                name TEXT NOT NULL,
                cin TEXT,
                isin TEXT,
                notes TEXT,
                sector TEXT,
                industry TEXT,
                sub_sector TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_gov_companies_cin
                ON companies(cin)
                WHERE cin IS NOT NULL AND TRIM(cin) != '';
            """
        )
        _migrate_to_person_id(conn)
        _migrate_market_check(conn)
        _migrate_sme_market_check(conn)
        _ensure_company_classification_columns(conn)
        _repair_board_seats_fk(conn)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS directors (
                person_id TEXT PRIMARY KEY,
                din TEXT UNIQUE,
                name TEXT NOT NULL,
                name_key TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_gov_directors_name_key
                ON directors(name_key);
            CREATE INDEX IF NOT EXISTS idx_gov_directors_din
                ON directors(din);

            CREATE TABLE IF NOT EXISTS board_seats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL REFERENCES companies(ticker) ON DELETE CASCADE,
                person_id TEXT NOT NULL REFERENCES directors(person_id) ON DELETE CASCADE,
                designation TEXT NOT NULL,
                category TEXT,
                source TEXT NOT NULL,
                as_of TEXT,
                fetched_at TEXT NOT NULL,
                UNIQUE (ticker, person_id)
            );

            CREATE INDEX IF NOT EXISTS idx_gov_seats_person ON board_seats(person_id);
            CREATE INDEX IF NOT EXISTS idx_gov_seats_ticker ON board_seats(ticker);

            CREATE TABLE IF NOT EXISTS scan_log (
                ticker TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                detail TEXT,
                fetched_at TEXT NOT NULL
            );
            """
        )
        _purge_bse_data(conn)
