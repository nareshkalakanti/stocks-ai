"""Audit map companies missing mcap / website / about (NSE family by default)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from stocks.core.database import load_company_profiles_from_db, load_market_cap_from_db
from stocks.core.text_utils import safe_str, sanitize_website
from stocks.governance.map_data import (
    _apply_profile_overrides,
    map_company_ticker_markets,
)

NSE_GOV_MARKETS = frozenset({"NSE", "NSE SME"})


def audit_map_profile_gaps(
    *,
    min_boards: int = 2,
    nse_only: bool = True,
) -> pd.DataFrame:
    """One row per map ticker with gap flags and market."""
    tm = map_company_ticker_markets(min_boards=min_boards)
    tickers: list[str] = []
    markets: dict[str, str] = {}
    for t, m in tm:
        key = safe_str(t).upper()
        if not key:
            continue
        market = safe_str(m).upper() or "NSE"
        if nse_only and market not in NSE_GOV_MARKETS:
            continue
        if key not in markets:
            markets[key] = market
            tickers.append(key)

    tickers = sorted(tickers)
    profiles = _apply_profile_overrides(load_company_profiles_from_db(tickers))
    mcap_df = load_market_cap_from_db(tickers)
    mcap_map: dict[str, float] = {}
    if not mcap_df.empty:
        for _, row in mcap_df.iterrows():
            key = safe_str(row.get("ticker")).upper()
            val = row.get("market_cap_cr")
            if not key or val is None:
                continue
            try:
                mcap_map[key] = float(val)
            except (TypeError, ValueError):
                continue

    rows: list[dict] = []
    for t in tickers:
        p = profiles.get(t) or {}
        web = sanitize_website(p.get("website"))
        about = safe_str(p.get("long_description")).strip()
        has_mcap = t in mcap_map
        rows.append(
            {
                "ticker": t,
                "market": markets.get(t, "NSE"),
                "missing_mcap": not has_mcap,
                "missing_website": not bool(web),
                "missing_about": not bool(about),
                "market_cap_cr": mcap_map.get(t),
            }
        )
    return pd.DataFrame(rows)


def gap_summary(df: pd.DataFrame) -> dict[str, int]:
    if df is None or df.empty:
        return {
            "tickers": 0,
            "missing_mcap": 0,
            "missing_website": 0,
            "missing_about": 0,
        }
    return {
        "tickers": len(df),
        "missing_mcap": int(df["missing_mcap"].sum()),
        "missing_website": int(df["missing_website"].sum()),
        "missing_about": int(df["missing_about"].sum()),
    }


def write_governance_gaps_csv(
    path: str | Path,
    *,
    min_boards: int = 2,
    nse_only: bool = True,
) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df = audit_map_profile_gaps(min_boards=min_boards, nse_only=nse_only)
    df.to_csv(out, index=False)
    return out
