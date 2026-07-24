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


def _require_market(market: str | None) -> str:
    m = safe_str(market).upper() or "NSE"
    if m not in {"NSE", "NSE SME"}:
        raise ValueError("Governance is NSE-only (BSE removed)")
    return m


def purge_bse_governance_data() -> dict[str, int]:
    """
    Delete all BSE companies (cascade seats), orphan directors,
    and scan_log rows for those tickers. Idempotent.
    """
    from stocks.governance.db import _purge_bse_data, get_governance_connection

    init_governance_db()
    with get_governance_connection() as conn:
        return _purge_bse_data(conn)


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
    sector: str | None = None,
    industry: str | None = None,
    sub_sector: str | None = None,
    replace_seats: bool = True,
    protect_din_board: bool = True,
) -> dict[str, object]:
    """
    Upsert one listed company and its board.

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
    market = _require_market(market)

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

    classif = _lookup_company_classification(ticker_key, market)
    sector_v = safe_str(sector) or classif.get("sector") or None
    industry_v = safe_str(industry) or classif.get("industry") or None
    sub_sector_v = safe_str(sub_sector) or classif.get("sub_sector") or None

    now = _utc_now()
    with get_governance_connection() as conn:
        conn.execute(
            """
            INSERT INTO companies (
                ticker, market, name, cin, isin, notes,
                sector, industry, sub_sector, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                market=excluded.market,
                name=excluded.name,
                cin=COALESCE(NULLIF(excluded.cin, ''), companies.cin),
                isin=COALESCE(NULLIF(excluded.isin, ''), companies.isin),
                notes=COALESCE(NULLIF(excluded.notes, ''), companies.notes),
                sector=COALESCE(NULLIF(excluded.sector, ''), companies.sector),
                industry=COALESCE(NULLIF(excluded.industry, ''), companies.industry),
                sub_sector=COALESCE(
                    NULLIF(excluded.sub_sector, ''), companies.sub_sector
                ),
                updated_at=excluded.updated_at
            """,
            (
                ticker_key,
                market,
                company_name,
                safe_str(cin) or None,
                safe_str(isin) or None,
                safe_str(notes) or None,
                sector_v,
                industry_v,
                sub_sector_v,
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


def _lookup_company_classification(ticker: str, market: str = "NSE") -> dict[str, str]:
    """Best-effort sector / industry / sub_sector from listings classification."""
    try:
        from stocks.listings.classification_service import lookup_classification

        sector, industry, subsector = lookup_classification(ticker, market=market)
        return {
            "sector": safe_str(sector),
            "industry": safe_str(industry),
            "sub_sector": safe_str(subsector),
        }
    except Exception:
        return {"sector": "", "industry": "", "sub_sector": ""}


def enrich_governance_company_classification(
    *,
    only_missing: bool = True,
) -> int:
    """Backfill sector / industry / sub_sector on governance companies. Returns updated count."""
    init_governance_db()
    try:
        from stocks.listings.classification_service import (
            load_classification_maps,
            lookup_classification,
        )

        maps = load_classification_maps()
    except Exception:
        maps = None

    index_industry: dict[str, str] = {}
    try:
        from stocks.core.database import get_connection, init_db

        init_db()
        with get_connection() as conn:
            for r in conn.execute(
                """
                SELECT ticker, industry FROM index_constituents
                WHERE industry IS NOT NULL AND TRIM(industry) != ''
                """
            ).fetchall():
                t = safe_str(r["ticker"]).upper()
                if t and t not in index_industry:
                    index_industry[t] = safe_str(r["industry"])
    except Exception:
        index_industry = {}

    with get_governance_connection() as conn:
        rows = conn.execute(
            """
            SELECT ticker, market, sector, industry, sub_sector
            FROM companies
            """
        ).fetchall()
    updated = 0
    now = _utc_now()
    with get_governance_connection() as conn:
        for row in rows:
            ticker = safe_str(row["ticker"]).upper()
            if not ticker:
                continue
            has_all = all(
                safe_str(row[c]) for c in ("sector", "industry", "sub_sector")
            )
            if only_missing and has_all:
                continue
            if maps is not None:
                sector, industry, subsector = lookup_classification(
                    ticker,
                    maps=maps,
                    market=safe_str(row["market"]).upper() or "NSE",
                )
                classif = {
                    "sector": safe_str(sector),
                    "industry": safe_str(industry),
                    "sub_sector": safe_str(subsector),
                }
            else:
                classif = _lookup_company_classification(
                    ticker, safe_str(row["market"]).upper() or "NSE"
                )
            nse_ind = index_industry.get(ticker, "")
            # Prefer listings sector; fall back to NSE index Industry for reporting.
            sector = (
                classif["sector"]
                or safe_str(row["sector"])
                or nse_ind
                or classif["industry"]
                or safe_str(row["industry"])
                or None
            )
            industry = (
                classif["industry"]
                or safe_str(row["industry"])
                or nse_ind
                or None
            )
            sub_sector = (
                classif["sub_sector"]
                or safe_str(row["sub_sector"])
                or None
            )
            if not any((sector, industry, sub_sector)):
                continue
            if (
                safe_str(row["sector"]) == safe_str(sector)
                and safe_str(row["industry"]) == safe_str(industry)
                and safe_str(row["sub_sector"]) == safe_str(sub_sector)
            ):
                continue
            conn.execute(
                """
                UPDATE companies
                SET sector = COALESCE(NULLIF(?, ''), sector),
                    industry = COALESCE(NULLIF(?, ''), industry),
                    sub_sector = COALESCE(NULLIF(?, ''), sub_sector),
                    updated_at = ?
                WHERE ticker = ?
                """,
                (sector, industry, sub_sector, now, ticker),
            )
            updated += 1
    return updated


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
            sector=board.get("sector"),
            industry=board.get("industry"),
            sub_sector=board.get("sub_sector"),
            seats=list(board.get("seats") or []),
            replace_seats=True,
            protect_din_board=False,
        )
        saved += 1
    if saved:
        enrich_governance_company_classification(only_missing=True)
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
        scanned = conn.execute("SELECT COUNT(*) FROM scan_log").fetchone()[0]
    return {
        "companies": int(companies),
        "directors": int(directors),
        "seats": int(seats),
        "multi_board_directors": int(multi),
        "directors_with_din": int(with_din),
        "scan_attempted": int(scanned),
    }


def record_scan_attempt(
    ticker: str,
    status: str,
    *,
    detail: str | None = None,
) -> None:
    """Remember a ticker was attempted so auto-batches can skip it."""
    init_governance_db()
    key = safe_str(ticker).upper()
    if not key:
        return
    with get_governance_connection() as conn:
        conn.execute(
            """
            INSERT INTO scan_log (ticker, status, detail, fetched_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                status=excluded.status,
                detail=excluded.detail,
                fetched_at=excluded.fetched_at
            """,
            (key, safe_str(status) or "failed", safe_str(detail) or None, _utc_now()),
        )


def scanned_ticker_set() -> set[str]:
    init_governance_db()
    with get_governance_connection() as conn:
        rows = conn.execute("SELECT ticker FROM scan_log").fetchall()
    return {safe_str(r[0]).upper() for r in rows if safe_str(r[0])}


def clear_scan_log(*, only_empty_failed: bool = False) -> int:
    """Clear scan attempts. If only_empty_failed, keep successful saves."""
    init_governance_db()
    with get_governance_connection() as conn:
        if only_empty_failed:
            cur = conn.execute(
                "DELETE FROM scan_log WHERE status IN ('empty', 'failed')"
            )
        else:
            cur = conn.execute("DELETE FROM scan_log")
        return int(cur.rowcount or 0)


def clear_all_governance_data() -> dict[str, int]:
    """Wipe companies, directors, board seats, and scan log — fresh start."""
    init_governance_db()
    with get_governance_connection() as conn:
        seats = conn.execute("SELECT COUNT(*) FROM board_seats").fetchone()[0]
        directors = conn.execute("SELECT COUNT(*) FROM directors").fetchone()[0]
        companies = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        scans = conn.execute("SELECT COUNT(*) FROM scan_log").fetchone()[0]
        conn.execute("DELETE FROM board_seats")
        conn.execute("DELETE FROM directors")
        conn.execute("DELETE FROM companies")
        conn.execute("DELETE FROM scan_log")
    return {
        "companies": int(companies),
        "directors": int(directors),
        "seats": int(seats),
        "scan_log": int(scans),
    }


def clear_scan_log_for_tickers(
    tickers: list[str],
    *,
    only_empty_failed: bool = True,
) -> int:
    """Clear scan_log rows for specific tickers (so they can be retried)."""
    keys = sorted({safe_str(t).upper() for t in tickers if safe_str(t)})
    if not keys:
        return 0
    init_governance_db()
    placeholders = ",".join("?" * len(keys))
    with get_governance_connection() as conn:
        if only_empty_failed:
            cur = conn.execute(
                f"""
                DELETE FROM scan_log
                WHERE ticker IN ({placeholders})
                  AND status IN ('empty', 'failed')
                """,
                keys,
            )
        else:
            cur = conn.execute(
                f"DELETE FROM scan_log WHERE ticker IN ({placeholders})",
                keys,
            )
        return int(cur.rowcount or 0)


def holdings_governance_coverage() -> dict[str, object]:
    """Coverage of portfolio holdings in governance.db boards."""
    from stocks.shared.portfolio import load_holdings

    init_governance_db()
    holdings = load_holdings(seed_if_empty=True)
    if holdings.empty or "ticker" not in holdings.columns:
        return {
            "total": 0,
            "with_board": 0,
            "missing": [],
            "empty_scan": [],
        }

    tickers = sorted(
        {safe_str(t).upper() for t in holdings["ticker"].tolist() if safe_str(t)}
    )
    with get_governance_connection() as conn:
        seat_rows = conn.execute(
            """
            SELECT ticker, COUNT(*) AS n
            FROM board_seats
            GROUP BY ticker
            """
        ).fetchall()
        scan_rows = conn.execute(
            "SELECT ticker, status FROM scan_log"
        ).fetchall()
    seats = {
        safe_str(r[0]).upper(): int(r[1] or 0)
        for r in seat_rows
        if safe_str(r[0])
    }
    scan_status = {
        safe_str(r[0]).upper(): safe_str(r[1])
        for r in scan_rows
        if safe_str(r[0])
    }
    missing = [t for t in tickers if seats.get(t, 0) <= 0]
    empty_scan = [
        t for t in missing if scan_status.get(t) in ("empty", "failed")
    ]
    return {
        "total": len(tickers),
        "with_board": len(tickers) - len(missing),
        "missing": missing,
        "empty_scan": empty_scan,
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
                c.sector,
                c.industry,
                c.sub_sector,
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
                c.market,
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
