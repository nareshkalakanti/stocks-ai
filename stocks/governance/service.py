"""Governance service — person_id directors, NSE boards, shared-seat lookup."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from stocks.core.text_utils import safe_str
from stocks.governance.db import _utc_now, get_governance_connection, init_governance_db
from stocks.governance.seed import CURATED_BOARDS


def _norm_din(raw: str | None) -> str:
    digits = re.sub(r"\D", "", safe_str(raw))
    if not digits:
        return ""
    return digits.zfill(8)[-8:]


def _name_key(name: str) -> str:
    text = safe_str(name).lower()
    text = re.sub(r"\b(mr|mrs|ms|dr|shri|smt)\.?\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def person_id_for(*, din: str | None = None, name: str | None = None) -> str:
    """Canonical person key: DIN when present, else stable name key."""
    din_key = _norm_din(din)
    if din_key and len(din_key) == 8:
        return din_key
    key = _name_key(name or "")
    if not key:
        raise ValueError("Director needs a DIN or a name")
    return f"n:{key}"


def _require_nse(market: str | None) -> str:
    m = safe_str(market).upper() or "NSE"
    if m != "NSE":
        raise ValueError("Governance DB is NSE-only")
    return "NSE"


def _infer_category(designation: str) -> str:
    text = designation.lower()
    if "independent" in text:
        return "Independent"
    if any(x in text for x in ("managing", "executive", "whole-time", "whole time", "ceo", "cfo", "cto")):
        return "Executive"
    if "non-executive" in text or "non executive" in text:
        return "Non-Executive"
    return ""


def ticker_has_din_board(ticker: str) -> bool:
    init_governance_db()
    key = safe_str(ticker).upper()
    with get_governance_connection() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM board_seats s
            JOIN directors d ON d.person_id = s.person_id
            WHERE s.ticker = ? AND d.din IS NOT NULL AND TRIM(d.din) != ''
            LIMIT 1
            """,
            (key,),
        ).fetchone()
    return row is not None


def save_company_board(
    *,
    ticker: str,
    name: str,
    seats: list[dict[str, Any]],
    cin: str | None = None,
    isin: str | None = None,
    notes: str | None = None,
    market: str = "NSE",
    replace_seats: bool = True,
    protect_din_board: bool = True,
) -> dict[str, object]:
    """
    Upsert one NSE company and its board.

    Each seat needs ``name`` + ``designation``. ``din`` is preferred (best match key);
    without DIN we store ``person_id = n:<normalized name>``.
    """
    init_governance_db()
    ticker_key = safe_str(ticker).upper()
    if not ticker_key:
        raise ValueError("ticker required")
    company_name = safe_str(name)
    if not company_name:
        raise ValueError("company name required")
    market = _require_nse(market)

    clean_seats: list[dict[str, str]] = []
    for raw in seats:
        person = safe_str(raw.get("name"))
        designation = safe_str(raw.get("designation"))
        din = _norm_din(raw.get("din"))
        if din and len(din) != 8:
            raise ValueError(f"Invalid DIN for {person or '?'}: {raw.get('din')!r}")
        if not person:
            raise ValueError("Director name required")
        if not designation:
            raise ValueError(f"Designation required for {person}")
        pid = person_id_for(din=din or None, name=person)
        category = safe_str(raw.get("category")) or _infer_category(designation)
        clean_seats.append(
            {
                "person_id": pid,
                "din": din,
                "name": person,
                "designation": designation,
                "category": category,
                "source": safe_str(raw.get("source")) or "manual",
                "as_of": safe_str(raw.get("as_of")) or "",
            }
        )

    if not clean_seats:
        raise ValueError("At least one director seat required")

    new_has_din = any(s["din"] for s in clean_seats)
    if protect_din_board and not new_has_din and ticker_has_din_board(ticker_key):
        return {
            "ticker": ticker_key,
            "seats": 0,
            "skipped": True,
            "reason": "Kept curated DIN board (scan had no DINs)",
        }

    now = _utc_now()
    with get_governance_connection() as conn:
        conn.execute(
            """
            INSERT INTO companies (ticker, market, name, cin, isin, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                market=excluded.market,
                name=excluded.name,
                cin=COALESCE(NULLIF(excluded.cin, ''), companies.cin),
                isin=COALESCE(NULLIF(excluded.isin, ''), companies.isin),
                notes=COALESCE(NULLIF(excluded.notes, ''), companies.notes),
                updated_at=excluded.updated_at
            """,
            (
                ticker_key,
                market,
                company_name,
                safe_str(cin) or None,
                safe_str(isin) or None,
                safe_str(notes) or None,
                now,
            ),
        )
        if replace_seats:
            conn.execute("DELETE FROM board_seats WHERE ticker = ?", (ticker_key,))

        for seat in clean_seats:
            conn.execute(
                """
                INSERT INTO directors (person_id, din, name, name_key, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(person_id) DO UPDATE SET
                    din=COALESCE(NULLIF(excluded.din, ''), directors.din),
                    name=excluded.name,
                    name_key=excluded.name_key,
                    updated_at=excluded.updated_at
                """,
                (
                    seat["person_id"],
                    seat["din"] or None,
                    seat["name"],
                    _name_key(seat["name"]),
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO board_seats (
                    ticker, person_id, designation, category, source, as_of, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, person_id) DO UPDATE SET
                    designation=excluded.designation,
                    category=excluded.category,
                    source=excluded.source,
                    as_of=excluded.as_of,
                    fetched_at=excluded.fetched_at
                """,
                (
                    ticker_key,
                    seat["person_id"],
                    seat["designation"],
                    seat["category"] or None,
                    seat["source"],
                    seat["as_of"] or None,
                    now,
                ),
            )

    return {"ticker": ticker_key, "seats": len(clean_seats), "skipped": False}


def seed_curated_boards(*, force: bool = False) -> int:
    init_governance_db()
    existing = set(companies_with_boards()["ticker"].astype(str).str.upper()) if not force else set()
    saved = 0
    for board in CURATED_BOARDS:
        ticker = safe_str(board.get("ticker")).upper()
        if not force and ticker in existing:
            continue
        save_company_board(
            ticker=ticker,
            name=board["name"],
            cin=board.get("cin"),
            isin=board.get("isin"),
            notes=board.get("notes"),
            seats=list(board.get("seats") or []),
            replace_seats=True,
            protect_din_board=False,
        )
        saved += 1
    return saved


def governance_stats() -> dict[str, int]:
    init_governance_db()
    with get_governance_connection() as conn:
        companies = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        directors = conn.execute("SELECT COUNT(*) FROM directors").fetchone()[0]
        seats = conn.execute("SELECT COUNT(*) FROM board_seats").fetchone()[0]
        multi = conn.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT person_id FROM board_seats
                GROUP BY person_id HAVING COUNT(DISTINCT ticker) >= 2
            )
            """
        ).fetchone()[0]
        with_din = conn.execute(
            "SELECT COUNT(*) FROM directors WHERE din IS NOT NULL AND TRIM(din) != ''"
        ).fetchone()[0]
    return {
        "companies": int(companies),
        "directors": int(directors),
        "seats": int(seats),
        "multi_board_directors": int(multi),
        "directors_with_din": int(with_din),
    }


def companies_with_boards() -> pd.DataFrame:
    init_governance_db()
    with get_governance_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                c.ticker,
                c.market,
                c.name,
                c.cin,
                c.isin,
                c.notes,
                c.updated_at,
                COUNT(s.id) AS director_count
            FROM companies c
            LEFT JOIN board_seats s ON s.ticker = c.ticker
            GROUP BY c.ticker
            ORDER BY c.name COLLATE NOCASE
            """
        ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def directors_for_ticker(ticker: str) -> pd.DataFrame:
    init_governance_db()
    key = safe_str(ticker).upper()
    with get_governance_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                s.ticker,
                d.person_id,
                d.din,
                d.name,
                s.designation,
                s.category,
                s.source,
                s.as_of,
                (
                    SELECT COUNT(DISTINCT s2.ticker)
                    FROM board_seats s2
                    WHERE s2.person_id = d.person_id
                ) AS board_count
            FROM board_seats s
            JOIN directors d ON d.person_id = s.person_id
            WHERE s.ticker = ?
            ORDER BY
                CASE
                    WHEN LOWER(s.designation) LIKE '%chair%' THEN 0
                    WHEN LOWER(s.designation) LIKE '%managing%' THEN 1
                    WHEN LOWER(s.category) LIKE '%independent%' THEN 3
                    ELSE 2
                END,
                d.name COLLATE NOCASE
            """,
            (key,),
        ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def seats_for_person(person_id: str) -> pd.DataFrame:
    init_governance_db()
    pid = safe_str(person_id)
    if not pid:
        return pd.DataFrame()
    with get_governance_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                d.person_id,
                d.din,
                d.name AS director_name,
                s.ticker,
                c.name AS company_name,
                s.designation,
                s.category,
                s.source,
                s.as_of
            FROM board_seats s
            JOIN directors d ON d.person_id = s.person_id
            JOIN companies c ON c.ticker = s.ticker
            WHERE d.person_id = ?
            ORDER BY c.name COLLATE NOCASE
            """,
            (pid,),
        ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def seats_for_din(din: str) -> pd.DataFrame:
    """Compatibility helper — resolve DIN to person_id then list seats."""
    din_key = _norm_din(din)
    if not din_key:
        return pd.DataFrame()
    return seats_for_person(din_key)


def multi_board_directors(*, min_boards: int = 2) -> pd.DataFrame:
    init_governance_db()
    min_boards = max(2, int(min_boards))
    with get_governance_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                d.person_id,
                d.din,
                d.name,
                COUNT(DISTINCT s.ticker) AS board_count,
                GROUP_CONCAT(s.ticker, ', ') AS tickers
            FROM directors d
            JOIN board_seats s ON s.person_id = d.person_id
            GROUP BY d.person_id
            HAVING COUNT(DISTINCT s.ticker) >= ?
            ORDER BY board_count DESC, d.name COLLATE NOCASE
            """,
            (min_boards,),
        ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def overlaps_for_ticker(ticker: str) -> pd.DataFrame:
    board = directors_for_ticker(ticker)
    if board.empty:
        return pd.DataFrame()
    multi = board[board["board_count"] >= 2].copy()
    if multi.empty:
        return multi
    rows: list[dict] = []
    for _, row in multi.iterrows():
        seats = seats_for_person(str(row["person_id"]))
        others = seats[seats["ticker"].astype(str).str.upper() != safe_str(ticker).upper()]
        for _, seat in others.iterrows():
            rows.append(
                {
                    "person_id": row["person_id"],
                    "din": row.get("din"),
                    "director": row["name"],
                    "here_as": row["designation"],
                    "also_ticker": seat["ticker"],
                    "also_company": seat["company_name"],
                    "also_as": seat["designation"],
                }
            )
    return pd.DataFrame(rows)
