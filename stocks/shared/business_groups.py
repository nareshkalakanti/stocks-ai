"""Business groups — parent + spin-off families synced from demerger feed."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stocks.core.config import BASE_DIR
from stocks.core.database import (
    business_groups_count,
    clear_all_business_groups,
    load_all_business_group_members,
    save_business_group,
    upsert_business_group,
)
from stocks.core.text_utils import safe_str
from stocks.shared.corp_tags import clear_corp_tags_cache

_BUSINESS_GROUPS_SEED_PATH = BASE_DIR / "data" / "business_groups_seed.json"


def _member(
    ticker: str,
    *,
    name: str | None = None,
    market: str = "NSE",
    demerger: bool = False,
    spin_off: bool = False,
) -> dict:
    return {
        "ticker": safe_str(ticker).upper(),
        "market": safe_str(market).upper() or "NSE",
        "name": name,
        "demerger": demerger,
        "spin_off": spin_off,
    }


def _groups_from_demerger_df(df: pd.DataFrame) -> dict[str, dict]:
    """Build parent-keyed groups from demerger / spin-off rows."""
    groups: dict[str, dict] = {}
    if df is None or df.empty:
        return groups

    for _, row in df.iterrows():
        role = safe_str(row.get("row_role"))
        ticker = safe_str(row.get("ticker")).upper()
        if not ticker:
            continue

        if role == "Spin-off":
            parent = safe_str(row.get("parent_ticker")).upper()
            if not parent:
                continue
            bucket = groups.setdefault(
                parent,
                {
                    "name": safe_str(row.get("parent_company")) or parent,
                    "members": {},
                },
            )
            bucket["members"][parent] = _member(
                parent,
                name=safe_str(row.get("parent_company")) or parent,
                demerger=True,
            )
            bucket["members"][ticker] = _member(
                ticker,
                name=safe_str(row.get("company")) or ticker,
                spin_off=True,
            )
            continue

        if role == "Parent":
            parent = ticker
            demerged = safe_str(row.get("demerged_ticker")).upper()
            bucket = groups.setdefault(
                parent,
                {
                    "name": safe_str(row.get("company")) or parent,
                    "members": {},
                },
            )
            bucket["members"][parent] = _member(
                parent,
                name=safe_str(row.get("company")) or parent,
                demerger=True,
            )
            if demerged:
                bucket["members"][demerged] = _member(
                    demerged,
                    name=safe_str(row.get("demerged_company")) or demerged,
                    spin_off=True,
                )

    return groups


def sync_business_groups_from_demergers(*, refresh_demergers: bool = False) -> int:
    """Create/update business groups from demerger parent + spin-off pairs."""
    from stocks.market.merger_demerger import load_merger_demerger_table

    df, _ = load_merger_demerger_table(refresh=refresh_demergers)
    groups = _groups_from_demerger_df(df)
    if not groups:
        return 0

    saved = 0
    for parent_ticker, payload in groups.items():
        members = list(payload["members"].values())
        if len(members) < 2:
            continue
        upsert_business_group(payload["name"], members, token=parent_ticker)
        saved += 1

    clear_corp_tags_cache()
    return saved


def seed_default_business_groups(*, force: bool = False) -> int:
    """Load bundled group definitions when SQLite is empty (or replace all when force=True)."""
    if not _BUSINESS_GROUPS_SEED_PATH.is_file():
        return business_groups_count()
    if not force and business_groups_count() > 0:
        return business_groups_count()

    try:
        payload = json.loads(_BUSINESS_GROUPS_SEED_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return business_groups_count()

    groups = payload.get("groups")
    if not isinstance(groups, list) or not groups:
        return business_groups_count()

    if force:
        clear_all_business_groups()

    for group in groups:
        if not isinstance(group, dict):
            continue
        name = safe_str(group.get("name"))
        members = group.get("members")
        if not name or not isinstance(members, list) or not members:
            continue
        token = safe_str(group.get("token")).upper() or None
        normalized = [
            _member(
                m.get("ticker", ""),
                name=m.get("name"),
                market=safe_str(m.get("market")).upper() or "NSE",
                demerger=bool(m.get("demerger")),
                spin_off=bool(m.get("spin_off")),
            )
            for m in members
            if isinstance(m, dict) and safe_str(m.get("ticker"))
        ]
        if not normalized:
            continue
        if token:
            upsert_business_group(name, normalized, token=token)
        else:
            save_business_group(name, normalized, token=token)

    clear_corp_tags_cache()
    return business_groups_count()


def ensure_business_groups(*, seed_if_empty: bool = True) -> int:
    """Seed bundled groups, else auto-sync from demerger feed when DB is empty."""
    if not seed_if_empty or business_groups_count() > 0:
        return business_groups_count()
    seeded = seed_default_business_groups()
    if seeded > 0:
        return seeded
    sync_business_groups_from_demergers()
    return business_groups_count()


def load_business_group_members(*, seed_if_empty: bool = True) -> pd.DataFrame:
    if seed_if_empty:
        ensure_business_groups(seed_if_empty=True)
    return load_all_business_group_members()
