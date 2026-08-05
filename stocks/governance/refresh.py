"""Refresh governance.db — CINs (BSE) + optional MCA boards (Apify)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import pandas as pd

from stocks.core.config import GOVERNANCE_DB_PATH
from stocks.core.text_utils import safe_str
from stocks.governance.db import get_governance_connection, init_governance_db
from stocks.governance.service import (
    missing_boards,
    save_company_board,
    ticker_has_din_board,
    upsert_company_cin,
)
from stocks.market.bse_cin import (
    load_bse_code_map,
    resolve_cin_for_ticker,
    save_bse_code_map,
)

_DUMMY_DINS = frozenset({"99999999", "00000000"})


def _norm_din(raw: Any) -> str:
    digits = re.sub(r"\D", "", safe_str(raw))
    if not digits:
        return ""
    return digits.zfill(8)[-8:]


def _load_apify_token() -> str:
    token = safe_str(os.environ.get("APIFY_TOKEN"))
    if token:
        return token
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("APIFY_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def companies_with_cin_missing_din_board() -> pd.DataFrame:
    """Companies that have a CIN stored but no DIN-backed board yet."""
    init_governance_db()
    with get_governance_connection() as conn:
        rows = conn.execute(
            """
            SELECT c.ticker, c.name, c.market, c.cin
            FROM companies c
            WHERE c.cin IS NOT NULL AND TRIM(c.cin) != ''
            ORDER BY c.ticker
            """
        ).fetchall()
    out: list[dict] = []
    for r in rows:
        ticker = safe_str(r["ticker"]).upper()
        if not ticker or ticker_has_din_board(ticker):
            continue
        out.append(
            {
                "ticker": ticker,
                "name": safe_str(r["name"]) or ticker,
                "market": safe_str(r["market"]).upper() or "NSE",
                "cin": safe_str(r["cin"]).upper(),
            }
        )
    return pd.DataFrame(out)


def refresh_missing_cins(*, fetch_screener_codes: bool = True) -> dict[str, int]:
    """
    Resolve BSE → CIN for tickers still missing a DIN board.
    Upserts CIN onto ``companies`` (no seats). Updates ``bse_codes`` in stocks_ai.db.
    """
    init_governance_db()
    miss = missing_boards()
    code_map = load_bse_code_map()
    tried = code_ok = cin_ok = 0
    for row in miss.itertuples(index=False):
        ticker = safe_str(row.ticker).upper()
        if not ticker:
            continue
        tried += 1
        resolved = resolve_cin_for_ticker(
            ticker,
            code_map=code_map,
            fetch_missing_code=fetch_screener_codes,
        )
        code = resolved.get("bse_code")
        cin = resolved.get("cin")
        if code:
            code_ok += 1
            code_map[ticker] = str(code)
        if cin:
            cin_ok += 1
            upsert_company_cin(
                ticker=ticker,
                name=safe_str(row.name) or ticker,
                cin=str(cin),
                market=safe_str(row.market).upper() or "NSE",
            )
    save_bse_code_map(code_map)
    return {
        "missing_boards": len(miss),
        "tried": tried,
        "bse_codes": code_ok,
        "cins_saved": cin_ok,
    }


def _seats_from_foxlabs_item(item: dict) -> list[dict[str, Any]]:
    directors = item.get("directors") or []
    if not isinstance(directors, list):
        return []
    seats: list[dict[str, Any]] = []
    for d in directors:
        if not isinstance(d, dict):
            continue
        name = safe_str(d.get("name") or d.get("directorName"))
        din = _norm_din(d.get("din") or d.get("DIN"))
        if din in _DUMMY_DINS:
            din = ""
        role = safe_str(d.get("designation") or d.get("role") or "Director")
        if not name or not role:
            continue
        seats.append(
            {
                "name": name,
                "din": din or None,
                "designation": role,
                "category": safe_str(d.get("category")) or None,
                "source": "apify_foxlabs_mca",
                "as_of": safe_str(d.get("beginDate") or d.get("tenure") or ""),
            }
        )
    return seats


def refresh_boards_from_apify(
    *,
    max_companies: int | None = None,
    actor_id: str = "foxlabs/indian-company-data",
) -> dict[str, int]:
    """
    Fetch MCA director boards via Apify for companies that already have a CIN
    but no DIN board. Saves seats into governance.db.
    """
    token = _load_apify_token()
    if not token:
        raise RuntimeError("APIFY_TOKEN missing (set in .env or environment)")

    from apify_client import ApifyClient

    need = companies_with_cin_missing_din_board()
    if need.empty:
        return {
            "candidates": 0,
            "fetched": 0,
            "saved": 0,
            "skipped": 0,
            "unmatched": 0,
        }
    if max_companies is not None:
        need = need.head(max(0, int(max_companies)))

    cin_to_meta = {
        safe_str(r.cin).upper(): {
            "ticker": safe_str(r.ticker).upper(),
            "name": safe_str(r.name),
            "market": safe_str(r.market).upper() or "NSE",
        }
        for r in need.itertuples(index=False)
    }
    cins = list(cin_to_meta.keys())
    client = ApifyClient(token)
    run = client.actor(actor_id).call(
        run_input={
            "companyNames": [],
            "cins": cins,
            "companyUrls": [],
            "maxResults": len(cins) + 5,
            "maxConcurrency": 10,
            "proxyConfiguration": {
                "useApifyProxy": True,
                "apifyProxyGroups": [],
            },
        }
    )
    ds_id = getattr(run, "default_dataset_id", None)
    if not ds_id and hasattr(run, "model_dump"):
        ds_id = run.model_dump().get("defaultDatasetId")
    items = list(client.dataset(ds_id).iterate_items())

    saved = skipped = unmatched = 0
    for item in items:
        cin = safe_str(item.get("cin")).upper()
        meta = cin_to_meta.get(cin)
        if not meta:
            unmatched += 1
            continue
        seats = _seats_from_foxlabs_item(item)
        if not any(s.get("din") for s in seats):
            skipped += 1
            continue
        result = save_company_board(
            ticker=meta["ticker"],
            name=safe_str(item.get("name")) or meta["name"],
            cin=cin,
            market=meta["market"],
            seats=seats,
            replace_seats=True,
            protect_din_board=False,
            notes="apify foxlabs/indian-company-data",
        )
        if result.get("skipped"):
            skipped += 1
        else:
            saved += 1
    return {
        "candidates": len(cins),
        "fetched": len(items),
        "saved": saved,
        "skipped": skipped,
        "unmatched": unmatched,
    }


def update_governance_seed() -> Path:
    """Checkpoint + VACUUM live ``governance.db`` so it is safe to commit."""
    init_governance_db()
    with get_governance_connection() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("VACUUM")
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{GOVERNANCE_DB_PATH}{suffix}")
        if sidecar.is_file():
            sidecar.unlink(missing_ok=True)
    return GOVERNANCE_DB_PATH
