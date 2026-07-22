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


def init_governance_db() -> None:
    """
    Schema:

    - companies — NSE tickers with stored boards
    - directors — people keyed by ``person_id`` (DIN when known, else ``n:<name_key>``)
    - board_seats — one row per (ticker, person_id)
    """
    with get_governance_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS companies (
                ticker TEXT PRIMARY KEY,
                market TEXT NOT NULL DEFAULT 'NSE'
                    CHECK (market = 'NSE'),
                name TEXT NOT NULL,
                cin TEXT,
                isin TEXT,
                notes TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_gov_companies_cin
                ON companies(cin)
                WHERE cin IS NOT NULL AND TRIM(cin) != '';
            """
        )
        _migrate_to_person_id(conn)
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
            """
        )
